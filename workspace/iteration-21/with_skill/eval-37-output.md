# GKE AI/ML Fleet Upgrade Plan: 1.31 → 1.32

## Executive Summary

**Scope:** 5,000-node mixed AI/ML fleet upgrade prioritizing training continuity and inference availability  
**Timeline:** 3-4 weeks with careful sequencing to minimize disruption  
**Strategy:** Phase upgrades by workload criticality, GPU reservation constraints, and capacity requirements

## Fleet Architecture Analysis

| Pool Type | Nodes | Primary Workload | Upgrade Priority | Strategy |
|-----------|-------|------------------|------------------|----------|
| CPU services | 1,000 | APIs, controllers, monitoring | **Phase 1** (lowest risk) | Standard surge |
| T4 development | 500 | Dev/test workloads | **Phase 2** (test validation) | Standard surge |
| A100 inference | 1,500 | Production serving | **Phase 3** (critical uptime) | Autoscaled blue-green |
| H100 training | 2,000 | Multi-day training jobs | **Phase 4** (highest impact) | Manual coordination |

## Pre-Upgrade Preparation (Week 1)

### Cluster Configuration Audit
```bash
# Check current versions across all clusters
for cluster in training-cluster inference-cluster dev-cluster services-cluster; do
  echo "=== $cluster ==="
  gcloud container clusters describe $cluster \
    --zone us-central1-a \
    --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"
done

# Verify 1.32 availability in your release channel
gcloud container get-server-config --zone us-central1-a \
  --format="yaml(channels)"
```

### GPU Driver Compatibility Validation
```bash
# CRITICAL: Test 1.32 + driver combination in staging before production
# Create test node pool with target version
gcloud container node-pools create test-h100-132 \
  --cluster training-cluster \
  --zone us-central1-a \
  --machine-type a3-highgpu-8g \
  --num-nodes 2 \
  --cluster-version 1.32.x-gke.xxx

# Deploy representative training/inference workloads to validate CUDA compatibility
# Test model loading, GPU utilization, inter-node communication (NCCL/RDMA)
```

### Maintenance Window Configuration
```bash
# Set maintenance windows per workload type
# Services: Business hours acceptable (faster resolution if issues)
gcloud container clusters update services-cluster \
  --zone us-central1-a \
  --maintenance-window-start "2024-12-16T14:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=MO"

# GPU clusters: Off-peak hours only
gcloud container clusters update training-cluster \
  --zone us-central1-a \
  --maintenance-window-start "2024-12-16T02:00:00Z" \
  --maintenance-window-duration 8h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### Training Job Protection Setup
```bash
# Block auto-upgrades during active training campaigns
gcloud container clusters update training-cluster \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Phase 1: CPU Services Clusters (Week 1, Days 5-7)

**Objective:** Validate 1.32 stability with lowest-risk workloads  
**Duration:** 2-3 days  
**Risk:** Low (stateless services, no GPU dependencies)

### Strategy: Standard Surge Upgrade

```bash
# Configure surge settings for CPU pools
gcloud container node-pools update default-pool \
  --cluster services-cluster \
  --zone us-central1-a \
  --max-surge-upgrade 50 \
  --max-unavailable-upgrade 0  # Zero downtime for services

# Control plane upgrade
gcloud container clusters upgrade services-cluster \
  --zone us-central1-a \
  --master \
  --cluster-version 1.32.x-gke.xxx

# Node pool upgrade
gcloud container node-pools upgrade default-pool \
  --cluster services-cluster \
  --zone us-central1-a \
  --cluster-version 1.32.x-gke.xxx
```

### Validation Checklist
- [ ] Monitoring/observability stack operational (Prometheus, Grafana, Cloud Monitoring)
- [ ] CI/CD pipelines functional
- [ ] API gateways responding with normal latency
- [ ] Database connections stable
- [ ] No deprecated API warnings in logs: `kubectl get --raw /metrics | grep deprecated`

## Phase 2: T4 Development Clusters (Week 2, Days 1-3)

**Objective:** Validate GPU driver compatibility and workload behavior on 1.32  
**Duration:** 2-3 days  
**Risk:** Low (dev workloads, interruptible)

### Strategy: Standard Surge with GPU Considerations

```bash
# T4 pools typically have some surge capacity available
gcloud container node-pools update t4-dev-pool \
  --cluster dev-cluster \
  --zone us-central1-a \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 0

# Upgrade control plane first
gcloud container clusters upgrade dev-cluster \
  --zone us-central1-a \
  --master \
  --cluster-version 1.32.x-gke.xxx

# Node pool upgrade
gcloud container node-pools upgrade t4-dev-pool \
  --cluster dev-cluster \
  --zone us-central1-a \
  --cluster-version 1.32.x-gke.xxx
```

### Critical GPU Validation
```bash
# Verify GPU driver installation post-upgrade
kubectl get nodes -l accelerator=nvidia-tesla-t4 \
  -o custom-columns=NAME:.metadata.name,GPU:.status.allocatable.'nvidia\.com/gpu'

# Test model deployment
kubectl run gpu-test --image=nvidia/cuda:12.0-runtime-ubuntu20.04 \
  --limits=nvidia.com/gpu=1 \
  --rm -it --restart=Never -- nvidia-smi

# Validate CUDA version compatibility with your models
```

### Development Team Coordination
- [ ] Notify dev teams of upgrade window
- [ ] Pause CI/CD GPU pipelines during node upgrades
- [ ] Test representative ML workloads: training, inference, Jupyter notebooks
- [ ] Verify GPU sharing (if using MIG or time-slicing)

## Phase 3: A100 Inference Clusters (Week 2, Days 4-7)

**Objective:** Upgrade production inference with minimal service disruption  
**Duration:** 3-4 days  
**Risk:** High (production traffic, SLA requirements)

### Strategy: Autoscaled Blue-Green for Zero-Downtime Inference

**Why autoscaled blue-green for inference:**
- Eliminates inference latency spikes from pod restarts
- GPU VMs don't support live migration — every upgrade requires pod restart
- Keeps old pool serving while new pool warms up
- Cost-efficient (scales down old pool as new pool scales up)

```bash
# Enable autoscaling on inference pools
gcloud container node-pools update a100-inference-pool \
  --cluster inference-cluster \
  --zone us-central1-a \
  --enable-autoscaling \
  --total-min-nodes 100 \
  --total-max-nodes 1500

# Configure autoscaled blue-green upgrade
gcloud container node-pools update a100-inference-pool \
  --cluster inference-cluster \
  --zone us-central1-a \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

### Phased Inference Upgrade

**Step 1: Control Plane Upgrade**
```bash
gcloud container clusters upgrade inference-cluster \
  --zone us-central1-a \
  --master \
  --cluster-version 1.32.x-gke.xxx
```

**Step 2: Node Pool Upgrade with Soak Period**
```bash
# Initiate autoscaled blue-green upgrade
gcloud container node-pools upgrade a100-inference-pool \
  --cluster inference-cluster \
  --zone us-central1-a \
  --cluster-version 1.32.x-gke.xxx

# Monitor blue-green phases
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=a100-inference-pool -o wide'
```

### Production Validation During Soak
- [ ] Model serving latency within SLA (p95 < baseline + 10%)
- [ ] Inference throughput matches pre-upgrade levels
- [ ] GPU utilization normal across new nodes
- [ ] No CUDA errors in application logs
- [ ] Load balancer health checks passing
- [ ] Auto-scaling behavior normal under load

### Rollback Plan (if needed during soak)
```bash
# Rollback during blue-green soak period
gcloud container node-pools rollback a100-inference-pool \
  --cluster inference-cluster \
  --zone us-central1-a
```

## Phase 4: H100 Training Clusters (Week 3-4)

**Objective:** Upgrade training infrastructure without disrupting multi-day jobs  
**Duration:** 7-10 days with training campaign coordination  
**Risk:** Highest (expensive compute, long-running jobs, RDMA topology)

### Pre-Upgrade Training Coordination

**Step 1: Training Campaign Assessment**
```bash
# Identify running training jobs and estimated completion times
kubectl get pods -n training \
  -o custom-columns=NAME:.metadata.name,NODE:.spec.nodeName,RUNTIME:.status.startTime,STATE:.status.phase

# Check for multi-node jobs with RDMA/NCCL dependencies
kubectl get pods -n training -l job-type=distributed \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.nodeSelector}{"\n"}{end}'
```

**Step 2: Checkpoint and Pause Strategy**
- [ ] Coordinate with ML teams to checkpoint long-running jobs
- [ ] Schedule upgrade during natural gap between training campaigns
- [ ] Verify all training frameworks support checkpointing (PyTorch, JAX, TensorFlow)
- [ ] Pause job submission 2 hours before upgrade window

### H100 Upgrade Strategy: Manual Pool Replacement

**Why manual strategy for H100 training:**
- Fixed GPU reservations with no surge capacity
- Multi-day jobs cannot tolerate eviction
- RDMA topology must be preserved
- Need maximum control over timing

```bash
# Step 1: Control plane upgrade (safe, no node impact)
gcloud container clusters upgrade training-cluster \
  --zone us-central1-a \
  --master \
  --cluster-version 1.32.x-gke.xxx

# Step 2: Create replacement node pool with 1.32
gcloud container node-pools create h100-training-132 \
  --cluster training-cluster \
  --zone us-central1-a \
  --machine-type a3-highgpu-8g \
  --num-nodes 2000 \
  --cluster-version 1.32.x-gke.xxx \
  --reservation-affinity=TRAINING_RESERVATION \
  --placement-type=COMPACT  # Preserve RDMA topology
```

**Step 3: Validate New Pool Before Migration**
```bash
# Deploy test training job on new nodes
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: nccl-test-132
  namespace: training
spec:
  template:
    spec:
      nodeSelector:
        cloud.google.com/gke-nodepool: h100-training-132
      containers:
      - name: nccl-test
        image: nvcr.io/nvidia/pytorch:23.10-py3
        command: ["python", "-m", "torch.distributed.run", "--nproc_per_node=8", "nccl_test.py"]
        resources:
          limits:
            nvidia.com/gpu: 8
EOF

# Verify RDMA connectivity and NCCL performance
kubectl logs -n training job/nccl-test-132
```

**Step 4: Controlled Migration**
```bash
# Cordon old H100 pool
kubectl cordon -l cloud.google.com/gke-nodepool=h100-training-pool

# Wait for natural job completion (monitor daily)
watch 'kubectl get pods -n training --field-selector=status.phase=Running | wc -l'

# When old pool is empty, delete it
gcloud container node-pools delete h100-training-pool \
  --cluster training-cluster \
  --zone us-central1-a
```

### Training Workload Validation Post-Upgrade
- [ ] NCCL all-reduce performance matches baseline
- [ ] Multi-node job scheduling working (placement groups intact)
- [ ] GPU memory and compute utilization normal
- [ ] Checkpoint/restore functionality working
- [ ] No CUDA version conflicts with training frameworks
- [ ] InfiniBand/RDMA topology preserved (if applicable)

## Multi-Cluster Fleet Monitoring

### Upgrade Progress Dashboard
```bash
# Create monitoring query for upgrade status across fleet
# Monitor via Cloud Monitoring or Prometheus
gcloud logging read '
resource.type="gke_cluster"
protoPayload.metadata.operationType="UPGRADE_NODES"
' --limit=50 --format=json
```

### Health Validation Script
```bash
#!/bin/bash
# fleet-health-check.sh
CLUSTERS=("services-cluster" "dev-cluster" "inference-cluster" "training-cluster")
ZONE="us-central1-a"

for cluster in "${CLUSTERS[@]}"; do
    echo "=== $cluster Health Check ==="
    
    # Version status
    gcloud container clusters describe $cluster --zone $ZONE \
        --format="value(currentMasterVersion)"
    
    # Node readiness
    kubectl get nodes --no-headers | grep -v Ready | wc -l
    
    # Pod health
    kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded | wc -l
    
    echo ""
done
```

## Risk Mitigation and Rollback Plans

### Immediate Rollback Triggers
- GPU workload failure rate > 5%
- Inference latency increase > 25%
- Training job startup failures
- CUDA compatibility errors
- RDMA/NCCL performance degradation > 15%

### Rollback Procedures by Phase

**Phase 1-2 (CPU/T4): Standard Rollback**
```bash
# Create new pool at 1.31, migrate workloads
gcloud container node-pools create rollback-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.xxx
```

**Phase 3 (A100): Blue-Green Rollback**
```bash
# During soak period only
gcloud container node-pools rollback a100-inference-pool \
  --cluster inference-cluster \
  --zone us-central1-a
```

**Phase 4 (H100): Pool Swap Rollback**
- Keep old pool available during migration
- Re-cordon new pool, uncordon old pool if issues arise
- Full rollback requires recreating 1.31 pool (most expensive)

## Timeline Summary

| Week | Phase | Workload | Duration | Risk Level |
|------|--------|----------|----------|------------|
| 1 | Prep + Phase 1 | CPU services | 5-7 days | Low |
| 2 | Phase 2 + 3 start | T4 dev + A100 inference | 7 days | Medium |
| 3 | Phase 3 complete + Phase 4 start | A100 finish + H100 prep | 7 days | High |
| 4 | Phase 4 complete | H100 training complete | 7 days | Highest |

## Success Metrics

### Technical KPIs
- Zero unplanned training job terminations
- Inference SLA maintained (p95 latency within 10% of baseline)
- GPU utilization maintained at >85% for training pools
- No CUDA compatibility regressions
- Upgrade completion within 4-week