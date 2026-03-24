# GKE Cluster Upgrade Plan: v1.31 → v1.32
**Mixed AI/ML Platform - 5,000 Node Fleet**

## Executive Summary

This phased upgrade plan prioritizes business continuity by protecting training workloads and maintaining inference availability while systematically upgrading the entire 5,000-node fleet.

## Pre-Upgrade Prerequisites

### 1. Infrastructure Preparation
```bash
# Backup cluster configuration
kubectl get nodes -o yaml > cluster-nodes-backup.yaml
kubectl get all --all-namespaces -o yaml > workloads-backup.yaml

# Verify cluster health
kubectl get nodes --no-headers | awk '{print $2}' | sort | uniq -c
kubectl top nodes
```

### 2. Workload Assessment
```yaml
# Create node affinity rules for critical workloads
apiVersion: v1
kind: Pod
spec:
  affinity:
    nodeAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        preference:
          matchExpressions:
          - key: upgrade-phase
            operator: NotIn
            values: ["active"]
```

### 3. Monitoring Setup
- Set up enhanced monitoring for GPU utilization
- Configure alerting for training job failures
- Establish inference latency baselines

## Phase 1: CPU Services Layer (Days 1-2)
**Target: 1,000 CPU nodes**

### Rationale
- Lowest risk to AI/ML workloads
- Establishes upgrade confidence
- Services can tolerate brief interruptions

### Execution Plan
```bash
# Create maintenance node pools
gcloud container node-pools create cpu-upgrade-pool \
    --cluster=ml-cluster \
    --machine-type=n1-standard-16 \
    --num-nodes=200 \
    --node-version=1.32

# Gradual migration in batches of 200 nodes
for batch in {1..5}; do
    kubectl drain -l "nodepool=cpu-services-batch-${batch}" \
        --ignore-daemonsets \
        --delete-emptydir-data \
        --grace-period=300
    
    # Upgrade batch
    gcloud container clusters upgrade ml-cluster \
        --node-pool=cpu-services-${batch} \
        --cluster-version=1.32
    
    # Validate batch
    kubectl wait --for=condition=Ready nodes \
        -l "nodepool=cpu-services-batch-${batch}" \
        --timeout=600s
        
    sleep 1800  # 30-min stabilization period
done
```

### Validation Criteria
- All services responding within SLA
- No increase in error rates
- Resource utilization normal

## Phase 2: Development T4 Nodes (Days 3-4)
**Target: 500 T4 nodes**

### Rationale
- Development workloads are interruptible
- Tests GPU upgrade procedures
- Smaller blast radius for learning

### Execution Plan
```bash
# Label development nodes for controlled upgrade
kubectl label nodes -l "gpu-type=t4,environment=development" upgrade-phase=scheduled

# Implement blue-green approach for T4 nodes
gcloud container node-pools create t4-development-v132 \
    --cluster=ml-cluster \
    --accelerator=type=nvidia-tesla-t4,count=1 \
    --machine-type=n1-standard-8 \
    --num-nodes=500 \
    --node-version=1.32 \
    --disk-size=200GB

# Migrate development workloads
kubectl annotate nodes -l "gpu-type=t4,environment=development" \
    node.kubernetes.io/unschedulable=NoSchedule

# Drain original T4 nodes after workload migration
kubectl drain -l "gpu-type=t4,environment=development,upgrade-phase=scheduled" \
    --ignore-daemonsets \
    --delete-emptydir-data \
    --grace-period=600
```

### Testing Protocol
- Validate GPU drivers (NVIDIA 535+)
- Test CUDA compatibility
- Verify development tool functionality

## Phase 3: A100 Inference Nodes (Days 5-8)
**Target: 1,500 A100 nodes**

### Rationale
- Critical for production inference
- Requires careful load balancing
- Rolling upgrade with traffic shifting

### Execution Plan
```bash
# Create A100 upgrade pools in stages
for zone in {a,b,c}; do
    gcloud container node-pools create a100-inference-v132-${zone} \
        --cluster=ml-cluster \
        --zone=us-central1-${zone} \
        --accelerator=type=nvidia-tesla-a100,count=2 \
        --machine-type=a2-highgpu-2g \
        --num-nodes=500 \
        --node-version=1.32 \
        --disk-size=500GB \
        --enable-autoscaling \
        --min-nodes=400 \
        --max-nodes=600
done

# Implement canary deployment strategy
kubectl apply -f - <<EOF
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: inference-service-upgrade
spec:
  strategy:
    canary:
      steps:
      - setWeight: 10
      - pause: {duration: 30m}
      - setWeight: 25
      - pause: {duration: 1h}
      - setWeight: 50
      - pause: {duration: 2h}
      - setWeight: 75
      - pause: {duration: 1h}
      - setWeight: 100
EOF
```

### Traffic Management
```yaml
# Istio VirtualService for gradual traffic shifting
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata:
  name: inference-traffic-split
spec:
  http:
  - match:
    - headers:
        canary:
          exact: "true"
    route:
    - destination:
        host: inference-service
        subset: v132
      weight: 100
  - route:
    - destination:
        host: inference-service
        subset: v131
      weight: 90
    - destination:
        host: inference-service
        subset: v132
      weight: 10
```

### Monitoring & Rollback Plan
- P95 latency < 150ms threshold
- Error rate < 0.1%
- Automated rollback triggers

## Phase 4: H100 Training Nodes (Days 9-14)
**Target: 2,000 H100 nodes**

### Rationale
- Highest value, most sensitive workloads
- Requires coordination with training schedules
- Checkpointing strategy essential

### Pre-Phase Preparation
```bash
# Implement training job checkpointing
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: checkpoint-enforcer
spec:
  template:
    spec:
      containers:
      - name: checkpoint-trigger
        image: training-checkpoint:latest
        command: ["/bin/bash"]
        args:
        - -c
        - |
          # Force checkpoint all running training jobs
          for job in $(kubectl get pods -l "workload=training,gpu=h100" -o name); do
            kubectl exec $job -- python -c "
            import signal
            import os
            os.kill(os.getpid(), signal.SIGUSR1)  # Trigger checkpoint
            "
          done
EOF
```

### Execution Plan
```bash
# Upgrade H100 nodes in small batches (100 nodes each)
# Coordinate with training team for maintenance windows

for batch in $(seq 1 20); do
    echo "Upgrading H100 batch ${batch}/20"
    
    # Select 100 nodes for upgrade
    NODES=$(kubectl get nodes -l "gpu-type=h100" \
        -o jsonpath='{.items[*].metadata.name}' | \
        tr ' ' '\n' | head -100)
    
    # Cordon nodes and wait for job completion
    for node in $NODES; do
        kubectl cordon $node
    done
    
    # Wait for training jobs to complete or checkpoint
    timeout 7200 kubectl wait --for=delete pods \
        -l "workload=training" \
        --field-selector spec.nodeName in ($NODES)
    
    # Perform upgrade
    gcloud container clusters upgrade ml-cluster \
        --node-pool=h100-training-${batch} \
        --cluster-version=1.32
    
    # Validate and uncordon
    kubectl wait --for=condition=Ready nodes $NODES --timeout=1800s
    kubectl uncordon $NODES
    
    # Extended stabilization period
    sleep 3600  # 1 hour between batches
done
```

### Training Job Protection
```yaml
apiVersion: v1
kind: Pod
spec:
  affinity:
    podAntiAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
      - labelSelector:
          matchExpressions:
          - key: upgrade-status
            operator: In
            values: ["in-progress"]
        topologyKey: kubernetes.io/hostname
```

## Phase 5: Control Plane & Final Validation (Day 15)

### Control Plane Upgrade
```bash
# Upgrade control plane during lowest usage window
gcloud container clusters upgrade ml-cluster \
    --master \
    --cluster-version=1.32 \
    --quiet
```

### Comprehensive Validation
```bash
#!/bin/bash
# Post-upgrade validation script

echo "=== Cluster Health Check ==="
kubectl get nodes | grep -v Ready && echo "Node issues detected!" || echo "All nodes ready"

echo "=== GPU Node Validation ==="
kubectl describe nodes -l "accelerator!=null" | grep -E "(nvidia.com/gpu|Allocatable)"

echo "=== Workload Health ==="
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

echo "=== Performance Baseline ==="
kubectl top nodes -l "gpu-type=h100" | head -10
kubectl top nodes -l "gpu-type=a100" | head -10

echo "=== Training Job Status ==="
kubectl get jobs -l "workload=training" -o custom-columns=NAME:.metadata.name,STATUS:.status.phase,DURATION:.status.duration

echo "=== Inference Service Health ==="
curl -s http://inference-service/health | jq '.status'
```

## Risk Mitigation Strategies

### 1. Backup & Recovery
```bash
# Automated cluster state backup
kubectl create backup cluster-pre-upgrade \
    --include-namespaces=* \
    --storage-location=gs://ml-cluster-backups/
```

### 2. Rollback Procedures
```bash
# Rapid rollback script
./rollback-nodepool.sh --pool=a100-inference --target-version=1.31
```

### 3. Circuit Breakers
- Automatic upgrade halt if error rates > 0.5%
- Training job failure threshold: 2 jobs
- Inference latency threshold: P95 > 200ms

## Success Metrics

### Technical Metrics
- Zero data loss
- <2% training job interruption
- <5% increase in inference latency during transition
- 100% node upgrade success rate

### Business Metrics
- Maintain 99.9% inference availability
- <4 hours total training downtime
- Zero customer-facing incidents

## Communication Plan

### Stakeholder Notifications
- **T-7 days**: Training teams (job scheduling coordination)
- **T-3 days**: Inference service owners (traffic preparation)
- **T-1 day**: All users (final maintenance windows)
- **Real-time**: Status page updates during each phase

### Escalation Matrix
- **L1**: Platform team (immediate response)
- **L2**: ML Engineering (training impact)
- **L3**: Site Reliability (business impact)

## Timeline Summary

| Phase | Days | Target | Risk Level | Rollback Time |
|-------|------|--------|------------|---------------|
| 1     | 1-2  | CPU Services (1,000) | Low | 30 min |
| 2     | 3-4  | T4 Dev (500) | Low | 1 hour |
| 3     | 5-8  | A100 Inference (1,500) | Medium | 2 hours |
| 4     | 9-14 | H100 Training (2,000) | High | 4 hours |
| 5     | 15   | Control Plane | Medium | 1 hour |

**Total Duration**: 15 days
**Business Impact**: Minimal with proper execution
**Success Probability**: 95%+ with comprehensive testing

This plan ensures training continuity while maintaining inference availability throughout the upgrade process.