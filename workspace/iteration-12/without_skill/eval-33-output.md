Here's a comprehensive upgrade strategy to minimize impact on your ML inference workloads:

## Pre-Upgrade Preparation

### 1. Backup and Validation
```bash
# Backup critical configurations
kubectl get nodes -o yaml > nodes-backup.yaml
kubectl get pods --all-namespaces -o yaml > pods-backup.yaml

# Check workload distribution
kubectl get pods -o wide --field-selector=spec.nodeName=<node-name>
```

### 2. Configure Pod Disruption Budgets
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: inference-pdb
spec:
  minAvailable: 80%  # Adjust based on your availability requirements
  selector:
    matchLabels:
      app: ml-inference
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
spec:
  maxUnavailable: 1
  selector:
    matchLabels:
      app: ml-training
```

## Upgrade Strategy: Blue-Green Node Pool Approach

### Phase 1: Create New Node Pools (1.32)

```bash
# Create new L4 node pool
gcloud container node-pools create l4-pool-v132 \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --machine-type=g2-standard-48 \
  --accelerator=type=nvidia-l4,count=4 \
  --num-nodes=0 \
  --enable-autoscaling \
  --min-nodes=0 \
  --max-nodes=200 \
  --node-version=1.32.x \
  --node-taints=gpu-type=l4:NoSchedule \
  --node-labels=gpu-type=l4,pool-version=v132

# Create new A100 node pool
gcloud container node-pools create a100-pool-v132 \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --machine-type=a2-highgpu-4g \
  --accelerator=type=nvidia-tesla-a100,count=4 \
  --num-nodes=0 \
  --enable-autoscaling \
  --min-nodes=0 \
  --max-nodes=100 \
  --node-version=1.32.x \
  --node-taints=gpu-type=a100:NoSchedule \
  --node-labels=gpu-type=a100,pool-version=v132
```

### Phase 2: Update Node Selectors for Gradual Migration

```yaml
# Update inference deployments to prefer new nodes
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ml-inference-l4
spec:
  template:
    spec:
      nodeSelector:
        gpu-type: l4
      affinity:
        nodeAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            preference:
              matchExpressions:
              - key: pool-version
                operator: In
                values: ["v132"]
          - weight: 50
            preference:
              matchExpressions:
              - key: pool-version
                operator: In
                values: ["v131"]
      tolerations:
      - key: gpu-type
        operator: Equal
        value: l4
        effect: NoSchedule
```

### Phase 3: Controlled Migration Script

```bash
#!/bin/bash

# Migration script for inference workloads
migrate_inference_workloads() {
  # Scale up new node pools gradually
  for target_nodes in 20 50 100 150 200; do
    echo "Scaling L4 v132 pool to $target_nodes nodes"
    gcloud container clusters resize your-cluster-name \
      --node-pool=l4-pool-v132 \
      --num-nodes=$target_nodes \
      --zone=your-zone
    
    # Wait for nodes to be ready
    kubectl wait --for=condition=Ready nodes -l pool-version=v132,gpu-type=l4 --timeout=600s
    
    # Force pod rescheduling in batches
    kubectl get pods -l app=ml-inference,gpu-type=l4 -o name | \
      head -n 20 | xargs -I {} kubectl delete {}
    
    # Wait for pods to reschedule
    sleep 180
    
    # Check health
    kubectl get pods -l app=ml-inference --field-selector=status.phase!=Running
    
    read -p "Continue with next batch? (y/n) " -n 1 -r
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
      break
    fi
  done
}

# Migration for training workloads (more careful approach)
migrate_training_workloads() {
  # Wait for current training jobs to complete or reach checkpoint
  echo "Waiting for training jobs to reach safe checkpoint..."
  
  # List running training jobs
  kubectl get pods -l app=ml-training --field-selector=status.phase=Running
  
  # Scale A100 v132 pool
  gcloud container clusters resize your-cluster-name \
    --node-pool=a100-pool-v132 \
    --num-nodes=50 \
    --zone=your-zone
    
  # Update training job templates to use new nodes
  # This affects new jobs, existing jobs continue on old nodes
}
```

## Traffic Management During Upgrade

### 1. Implement Circuit Breaker Pattern
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: inference-config
data:
  circuit-breaker.yaml: |
    failure_threshold: 5
    timeout: 30s
    fallback_enabled: true
    health_check_interval: 10s
```

### 2. Enhanced Readiness Probes
```yaml
spec:
  containers:
  - name: ml-inference
    readinessProbe:
      httpGet:
        path: /health/ready
        port: 8080
      initialDelaySeconds: 30
      periodSeconds: 10
      timeoutSeconds: 5
      failureThreshold: 3
    livenessProbe:
      httpGet:
        path: /health/live
        port: 8080
      initialDelaySeconds: 60
      periodSeconds: 30
```

## Monitoring and Rollback Strategy

### 1. Key Metrics to Monitor
```bash
# Latency monitoring
kubectl top pods --containers -l app=ml-inference

# GPU utilization
nvidia-smi --query-gpu=utilization.gpu --format=csv

# Pod scheduling events
kubectl get events --field-selector=reason=FailedScheduling
```

### 2. Automated Rollback Trigger
```bash
#!/bin/bash
# Health check script
check_inference_health() {
  local failure_count=0
  local max_failures=5
  
  while [ $failure_count -lt $max_failures ]; do
    # Check average response time
    avg_latency=$(curl -s http://your-monitoring-endpoint/metrics | \
      grep inference_latency_avg | awk '{print $2}')
    
    if (( $(echo "$avg_latency > 500" | bc -l) )); then
      ((failure_count++))
      echo "High latency detected: ${avg_latency}ms (attempt $failure_count)"
    else
      failure_count=0
    fi
    
    sleep 30
  done
  
  echo "ALERT: Sustained high latency - consider rollback"
  # Trigger rollback process
}
```

## Fine-tuning Job Handling

### 1. Job Checkpointing
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: fine-tuning-job
spec:
  template:
    spec:
      restartPolicy: OnFailure
      containers:
      - name: training
        env:
        - name: CHECKPOINT_INTERVAL
          value: "600"  # Checkpoint every 10 minutes
        - name: CHECKPOINT_PATH
          value: "/mnt/checkpoints"
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /mnt/checkpoints
      volumes:
      - name: checkpoint-storage
        persistentVolumeClaim:
          claimName: training-checkpoints
```

### 2. Graceful Job Migration
```bash
# Script to handle training job migration
migrate_training_job() {
  local job_name=$1
  
  # Signal job to checkpoint
  kubectl exec -it $job_name -- kill -SIGUSR1 1
  
  # Wait for checkpoint to complete
  sleep 300
  
  # Update job to use new node pool
  kubectl patch job $job_name -p '{"spec":{"template":{"spec":{"nodeSelector":{"pool-version":"v132"}}}}}'
  
  # Delete old pod to trigger rescheduling
  kubectl delete pod -l job-name=$job_name
}
```

## Execution Timeline

1. **Day 1**: Create new node pools, test with canary workloads
2. **Day 2-3**: Migrate inference workloads in batches (L4 pool first)
3. **Day 4**: Wait for training jobs to complete, migrate A100 pool
4. **Day 5**: Verify all workloads, drain old pools
5. **Day 6**: Delete old node pools

This approach ensures minimal disruption while maintaining your SLA requirements for both inference latency and training job continuity.