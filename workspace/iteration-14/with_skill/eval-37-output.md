# GKE 1.31→1.32 Upgrade Plan: Mixed AI/ML Platform (5,000 nodes)

## Executive Summary

**Scope:** Upgrade 5,000-node mixed AI/ML platform from GKE 1.31→1.32  
**Priority:** Minimize training disruption, maintain inference availability  
**Duration:** 3-4 weeks with structured rollout phases  
**Risk Level:** High (large GPU fleet, version jump, training continuity)

## Fleet Architecture Context

| Node Type | Count | Primary Use | Upgrade Priority | Strategy |
|-----------|-------|-------------|------------------|----------|
| **H100** | 2,000 | Training (multi-day jobs) | **LAST** | Manual coordination with training schedules |
| **A100** | 1,500 | Inference (serving) | **3rd** | Rolling with capacity maintenance |
| **T4** | 500 | Development/testing | **1st** | Fast validation of 1.32 compatibility |
| **CPU** | 1,000 | Services/orchestration | **2nd** | Standard rolling upgrade |

## Phase 1: Pre-Upgrade Preparation (Week 1)

### Version Compatibility Assessment

**Critical checks for AI workloads:**
```bash
# Verify 1.32 GPU driver compatibility
gcloud container get-server-config --zone=ZONE \
  --format="yaml(channels.REGULAR.validNodeVersions)" | grep "1.32"

# Check current GPU driver versions
kubectl get nodes -l cloud.google.com/gke-accelerator=nvidia-tesla-h100 \
  -o custom-columns="NAME:.metadata.name,DRIVER:.status.nodeInfo.kernelVersion"
```

**GKE 1.32 GPU implications:**
- NVIDIA driver: Updates from 535.xx → 550.xx series (CUDA 12.4)
- **Risk:** PyTorch/JAX/TensorFlow compatibility with new CUDA version
- **Mitigation:** Test in T4 dev pools first

### Training Campaign Coordination

**Map current training workloads:**
```bash
# Identify long-running training jobs (>24h uptime)
kubectl get pods -A --field-selector=status.phase=Running \
  -o custom-columns="NAME:.metadata.name,NAMESPACE:.metadata.namespace,NODE:.spec.nodeName,AGE:.status.startTime" \
  | grep -E "(h100|H100)" | awk '$4 ~ /[0-9]+d/'
```

**Training freeze coordination:**
- **H100 pools:** Implement "no minor or node upgrades" maintenance exclusion
- **Duration:** Through completion of current training runs + upgrade window
- **Communication:** Alert ML teams of upcoming maintenance windows

```bash
# Block H100 pool upgrades during active training
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-start-time "2024-MM-DDTHH:MM:SSZ" \
  --add-maintenance-exclusion-end-time "2024-MM-DDTHH:MM:SSZ" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### Infrastructure Readiness

**GPU reservation verification:**
```bash
# Check reservation headroom for each GPU type
gcloud compute reservations describe h100-reservation --zone=ZONE
gcloud compute reservations describe a100-reservation --zone=ZONE
gcloud compute reservations describe t4-reservation --zone=ZONE
```

**Key finding:** GPU pools with fixed reservations have **NO surge capacity**  
**Implication:** Must use `maxSurge=0, maxUnavailable=N` strategy

## Phase 2: T4 Development Pools (Week 1, Days 4-5)

**Rationale:** Lowest risk, validates 1.32 GPU compatibility for entire fleet

### T4 Pool Upgrade Strategy
```bash
# Configure T4 pools for aggressive upgrade (lowest risk)
gcloud container node-pools update t4-dev-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4

# Control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.X-gke.XXXX

# T4 nodes (500 nodes, maxUnavailable=4 = ~125 batches)
gcloud container node-pools upgrade t4-dev-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.XXXX
```

**Expected duration:** 2-3 days (500 nodes ÷ 4 parallel ÷ 20 batch limit × 15min/node)

### Critical Validation Tests
```bash
# GPU driver post-upgrade
kubectl get nodes -l cloud.google.com/gke-accelerator=nvidia-tesla-t4 \
  -o custom-columns="NAME:.metadata.name,DRIVER:.status.nodeInfo.kernelVersion"

# CUDA compatibility test job
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: cuda-validation-t4
spec:
  template:
    spec:
      containers:
      - name: cuda-test
        image: nvidia/cuda:12.4-runtime-ubuntu20.04
        command: ["nvidia-smi", "--query-gpu=driver_version,cuda_version", "--format=csv"]
        resources:
          limits:
            nvidia.com/gpu: 1
      restartPolicy: Never
      nodeSelector:
        cloud.google.com/gke-accelerator: nvidia-tesla-t4
EOF
```

**Success criteria:**
- CUDA 12.4 accessible
- PyTorch/JAX test containers start successfully
- T4 development workloads resume normally

**Rollback trigger:** If CUDA/framework compatibility fails

## Phase 3: CPU Service Pools (Week 2)

**Rationale:** Support services must be stable before GPU inference upgrades

### CPU Pool Upgrade Strategy
```bash
# Configure conservative surge for service continuity
gcloud container node-pools update cpu-services-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# Upgrade (1,000 nodes, maxSurge=2 = ~500 batches)
gcloud container node-pools upgrade cpu-services-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.XXXX
```

**Expected duration:** 4-5 days  
**Risk mitigation:** Zero-downtime rolling replacement with PDB protection

### Service Health Validation
```bash
# Critical service health checks
kubectl get deployments -n ml-platform -o wide
kubectl get ingress -A
kubectl get services -A --field-selector spec.type=LoadBalancer

# Monitor service SLAs during upgrade
# Error rate < baseline + 0.5%
# P95 latency < baseline + 50ms
```

## Phase 4: A100 Inference Pools (Week 2-3)

**Rationale:** Inference must maintain availability; requires careful capacity management

### A100 Inference Strategy: Autoscaled Blue-Green

**Why autoscaled blue-green for inference:**
- Maintains serving capacity throughout upgrade
- No surge GPU quota required (cost-efficient scaling)
- Respects graceful termination for inference requests

```bash
# Configure A100 inference pools for autoscaled blue-green
gcloud container node-pools update a100-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 100 \
  --total-max-nodes 1500 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Upgrade with autoscaled blue-green
gcloud container node-pools upgrade a100-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.XXXX
```

**Capacity transition:** Green pool scales up (25% initial → 100%), blue pool scales down  
**Expected duration:** 5-7 days (1,500 nodes with careful scaling)

### Inference Availability Monitoring
```bash
# Monitor serving capacity during transition
kubectl get nodes -l cloud.google.com/gke-accelerator=nvidia-tesla-a100 \
  -o custom-columns="NAME:.metadata.name,STATUS:.status.conditions[-1].type,POOL:.metadata.labels.cloud\.google\.com/gke-nodepool"

# Track inference request success rates
# SLA: <1% error rate increase, <200ms P95 latency increase
```

## Phase 5: H100 Training Pools (Week 3-4)

**Rationale:** Highest risk due to multi-day training jobs; requires precise coordination

### Pre-Training Pool Upgrade Coordination

**Training job checkpoint coordination:**
```bash
# Identify active training jobs
kubectl get pods -A -l workload-type=training \
  --field-selector=status.phase=Running \
  -o custom-columns="NAME:.metadata.name,NAMESPACE:.metadata.namespace,AGE:.status.startTime,NODE:.spec.nodeName"

# Coordinate with ML teams for natural training breaks
# Target upgrade window: Between training campaigns
```

### H100 Strategy: Manual Blue-Green with Parallel Host Maintenance

**Why manual blue-green for H100:**
- Training jobs are 2-7 days long (exceed GKE's 1-hour PDB timeout)
- Requires RDMA/GPUDirect topology preservation
- Needs controlled timing aligned with training schedules

```bash
# Step 1: Create new H100 pool at 1.32 (reserve capacity first)
gcloud container node-pools create h100-training-v132 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --machine-type a3-highgpu-8g \
  --num-nodes 0 \
  --min-nodes 0 \
  --max-nodes 2000 \
  --enable-autoscaling \
  --cluster-version 1.32.X-gke.XXXX \
  --placement-type COMPACT \
  --reservation-affinity consume-reservation \
  --reservation h100-reservation

# Step 2: Scale up new pool ONLY when training completes
# Step 3: Drain old pool gracefully
kubectl cordon -l cloud.google.com/gke-nodepool=h100-training-v131
# Wait for natural training completion - NO force eviction

# Step 4: Delete old pool
gcloud container node-pools delete h100-training-v131 \
  --cluster CLUSTER_NAME \
  --zone ZONE
```

### Training Validation Protocol

**GPUDirect/RDMA connectivity test:**
```bash
# Deploy NCCL bandwidth test across new H100 nodes
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: nccl-test-h100-v132
spec:
  parallelism: 16  # 8 nodes × 2 pods = 16 H100s
  template:
    spec:
      containers:
      - name: nccl-test
        image: nvcr.io/nvidia/pytorch:24.XX-py3
        command: ["python", "-m", "torch.distributed.run", "--nproc_per_node=8", "nccl_test.py"]
        resources:
          limits:
            nvidia.com/gpu: 8
      nodeSelector:
        cloud.google.com/gke-nodepool: h100-training-v132
EOF
```

**Success criteria:**
- NCCL bandwidth >1.5TB/s for H100 NVLink
- Compact placement maintained (same physical rack)
- PyTorch distributed training functional

## Maintenance Windows & Exclusions

### Per-Phase Windows

```bash
# T4 Dev: Aggressive window (48-hour)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-MM-DDTHH:MM:SSZ" \
  --maintenance-window-end "2024-MM-DDTHH:MM:SSZ" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA,SU"

# H100 Training: Protected until manual intervention
# Use "no minor or node upgrades" exclusion until Step 2 of H100 upgrade
```

### Training Protection Exclusions

```bash
# Block auto-upgrades on H100 until coordinated maintenance
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "h100-training-protection" \
  --add-maintenance-exclusion-start-time "2024-MM-DDTHH:MM:SSZ" \
  --add-maintenance-exclusion-until-end-of-support \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

## Risk Mitigation & Rollback

### GPU-Specific Rollback Challenges

**Control plane:** 1.32→1.31 minor downgrade requires GKE support  
**Node pools:** Cannot downgrade in-place; requires new pool creation

**Per-pool rollback strategy:**
1. **T4/CPU:** Create new pool at 1.31, migrate workloads, delete 1.32 pool
2. **A100 inference:** Autoscaling supports quick pool swap with minimal downtime
3. **H100 training:** Most complex — requires waiting for training completion before pool swap

### Rollback Triggers

- CUDA compatibility failure (PyTorch/JAX won't start)
- >5% inference error rate increase
- Training job startup failures on new nodes
- RDMA/GPUDirect bandwidth degradation >20%

## Success Metrics & Validation

### Training Continuity (H100)
- Zero training job failures due to upgrade
- NCCL bandwidth maintained within 5% of baseline
- Training throughput (samples/second) within 10% of baseline

### Inference Availability (A100)
- <1% error rate increase during upgrade window
- <200ms P95 latency increase
- Zero serving downtime

### Development Velocity (T4)
- Experiment queues resume <2 hours post-upgrade
- CUDA 12.4 compatibility confirmed

## Timeline Summary

| Week | Phase | Nodes | Duration | Risk | Validation |
|------|-------|-------|----------|------|------------|
| **1** | Prep + T4 | 500 | 3 days | Low | CUDA compatibility |
| **2** | CPU Services | 1,000 | 5 days | Medium | Service SLAs |
| **2-3** | A100 Inference | 1,500 | 7 days | Medium | Serving availability |
| **3-4** | H100 Training | 2,000 | 7-14 days | High | Training continuity |

**Total duration:** 3-4 weeks depending on training campaign coordination  
**Success criteria:** Zero training disruption, <1% inference impact, full fleet on 1.32

**Next actions:**
1. Coordinate with ML teams on training schedules
2. Verify GPU reservations have adequate capacity for blue-green transitions
3. Test CUDA 12.4 compatibility in T4 staging environment
4. Set up enhanced monitoring for inference SLAs during A100 upgrade