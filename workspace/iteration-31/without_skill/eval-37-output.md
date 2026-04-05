# GKE Cluster Upgrade Plan: v1.31 → v1.32
## Mixed AI/ML Platform - 5,000 Node Fleet

## Executive Summary
This plan prioritizes **training continuity** and **inference availability** through a carefully orchestrated 5-phase upgrade approach, minimizing disruption to critical AI/ML workloads.

## Pre-Upgrade Preparation

### 1. Compatibility Validation
```bash
# Test upgrade compatibility
kubectl version --short
kubectl get nodes --show-labels
kubectl api-resources --verbs=list --namespaced -o name | head -20

# Validate AI/ML workload compatibility
kubectl get pods -A -o jsonpath='{range .items[*]}{.spec.containers[*].image}{"\n"}{end}' | sort -u
```

### 2. Backup Strategy
```bash
# Backup cluster state
kubectl get all --all-namespaces -o yaml > cluster-backup-pre-upgrade.yaml
kubectl get pv,pvc --all-namespaces -o yaml > storage-backup.yaml

# Export training checkpoints and model artifacts
kubectl get pods -l workload-type=training -o yaml > training-workloads.yaml
```

### 3. Monitoring Setup
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-monitoring
data:
  training-jobs.sh: |
    #!/bin/bash
    watch -n 30 'kubectl get pods -l workload-type=training --field-selector=status.phase=Running'
  
  inference-health.sh: |
    #!/bin/bash
    watch -n 10 'kubectl get pods -l workload-type=inference -o wide'
```

## Phase 1: CPU Service Nodes (Days 1-2)
**Target: 1,000 CPU nodes | Risk: LOW | Impact: Service degradation**

### 1.1 Preparation
```bash
# Create node pool with v1.32
gcloud container node-pools create cpu-nodes-v132 \
  --cluster=ai-ml-cluster \
  --machine-type=c2-standard-16 \
  --num-nodes=100 \
  --node-version=1.32.0-gke.1200 \
  --node-labels=upgrade-batch=cpu-phase1,workload-type=services

# Verify new nodes
kubectl get nodes -l upgrade-batch=cpu-phase1
```

### 1.2 Migration Strategy
```yaml
# Update service deployments with node affinity
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-gateway
spec:
  template:
    spec:
      affinity:
        nodeAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            preference:
              matchExpressions:
              - key: upgrade-batch
                operator: In
                values: ["cpu-phase1"]
```

### 1.3 Execution
```bash
# Rolling migration - 200 nodes per batch
for batch in {1..5}; do
  echo "Migrating CPU batch $batch"
  
  # Cordon old nodes
  kubectl get nodes -l node-pool=cpu-old-batch-$batch -o name | xargs kubectl cordon
  
  # Scale up new node pool
  gcloud container node-pools resize cpu-nodes-v132 --num-nodes=$((batch * 200))
  
  # Wait for services to migrate
  kubectl rollout restart deployment/api-gateway
  kubectl rollout restart deployment/monitoring-stack
  kubectl rollout restart deployment/logging-aggregator
  
  # Verify migration
  sleep 300
  kubectl get pods -o wide | grep -v v1.32 || echo "Migration successful for batch $batch"
done
```

## Phase 2: Development T4 Nodes (Days 3-4)
**Target: 500 T4 nodes | Risk: MEDIUM | Impact: Development workflow**

### 2.1 Development Environment Preparation
```bash
# Create maintenance window notification
kubectl create configmap dev-maintenance \
  --from-literal=message="T4 development nodes upgrading. Save work and prepare for brief interruptions."

# Backup development workloads
kubectl get pods -l environment=development -o yaml > dev-workloads-backup.yaml
```

### 2.2 Upgrade Execution
```bash
# Create new T4 node pool
gcloud container node-pools create t4-dev-v132 \
  --cluster=ai-ml-cluster \
  --accelerator=type=nvidia-tesla-t4,count=1 \
  --machine-type=n1-standard-8 \
  --num-nodes=500 \
  --node-version=1.32.0-gke.1200 \
  --node-labels=workload-type=development,gpu-type=t4

# Install GPU drivers
kubectl apply -f https://raw.githubusercontent.com/GoogleCloudPlatform/container-engine-accelerators/master/nvidia-driver-installer/cos/daemonset-preloaded.yaml

# Migrate development workloads
kubectl patch deployment jupyter-hub -p '{"spec":{"template":{"spec":{"nodeSelector":{"gpu-type":"t4","workload-type":"development"}}}}}'
```

### 2.3 Validation
```bash
# Test GPU availability
kubectl run gpu-test --image=nvidia/cuda:11.0-runtime-ubuntu18.04 --limits=nvidia.com/gpu=1 -- nvidia-smi

# Verify development tools
kubectl get pods -l app=jupyter -o wide
kubectl logs -l app=jupyter | grep "GPU detected"
```

## Phase 3: A100 Inference Nodes (Days 5-8)
**Target: 1,500 A100 nodes | Risk: HIGH | Impact: Service availability**

### 3.1 Blue-Green Deployment Preparation
```bash
# Create new A100 inference pool (Green)
gcloud container node-pools create a100-inference-v132-green \
  --cluster=ai-ml-cluster \
  --accelerator=type=nvidia-tesla-a100,count=2 \
  --machine-type=a2-highgpu-2g \
  --num-nodes=0 \
  --max-nodes=1500 \
  --node-version=1.32.0-gke.1200 \
  --node-labels=workload-type=inference,gpu-type=a100,deployment=green
```

### 3.2 Traffic Splitting Strategy
```yaml
# Update inference service for gradual migration
apiVersion: v1
kind: Service
metadata:
  name: model-inference
  annotations:
    cloud.google.com/backend-config: '{"default": "inference-backend-config"}'
spec:
  selector:
    app: inference-server
---
apiVersion: cloud.google.com/v1
kind: BackendConfig
metadata:
  name: inference-backend-config
spec:
  customRequestHeaders:
    headers:
    - "X-Deployment-Version:green"
  sessionAffinity:
    affinityType: "CLIENT_IP"
```

### 3.3 Rolling Upgrade with Traffic Management
```bash
# Phase 3a: Deploy 25% capacity on new nodes
gcloud container node-pools resize a100-inference-v132-green --num-nodes=375

# Deploy inference workloads to green environment
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inference-server-green
spec:
  replicas: 375
  selector:
    matchLabels:
      app: inference-server
      deployment: green
  template:
    spec:
      nodeSelector:
        deployment: green
        workload-type: inference
      containers:
      - name: inference-server
        image: your-registry/inference-server:latest
        resources:
          limits:
            nvidia.com/gpu: 2
EOF

# Implement traffic splitting (25% to green)
kubectl patch service model-inference -p '{"spec":{"selector":{"deployment":null}}}'

# Monitor inference latency and error rates
for i in {1..10}; do
  curl -s http://your-inference-endpoint/health | jq '.latency,.errors'
  sleep 30
done
```

### 3.4 Progressive Traffic Migration
```bash
# Phase 3b: Scale to 50% (Day 6)
gcloud container node-pools resize a100-inference-v132-green --num-nodes=750
kubectl scale deployment inference-server-green --replicas=750

# Phase 3c: Scale to 75% (Day 7)
gcloud container node-pools resize a100-inference-v132-green --num-nodes=1125
kubectl scale deployment inference-server-green --replicas=1125

# Phase 3d: Complete migration (Day 8)
gcloud container node-pools resize a100-inference-v132-green --num-nodes=1500
kubectl scale deployment inference-server-green --replicas=1500

# Remove blue environment
kubectl scale deployment inference-server-blue --replicas=0
gcloud container node-pools delete a100-inference-v131-blue --quiet
```

## Phase 4: H100 Training Nodes - Batch 1 (Days 9-11)
**Target: 1,000 H100 nodes | Risk: CRITICAL | Impact: Training interruption**

### 4.1 Training Job Analysis
```bash
# Identify long-running training jobs
kubectl get pods -l workload-type=training -o custom-columns=NAME:.metadata.name,AGE:.status.startTime,NODE:.spec.nodeName

# Create training checkpoint backup
kubectl exec -it training-pod-1 -- python -c "
import torch
torch.save(model.state_dict(), '/shared-storage/checkpoint-pre-upgrade.pth')
print('Checkpoint saved')
"
```

### 4.2 Coordinated Migration
```bash
# Create new H100 pool for first batch
gcloud container node-pools create h100-training-v132-batch1 \
  --cluster=ai-ml-cluster \
  --accelerator=type=nvidia-h100-80gb,count=8 \
  --machine-type=a3-highgpu-8g \
  --num-nodes=1000 \
  --node-version=1.32.0-gke.1200 \
  --node-labels=workload-type=training,gpu-type=h100,batch=1

# Wait for nodes to be ready
kubectl wait --for=condition=Ready nodes -l batch=1 --timeout=1800s
```

### 4.3 Training Job Migration
```yaml
# Update training jobs with checkpoint restoration
apiVersion: batch/v1
kind: Job
metadata:
  name: training-job-migrated
spec:
  template:
    spec:
      nodeSelector:
        batch: "1"
        gpu-type: h100
      initContainers:
      - name: restore-checkpoint
        image: your-registry/training-image:latest
        command: ["python", "-c"]
        args: 
        - |
          import torch
          import os
          if os.path.exists('/shared-storage/checkpoint-pre-upgrade.pth'):
            checkpoint = torch.load('/shared-storage/checkpoint-pre-upgrade.pth')
            print(f"Restored checkpoint from epoch {checkpoint.get('epoch', 'unknown')}")
      containers:
      - name: training
        image: your-registry/training-image:latest
        resources:
          limits:
            nvidia.com/gpu: 8
        volumeMounts:
        - name: shared-storage
          mountPath: /shared-storage
```

### 4.4 Migration Execution
```bash
# Migrate training jobs in maintenance windows
for job in $(kubectl get jobs -l workload-type=training,batch=old-1 -o name); do
  echo "Migrating $job"
  
  # Create checkpoint
  kubectl exec -it ${job}-pod -- python /scripts/create_checkpoint.py
  
  # Delete old job
  kubectl delete $job
  
  # Create new job on v1.32 nodes
  kubectl apply -f training-jobs/$(basename $job)-v132.yaml
  
  # Wait for job to start
  kubectl wait --for=condition=Ready pod -l job-name=$(basename $job) --timeout=600s
  
  sleep 120  # Stagger migrations
done
```

## Phase 5: H100 Training Nodes - Batch 2 (Days 12-14)
**Target: 1,000 H100 nodes | Risk: CRITICAL | Impact: Training interruption**

### 5.1 Final Batch Preparation
```bash
# Create final H100 node pool
gcloud container node-pools create h100-training-v132-batch2 \
  --cluster=ai-ml-cluster \
  --accelerator=type=nvidia-h100-80gb,count=8 \
  --machine-type=a3-highgpu-8g \
  --num-nodes=1000 \
  --node-version=1.32.0-gke.1200 \
  --node-labels=workload-type=training,gpu-type=h100,batch=2

# Verify all GPU drivers and CUDA compatibility
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: gpu-validation
spec:
  selector:
    matchLabels:
      name: gpu-validation
  template:
    spec:
      nodeSelector:
        batch: "2"
      containers:
      - name: validator
        image: nvidia/cuda:12.0-runtime-ubuntu20.04
        command: ["sh", "-c"]
        args: ["nvidia-smi && python3 -c 'import torch; print(torch.cuda.is_available())'"]
        resources:
          limits:
            nvidia.com/gpu: 1
EOF
```

### 5.2 Complete Final Migration
```bash
# Execute final training job migrations
kubectl get jobs -l workload-type=training,batch=old-2 -o name | while read job; do
  echo "Final migration: $job"
  
  # Enhanced checkpoint with metadata
  kubectl exec -it ${job}-pod -- python -c "
import torch
import json
from datetime import datetime

# Save comprehensive checkpoint
checkpoint = {
    'model_state': model.state_dict(),
    'optimizer_state': optimizer.state_dict(),
    'epoch': current_epoch,
    'loss': current_loss,
    'timestamp': datetime.now().isoformat(),
    'migration': 'v1.31-to-v1.32'
}
torch.save(checkpoint, '/shared-storage/final-checkpoint.pth')
print('Enhanced checkpoint saved for migration')
  "
  
  # Apply new job configuration
  kubectl apply -f training-jobs-v132/$(basename $job).yaml
  
  # Monitor restoration
  kubectl logs -f ${job}-pod | grep -E "(Checkpoint|Restored|Training resumed)"
done
```

## Post-Upgrade Validation

### 1. Comprehensive Health Check
```bash
# Verify all nodes are on v1.32
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion | grep -v v1.32 || echo "All nodes upgraded successfully"

# Check GPU availability across all node types
kubectl run gpu-check-h100 --image=nvidia/cuda:12.0-runtime-ubuntu20.04 --limits=nvidia.com/gpu=8 --overrides='{"spec":{"nodeSelector":{"gpu-type":"h100"}}}' -- nvidia-smi
kubectl run gpu-check-a100 --image=nvidia/cuda:11.0-runtime-ubuntu20.04 --limits=nvidia.com/gpu=2 --overrides='{"spec":{"nodeSelector":{"gpu-type":"a100"}}}' -- nvidia-smi
kubectl run gpu-check-t4 --image=nvidia/cuda:11.0-runtime-ubuntu20.04 --limits=nvidia.com/gpu=1 --overrides='{"spec":{"nodeSelector":{"gpu-type":"t4"}}}' -- nvidia-smi
```

### 2. Workload Validation
```bash
# Training jobs health
kubectl get jobs -l workload-type=training -o custom-columns=NAME:.metadata.name,COMPLETIONS:.status.completions,ACTIVE:.status.active,FAILED:.status.failed

# Inference service performance
for i in {1..5}; do
  curl -s -w "Response time: %{time_total}s\n" http://your-inference-