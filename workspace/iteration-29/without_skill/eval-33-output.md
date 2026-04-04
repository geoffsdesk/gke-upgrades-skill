Here's a comprehensive upgrade strategy to minimize impact on your ML inference workloads and fine-tuning jobs:

## Pre-Upgrade Preparation

### 1. Workload Analysis & Planning
```bash
# Audit current workloads and their criticality
kubectl get pods -o wide --all-namespaces | grep -E "(a100|l4)"

# Check for any system pods or critical services
kubectl get pods -n kube-system -o wide

# Review current resource utilization
kubectl top nodes
kubectl top pods --all-namespaces
```

### 2. Configure Pod Disruption Budgets
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: inference-pdb
spec:
  minAvailable: 80%  # Maintain 80% capacity during upgrades
  selector:
    matchLabels:
      workload-type: inference
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: fine-tuning-pdb
spec:
  maxUnavailable: 0  # Protect long-running training jobs
  selector:
    matchLabels:
      workload-type: fine-tuning
```

## Upgrade Strategy: Phased Node Pool Approach

### Phase 1: Control Plane Upgrade (Low Risk)
```bash
# Upgrade control plane first - minimal disruption
gcloud container clusters upgrade CLUSTER_NAME \
    --master \
    --cluster-version=1.32.x \
    --zone=YOUR_ZONE
```

### Phase 2: L4 Inference Pool Upgrade (Rolling)
Since L4s handle inference with auto-scaling, use rolling upgrade:

```bash
# Configure surge settings for minimal disruption
gcloud container node-pools update l4-inference-pool \
    --cluster=CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --max-surge-upgrade=20 \
    --max-unavailable-upgrade=5

# Start rolling upgrade
gcloud container node-pools upgrade l4-inference-pool \
    --cluster=CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --cluster-version=1.32.x
```

### Phase 3: A100 Fine-tuning Pool Upgrade (Blue-Green)
For A100s with long-running jobs, use blue-green approach:

```bash
# Create new A100 node pool with 1.32
gcloud container node-pools create a100-pool-v132 \
    --cluster=CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --machine-type=a2-ultragpu-1g \
    --accelerator=type=nvidia-a100-80gb,count=1 \
    --num-nodes=0 \
    --enable-autoscaling \
    --min-nodes=0 \
    --max-nodes=100 \
    --node-version=1.32.x \
    --node-labels=pool-generation=v132,gpu-type=a100
```

## Migration Scripts

### 1. Inference Workload Monitor
```bash
#!/bin/bash
# monitor-inference.sh - Track latency during upgrade

while true; do
    # Monitor inference latency
    kubectl get pods -l workload-type=inference -o jsonpath='{.items[*].status.containerStatuses[*].restartCount}' | \
        awk '{for(i=1;i<=NF;i++) sum+=$i; print "Total restarts:", sum; sum=0}'
    
    # Check node readiness
    kubectl get nodes -l gpu-type=l4 --no-headers | \
        awk '{ready+= ($2=="Ready"); total++} END {printf "L4 Nodes Ready: %d/%d (%.1f%%)\n", ready, total, ready/total*100}'
    
    sleep 30
done
```

### 2. Fine-tuning Job Protection
```bash
#!/bin/bash
# protect-training-jobs.sh

# Cordon old A100 nodes with running training jobs
for node in $(kubectl get nodes -l gpu-type=a100,pool-generation!=v132 -o name); do
    # Check if node has long-running pods
    if kubectl get pods --field-selector spec.nodeName=${node#node/} | grep -q "fine-tuning"; then
        echo "Cordoning $node - has active training jobs"
        kubectl cordon $node
    fi
done
```

### 3. Graceful A100 Migration
```yaml
# migration-job.yaml - Orchestrate A100 pool migration
apiVersion: batch/v1
kind: Job
metadata:
  name: a100-migration-orchestrator
spec:
  template:
    spec:
      containers:
      - name: migrator
        image: google/cloud-sdk:slim
        command:
        - /bin/bash
        - -c
        - |
          # Wait for current training jobs to complete
          while kubectl get pods -l workload-type=fine-tuning,gpu-type=a100 | grep -q Running; do
            echo "Waiting for training jobs to complete..."
            kubectl get pods -l workload-type=fine-tuning --field-selector status.phase=Running
            sleep 300  # Check every 5 minutes
          done
          
          # Scale up new pool
          gcloud container node-pools resize a100-pool-v132 --num-nodes=100
          
          # Update node selectors for new jobs
          kubectl patch deployment inference-router -p '{"spec":{"template":{"spec":{"nodeSelector":{"pool-generation":"v132"}}}}}'
          
          # Drain old nodes
          for node in $(kubectl get nodes -l gpu-type=a100,pool-generation!=v132 -o name); do
            kubectl drain $node --ignore-daemonsets --delete-emptydir-data --force
          done
      restartPolicy: Never
```

## Monitoring & Validation

### 1. Real-time Monitoring Dashboard
```bash
# Create monitoring script for upgrade progress
cat << 'EOF' > upgrade-monitor.sh
#!/bin/bash
watch -n 10 'echo "=== Cluster Status ==="
kubectl get nodes -l gpu-type=l4 --no-headers | awk "{ready += (\$2==\"Ready\"); total++} END {print \"L4 Nodes: \" ready \"/\" total}"
kubectl get nodes -l gpu-type=a100 --no-headers | awk "{ready += (\$2==\"Ready\"); total++} END {print \"A100 Nodes: \" ready \"/\" total}"
echo "=== Active Workloads ==="
kubectl get pods -l workload-type=inference --no-headers | wc -l | xargs echo "Inference Pods:"
kubectl get pods -l workload-type=fine-tuning --no-headers | wc -l | xargs echo "Training Pods:"
echo "=== Recent Events ==="
kubectl get events --sort-by=.lastTimestamp | tail -5'
EOF
chmod +x upgrade-monitor.sh
```

### 2. Rollback Plan
```bash
# rollback-plan.sh
#!/bin/bash
case "$1" in
  "l4-rollback")
    echo "Rolling back L4 pool..."
    gcloud container node-pools rollback l4-inference-pool \
        --cluster=CLUSTER_NAME --zone=YOUR_ZONE
    ;;
  "a100-rollback")
    echo "Switching back to old A100 pool..."
    kubectl patch deployment inference-router -p '{"spec":{"template":{"spec":{"nodeSelector":{"pool-generation":"v131"}}}}}'
    gcloud container node-pools resize a100-pool-v131 --num-nodes=100
    ;;
esac
```

## Timeline & Execution

### Recommended Schedule:
1. **Day 1**: Control plane upgrade (5-10 minutes)
2. **Day 2**: L4 pool rolling upgrade (2-4 hours)
3. **Day 3-4**: Monitor fine-tuning job completion
4. **Day 5**: A100 blue-green migration (30 minutes active work)
5. **Day 6**: Cleanup old A100 pool

### Key Success Metrics:
- Inference latency increase < 5%
- Zero training job interruptions
- Node availability > 95% throughout upgrade
- Successful validation of GPU drivers and CUDA compatibility

This approach ensures minimal disruption to your ML workloads while providing safe rollback options at each phase.