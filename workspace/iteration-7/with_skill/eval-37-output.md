# GKE AI/ML Fleet Upgrade Plan: 1.31 → 1.32

**Fleet Overview:** 5,000 nodes across mixed GPU/CPU workloads  
**Priority:** Training continuity > Inference availability > Development > Services  
**Strategy:** Phased upgrade with maintenance exclusions protecting active training

## Phase Overview

| Phase | Node Pools | Strategy | Duration | Training Impact |
|-------|-----------|----------|----------|-----------------|
| **Phase 1** | CPU services (1,000 nodes) | Surge upgrade | 2-3 days | None |
| **Phase 2** | T4 development (500 nodes) | Surge upgrade | 1-2 days | None |
| **Phase 3** | A100 inference (1,500 nodes) | Blue-green upgrade | 3-5 days | Managed degradation |
| **Phase 4** | H100 training (2,000 nodes) | Coordinated maintenance window | 7-14 days | Planned pause |

**Total timeline:** 4-6 weeks with training coordination

## Pre-Upgrade Setup

### 1. Training Protection (Critical)
```bash
# Apply "no minor or node upgrades" exclusion to H100 training pools
gcloud container clusters update AI_CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-start-time "2024-MM-DDTHH:MM:SSZ" \
  --add-maintenance-exclusion-end-time "2024-MM-DDTHH:MM:SSZ" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

This blocks H100 node pool upgrades while allowing control plane security patches during active training campaigns.

### 2. Maintenance Windows
```bash
# Configure maintenance windows for each phase
gcloud container clusters update AI_CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-MM-DDTTHH:MM:SSZ" \
  --maintenance-window-end "2024-MM-DDTTHH:MM:SSZ" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA,SU"
```

### 3. Control Plane Upgrade (All Clusters)
Upgrade control plane first across all clusters. This is non-disruptive and establishes the foundation for node upgrades.

```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.X-gke.LATEST
```

## Phase 1: CPU Services (1,000 nodes)
**Timeline:** Week 1  
**Impact:** Minimal - services have redundancy and fast restart

### Strategy: Aggressive Surge
```bash
# Configure high surge for fast completion
gcloud container node-pools update cpu-services-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 10 \
  --max-unavailable-upgrade 0

# Upgrade
gcloud container node-pools upgrade cpu-services-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.LATEST
```

**Why aggressive surge:** CPU nodes are cheap, services restart quickly, and this reduces overall fleet upgrade time.

### Validation
```bash
kubectl get pods -n default -o wide | grep cpu-services
curl -f http://SERVICE_ENDPOINTS/health
```

## Phase 2: T4 Development (500 nodes)
**Timeline:** Week 2  
**Impact:** Minimal - development workloads are interruptible

### Strategy: Moderate Surge
```bash
# T4 nodes have better surge availability than H100/A100
gcloud container node-pools update t4-dev-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade t4-dev-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.LATEST
```

### Validation
```bash
kubectl get nodes -l cloud.google.com/gke-nodepool=t4-dev-pool
nvidia-smi # Verify GPU driver compatibility on upgraded nodes
```

## Phase 3: A100 Inference (1,500 nodes)
**Timeline:** Week 3-4  
**Impact:** Managed degradation with capacity planning

### Strategy: Auto-scale Blue-Green Upgrade
A100 inference pools likely have fixed reservations with no surge capacity. Blue-green minimizes availability gaps and provides instant rollback.

```bash
# Use GKE's native blue-green upgrade
gcloud container node-pools update a100-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --enable-blue-green-update \
  --blue-green-update-node-pool-soak-duration 2h

gcloud container node-pools upgrade a100-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.LATEST
```

### Inference-Specific Considerations
- **Traffic management:** Configure load balancers to gracefully shift traffic away from draining nodes
- **Model loading time:** A100 inference pods may take 5-10 minutes to load large models. Factor this into the soak duration
- **Reservation coordination:** Verify A100 reservations can support the temporary double capacity during blue-green transition

### Monitoring During Upgrade
```bash
# Watch inference latency and success rates
kubectl get pods -l app=inference -o wide
curl -f http://INFERENCE_ENDPOINTS/metrics
```

## Phase 4: H100 Training (2,000 nodes)
**Timeline:** Week 5-6 (coordinated with training schedule)  
**Impact:** Planned training pause - coordinate with ML teams

### Pre-Phase 4: Training Coordination
1. **Schedule training pause:** Coordinate 1-2 week window with ML teams between major training runs
2. **Checkpoint verification:** Ensure all active training jobs have recent checkpoints
3. **Remove maintenance exclusion:** Only after confirming training pause

```bash
# Remove training protection exclusion
gcloud container clusters update AI_CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "training-protection"
```

### Strategy: Conservative Unavailable Mode
H100 nodes are scarce and expensive. Use `maxUnavailable` to avoid needing surge capacity.

```bash
# Conservative drain-first approach for H100 pools
gcloud container node-pools update h100-training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2

gcloud container node-pools upgrade h100-training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.LATEST
```

**Why `maxUnavailable=2`:** Balances upgrade speed with conservative resource usage. H100 reservations typically can't support surge, and `maxUnavailable` is the primary lever for GPU pools.

### H100-Specific Validation
```bash
# Verify GPU driver and CUDA compatibility
kubectl debug node/H100_NODE_NAME -it --image=nvidia/cuda:12.2-runtime-ubuntu20.04 -- nvidia-smi

# Check GPUDirect-TCPX functionality (if used)
kubectl get pods -l training-type=multi-node -o wide
# Verify pods scheduled on upgraded nodes can still form TCPX mesh
```

### Training Resumption
After Phase 4 completes:
```bash
# Verify training job can resume from checkpoint
kubectl apply -f training-job-resume.yaml
kubectl logs -f training-job-pod | grep "Resuming from checkpoint"
```

## Cross-Phase Monitoring

### Fleet-Wide Health Dashboard
Monitor these metrics throughout all phases:

```bash
# Node version distribution
kubectl get nodes -o json | \
  jq -r '.items[] | [.metadata.labels["kubernetes.io/arch"], .status.nodeInfo.kubeletVersion] | @tsv' | \
  sort | uniq -c

# GPU utilization across pools
kubectl get nodes -l accelerator=nvidia-tesla-h100 -o name | \
  xargs -I {} kubectl describe {} | grep -A 10 "Allocated resources"

# Training job health
kubectl get pods -l workload-type=training --field-selector=status.phase=Running
```

### Success Criteria by Phase
- **Phase 1-2:** Zero service degradation, <5min restart times
- **Phase 3:** <20% inference capacity reduction during transition, <10min model load times
- **Phase 4:** Training jobs resume successfully from checkpoints post-upgrade

## Rollback Strategy

### Per-Phase Rollback
- **Phase 1-2:** Create new CPU/T4 pools at 1.31, migrate, delete upgraded pools
- **Phase 3:** Blue-green upgrade provides instant rollback during 2h soak period
- **Phase 4:** Recreate H100 pool at 1.31 (most disruptive - avoid if possible)

### Emergency Brake
If critical issues emerge:
```bash
# Re-apply training protection immediately
gcloud container clusters update AI_CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "emergency-freeze" \
  --add-maintenance-exclusion-start-time "NOW" \
  --add-maintenance-exclusion-end-time "NOW+30days" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Risk Mitigation

### GPU Driver Compatibility
GKE 1.32 may ship with different CUDA drivers than 1.31. Test in a staging environment first:
```bash
# Create staging cluster at 1.32 with same GPU types
# Verify training frameworks (PyTorch, JAX, TensorFlow) work with new CUDA version
```

### Reservation and Quota Management
- **H100/A100 surge capacity:** Confirm with Google Cloud that your reservations support temporary capacity increases for blue-green upgrades
- **Regional capacity:** Verify target regions have adequate GPU inventory during upgrade windows

### Training Data Pipeline
- Ensure training data pipelines can handle node restarts gracefully
- Verify distributed training can recover from partial cluster restarts
- Test that checkpointing frequency is adequate for your RTO requirements

This phased approach minimizes business impact while systematically upgrading your entire AI/ML fleet. The key insight is using maintenance exclusions to decouple training schedules from infrastructure maintenance, then coordinating the H100 upgrade with planned training gaps.