# GKE AI/ML Platform Upgrade Plan: 1.31 → 1.32

**Cluster:** Mixed AI/ML Platform (5,000 nodes)  
**Upgrade Path:** 1.31 → 1.32  
**Priority:** Training continuity > Inference availability > Dev/Services

---

## Executive Summary

This plan phases the upgrade across 4 distinct node pool types with different strategies optimized for each workload. Total estimated duration: 5-7 days with proper sequencing to minimize disruption to revenue-generating training and inference workloads.

## Phase 1: CPU Services (Day 1 - Low Risk)

**Target:** 1,000 CPU nodes running support services  
**Strategy:** Fast surge upgrade for rapid completion  
**Risk:** Low - services typically stateless and fault-tolerant

### Pre-upgrade Configuration
```bash
# Configure aggressive surge for CPU pools
gcloud container node-pools update cpu-services-pool \
  --cluster ml-platform \
  --zone us-central1-a \
  --max-surge-upgrade 20 \
  --max-unavailable-upgrade 0

# Set maintenance window during off-peak hours
gcloud container clusters update ml-platform \
  --zone us-central1-a \
  --maintenance-window-start 2024-01-15T02:00:00Z \
  --maintenance-window-end 2024-01-15T06:00:00Z \
  --maintenance-window-recurrence "FREQ=DAILY"
```

### Upgrade Commands
```bash
# Control plane first (required order)
gcloud container clusters upgrade ml-platform \
  --zone us-central1-a \
  --master \
  --cluster-version 1.32.0-gke.1200

# CPU node pool upgrade
gcloud container node-pools upgrade cpu-services-pool \
  --cluster ml-platform \
  --zone us-central1-a \
  --cluster-version 1.32.0-gke.1200
```

**Expected Duration:** 4-6 hours  
**Validation:** All services responding, no degraded performance

---

## Phase 2: T4 Development Nodes (Day 2 - Controlled Disruption)

**Target:** 500 T4 nodes for development/experimentation  
**Strategy:** Standard surge upgrade with moderate parallelism  
**Risk:** Medium - can pause dev work during upgrade window

### Configuration & Upgrade
```bash
# Moderate surge for T4 development pool
gcloud container node-pools update t4-dev-pool \
  --cluster ml-platform \
  --zone us-central1-a \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 0

# Upgrade T4 pool
gcloud container node-pools upgrade t4-dev-pool \
  --cluster ml-platform \
  --zone us-central1-a \
  --cluster-version 1.32.0-gke.1200
```

**Expected Duration:** 6-8 hours  
**Coordination:** Notify dev teams of 8-hour window for experiment interruption

---

## Phase 3: A100 Inference Nodes (Day 3-4 - High Availability Focus)

**Target:** 1,500 A100 nodes serving production inference  
**Strategy:** Autoscaled blue-green upgrade to minimize serving disruption  
**Risk:** High - revenue impact if inference capacity drops

### Critical Pre-checks
```bash
# Verify A100 reservation capacity for blue-green
gcloud compute reservations list --filter="name~a100"

# Check current inference load and scaling patterns
kubectl top nodes -l accelerator=nvidia-tesla-a100
```

### Blue-Green Strategy (Recommended)
```bash
# Configure autoscaled blue-green for minimal serving disruption
gcloud container node-pools update a100-inference-pool \
  --cluster ml-platform \
  --zone us-central1-a \
  --enable-autoscaling \
  --min-nodes 100 \
  --max-nodes 1500

# Initiate blue-green upgrade
gcloud container node-pools upgrade a100-inference-pool \
  --cluster ml-platform \
  --zone us-central1-a \
  --cluster-version 1.32.0-gke.1200 \
  --upgrade-strategy blue-green
```

### Alternative: GPU-Optimized Surge (If No Blue-Green Capacity)
```bash
# GPU pools typically have NO surge capacity - use maxUnavailable
gcloud container node-pools update a100-inference-pool \
  --cluster ml-platform \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 10

# Upgrade with controlled unavailability
gcloud container node-pools upgrade a100-inference-pool \
  --cluster ml-platform \
  --zone us-central1-a \
  --cluster-version 1.32.0-gke.1200
```

**Expected Duration:** 24-36 hours (1,500 nodes, ~20 parallel max)  
**Monitoring:** Continuous inference QPS and latency monitoring during upgrade

---

## Phase 4: H100 Training Nodes (Day 5-7 - Maximum Protection)

**Target:** 2,000 H100 nodes running multi-day training workloads  
**Strategy:** Maintenance exclusion + manual coordination with training schedule  
**Risk:** Critical - training interruption costs days/weeks of compute

### Training-First Approach

#### Option A: Maintenance Exclusion (Recommended)
```bash
# Block all upgrades during active training campaigns
gcloud container clusters update ml-platform \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-start-time 2024-01-15T00:00:00Z \
  --add-maintenance-exclusion-end-time 2024-01-31T23:59:59Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Coordinate with ML teams for training gaps
# Upgrade only when H100 pools are idle between training runs
```

#### Option B: Coordinated Cordon-and-Wait
```bash
# When training workloads complete, cordon H100 nodes
kubectl cordon -l cloud.google.com/gke-nodepool=h100-training-pool

# Wait for natural training job completion (no forced eviction)
# Then upgrade empty nodes
gcloud container node-pools update h100-training-pool \
  --cluster ml-platform \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 50  # Larger batches since nodes are empty

gcloud container node-pools upgrade h100-training-pool \
  --cluster ml-platform \
  --zone us-central1-a \
  --cluster-version 1.32.0-gke.1200
```

**Expected Duration:** 2-3 days (depends on training schedule alignment)  
**Coordination:** ML platform team schedules upgrade during natural training gaps

---

## GPU-Specific Considerations

### Driver Compatibility Validation
```bash
# Test GPU driver changes in staging first
# GKE 1.31 → 1.32 may change CUDA driver version
kubectl describe nodes -l accelerator=nvidia-tesla-h100 | grep cuda
```

**Critical:** CUDA version changes can break training frameworks. Test PyTorch/JAX/TensorFlow compatibility in dev environment first.

### Compact Placement Preservation
For multi-node training (NCCL, GPUDirect-TCPX):
```bash
# Verify replacement nodes maintain placement group topology
gcloud compute instances list --filter="zone:us-central1-a AND name~h100" \
  --format="table(name,zone,machineType,placement.group)"
```

### RDMA/High-Performance Networking
```bash
# Verify MTU and networking config survives upgrade
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.addresses[0].address}{"\n"}{end}'
```

---

## Risk Mitigation

### Training Workload Protection
- **Checkpointing:** Ensure all training jobs have recent checkpoints before Phase 4
- **PDB Configuration:** 
```bash
# Protect training pods from eviction
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
spec:
  minAvailable: 100%  # No disruption allowed during training
  selector:
    matchLabels:
      workload-type: training
```

### Inference SLA Protection
- **Gradual Rollout:** Blue-green strategy maintains serving capacity
- **Monitoring:** Track inference latency and error rates during A100 upgrade
- **Rollback Plan:** Keep blue pool available for 24h post-upgrade

### Resource Quotas
```bash
# Verify sufficient quota for surge/blue-green operations
gcloud compute project-info describe \
  --format="table(quotas[].metric:label=METRIC,quotas[].limit:label=LIMIT)" \
  --filter="quotas.metric:('NVIDIA_H100_GPUS', 'NVIDIA_A100_GPUS')"
```

---

## Monitoring & Validation

### Per-Phase Health Checks
```bash
# Node readiness by pool
kubectl get nodes -L cloud.google.com/gke-nodepool -o wide

# GPU utilization post-upgrade
kubectl describe nodes -l accelerator=nvidia-tesla-h100 | grep "Allocated resources" -A 10

# Training job continuity
kubectl get pods -l workload-type=training -o wide

# Inference endpoint health
curl -f https://ml-inference-endpoint/health
```

### Rollback Triggers
- **Training:** Any interruption to multi-day training runs
- **Inference:** >5% increase in p95 latency or >1% error rate increase
- **GPU Utilization:** <90% of expected GPU allocation post-upgrade

---

## Timeline Summary

| Phase | Workload | Duration | Risk Level | Strategy |
|-------|----------|----------|------------|----------|
| Day 1 | Control Plane + CPU Services | 6h | Low | Fast surge |
| Day 2 | T4 Development | 8h | Medium | Standard surge |
| Day 3-4 | A100 Inference | 24-36h | High | Blue-green |
| Day 5-7 | H100 Training | 48-72h | Critical | Exclusion + coordination |

**Total Fleet Upgrade:** 5-7 days with proper sequencing and risk controls.

This plan prioritizes your revenue-generating workloads (training continuity, inference availability) while leveraging GKE's native upgrade strategies optimized for each GPU workload type.