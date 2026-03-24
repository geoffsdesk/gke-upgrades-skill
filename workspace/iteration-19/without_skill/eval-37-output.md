# GKE 1.31 → 1.32 Upgrade Plan for Mixed AI/ML Platform

## Executive Summary

This phased upgrade plan prioritizes training continuity and inference availability while minimizing disruption across your 5,000-node AI/ML platform.

## Pre-Upgrade Preparation

### 1. Infrastructure Audit & Backup
```bash
# Backup cluster configurations
kubectl get all --all-namespaces -o yaml > cluster-backup-$(date +%Y%m%d).yaml

# Document current resource utilization
kubectl top nodes > node-utilization-pre-upgrade.txt
kubectl get pods --all-namespaces --field-selector=status.phase=Running > running-pods-pre-upgrade.txt
```

### 2. Compatibility Testing
- Set up isolated test cluster with representative workloads
- Validate GPU drivers compatibility (NVIDIA Driver 525+ for H100/A100)
- Test key ML frameworks (TensorFlow, PyTorch, JAX)
- Verify CSI drivers and storage configurations

### 3. Monitoring & Alerting Setup
```yaml
# Enhanced monitoring for upgrade
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-monitoring
data:
  alert-rules.yaml: |
    groups:
    - name: upgrade-alerts
      rules:
      - alert: NodeUpgradeStuck
        expr: kube_node_info{kubelet_version!="1.32"} > 0
        for: 30m
      - alert: GPUWorkloadDisrupted
        expr: nvidia_gpu_utilization < 0.8
        for: 15m
```

## Phase 1: Development Environment (Week 1)
**Target: 500 T4 nodes**

### Day 1-2: Control Plane Upgrade
```bash
# Upgrade control plane first
gcloud container clusters upgrade ml-cluster \
  --master \
  --cluster-version=1.32 \
  --zone=us-central1-a
```

### Day 3-5: T4 Node Pool Upgrade
```bash
# Create new T4 node pool with 1.32
gcloud container node-pools create t4-nodes-v132 \
  --cluster=ml-cluster \
  --machine-type=n1-standard-4 \
  --accelerator=type=nvidia-tesla-t4,count=1 \
  --num-nodes=500 \
  --node-version=1.32 \
  --enable-autoscaling \
  --max-nodes=600 \
  --min-nodes=400

# Drain and migrate development workloads
kubectl cordon -l node-pool=t4-nodes-v131
kubectl drain -l node-pool=t4-nodes-v131 --ignore-daemonsets --delete-emptydir-data

# Delete old node pool
gcloud container node-pools delete t4-nodes-v131 --cluster=ml-cluster
```

## Phase 2: CPU Services Infrastructure (Week 2)
**Target: 1,000 CPU nodes**

### Rolling Upgrade Strategy
```bash
# Upgrade CPU nodes in batches of 200
for batch in {1..5}; do
  echo "Upgrading CPU batch $batch"
  
  # Create new CPU node pool batch
  gcloud container node-pools create cpu-nodes-v132-batch$batch \
    --cluster=ml-cluster \
    --machine-type=n2-standard-8 \
    --num-nodes=200 \
    --node-version=1.32
  
  # Wait for nodes to be ready
  kubectl wait --for=condition=Ready nodes -l batch=cpu-batch$batch --timeout=600s
  
  # Drain corresponding old nodes
  kubectl drain -l batch=cpu-batch$batch,version=v131 \
    --ignore-daemonsets \
    --delete-emptydir-data \
    --grace-period=300
  
  # Verify services are healthy
  sleep 300
done
```

## Phase 3: A100 Inference Nodes (Week 3-4)
**Target: 1,500 A100 nodes**

### Blue-Green Deployment Approach
```yaml
# Inference service configuration with affinity
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inference-service
spec:
  replicas: 100
  template:
    spec:
      affinity:
        nodeAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            preference:
              matchExpressions:
              - key: node-version
                operator: In
                values: ["v132"]
          - weight: 50
            preference:
              matchExpressions:
              - key: node-version
                operator: In
                values: ["v131"]
```

```bash
# Week 3: Upgrade 50% of A100 nodes (750 nodes)
gcloud container node-pools create a100-inference-v132-primary \
  --cluster=ml-cluster \
  --machine-type=a2-highgpu-1g \
  --accelerator=type=nvidia-tesla-a100,count=1 \
  --num-nodes=750 \
  --node-version=1.32 \
  --node-taints=nvidia.com/gpu=present:NoSchedule

# Gradually shift inference traffic
kubectl patch deployment inference-service -p '{"spec":{"template":{"spec":{"nodeSelector":{"node-version":"v132"}}}}}'

# Week 4: Complete A100 upgrade
gcloud container node-pools create a100-inference-v132-secondary \
  --cluster=ml-cluster \
  --machine-type=a2-highgpu-1g \
  --accelerator=type=nvidia-tesla-a100,count=1 \
  --num-nodes=750 \
  --node-version=1.32
```

## Phase 4: H100 Training Nodes (Week 5-6)
**Target: 2,000 H100 nodes**

### Training-Aware Upgrade Strategy
```bash
# Pre-upgrade: Identify long-running training jobs
kubectl get pods -l workload-type=training --field-selector=status.phase=Running \
  -o custom-columns=NAME:.metadata.name,AGE:.status.startTime,NODE:.spec.nodeName

# Create checkpoint backup job
apiVersion: batch/v1
kind: Job
metadata:
  name: training-checkpoint-backup
spec:
  template:
    spec:
      containers:
      - name: checkpoint-backup
        image: gcr.io/ml-platform/checkpoint-backup:latest
        command: ["/bin/bash"]
        args:
        - -c
        - |
          # Backup all active training checkpoints
          gsutil -m cp -r /training-data/checkpoints/* gs://ml-checkpoints-backup/upgrade-$(date +%Y%m%d)/
```

### Coordinated H100 Upgrade
```bash
# Week 5: Upgrade training nodes in maintenance windows
# Upgrade 25% per day during low-training hours (typically 2-6 AM)

for day in {1..4}; do
  echo "Day $day: Upgrading 500 H100 nodes"
  
  # Schedule maintenance window
  gcloud container clusters update ml-cluster \
    --maintenance-window-start="2023-12-0${day}T02:00:00Z" \
    --maintenance-window-end="2023-12-0${day}T06:00:00Z"
  
  # Create new H100 node pool
  gcloud container node-pools create h100-training-v132-batch$day \
    --cluster=ml-cluster \
    --machine-type=a3-highgpu-8g \
    --accelerator=type=nvidia-h100-80gb,count=8 \
    --num-nodes=500 \
    --node-version=1.32 \
    --placement-type=COMPACT \
    --node-taints=training=true:NoSchedule
  
  # Coordinated training job migration
  kubectl patch deployment training-scheduler -p '{
    "spec": {
      "template": {
        "spec": {
          "nodeSelector": {
            "batch": "h100-batch'$day'",
            "version": "v132"
          }
        }
      }
    }
  }'
  
  # Wait for training jobs to migrate gracefully
  sleep 7200  # 2 hours
  
  # Drain old nodes
  kubectl drain -l batch=h100-batch$day,version=v131 \
    --ignore-daemonsets \
    --grace-period=600 \
    --timeout=3600s
done
```

## Phase 5: Validation & Cleanup (Week 7)

### Comprehensive Validation
```bash
# Validate all nodes are on 1.32
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion

# GPU validation script
#!/bin/bash
echo "Validating GPU accessibility..."
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: gpu-validation
spec:
  parallelism: 50
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: gpu-test
        image: nvidia/cuda:12.0-runtime-ubuntu20.04
        command: ["nvidia-smi"]
        resources:
          limits:
            nvidia.com/gpu: 1
EOF

# Performance baseline testing
kubectl apply -f performance-test-suite.yaml
```

### Cleanup Operations
```bash
# Remove old node pools
gcloud container node-pools list --cluster=ml-cluster --filter="version~1.31" --format="value(name)" | \
  xargs -I {} gcloud container node-pools delete {} --cluster=ml-cluster --quiet

# Update node selectors and remove temporary labels
kubectl patch deployment inference-service --type='json' -p='[{"op": "remove", "path": "/spec/template/spec/nodeSelector/node-version"}]'
```

## Rollback Strategy

### Quick Rollback Procedure
```bash
# Emergency rollback script
#!/bin/bash
EMERGENCY_ROLLBACK=true

if [ "$EMERGENCY_ROLLBACK" = true ]; then
  echo "Initiating emergency rollback..."
  
  # Restore from backup
  gcloud container clusters create ml-cluster-rollback \
    --cluster-version=1.31 \
    --num-nodes=0
  
  # Restore workloads
  kubectl apply -f cluster-backup-$(date +%Y%m%d).yaml
  
  # Update DNS to point to rollback cluster
  gcloud dns record-sets transaction start --zone=ml-zone
  gcloud dns record-sets transaction remove --zone=ml-zone \
    --name=ml-api.company.com. --type=A --ttl=300 \
    --records=[OLD_IP]
  gcloud dns record-sets transaction add --zone=ml-zone \
    --name=ml-api.company.com. --type=A --ttl=300 \
    --records=[ROLLBACK_IP]
  gcloud dns record-sets transaction execute --zone=ml-zone
fi
```

## Monitoring & Success Criteria

### Key Metrics to Track
- Training job completion rate: >98%
- Inference response latency: <200ms p95
- GPU utilization: >80% during active training
- Node readiness time: <10 minutes
- Zero data loss during migration

### Post-Upgrade Optimization
```bash
# Enable new 1.32 features
kubectl patch cluster ml-cluster --type=merge -p='{
  "spec": {
    "features": {
      "nodePoolAutoConfig": {
        "enabled": true
      },
      "improvedGPUScheduling": {
        "enabled": true
      }
    }
  }
}'
```

This phased approach ensures minimal disruption to your critical AI/ML workloads while maintaining high availability throughout the upgrade process.