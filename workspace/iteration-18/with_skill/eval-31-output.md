# GKE Upgrade Plan: Large-Scale LLM Training Cluster

## Cluster Context
- **512 H100 GPU nodes (A3 Mega, 8 GPUs each = 4,096 GPUs total)**
- **GPUDirect-TCPXO interconnect** 
- **Current: GKE 1.31 → Target: GKE 1.32**
- **Training runs: 2-3 weeks duration**
- **Cluster mode: Standard**

## Critical Constraints for AI Training Clusters

### GPUDirect-TCPXO Version Compatibility
✅ **Good news**: GPUDirect-TCPXO is supported on both GKE 1.31 and 1.32. However, you must verify the exact version requirements:
- Check that your current 1.31.x patch supports TCPXO for A3 Mega
- Confirm 1.32.x target version maintains TCPXO support
- **Test staging cluster first** - create a small A3 Mega node pool at target 1.32 version and verify TCPXO topology

### Multi-Week Training Protection Strategy

**Primary recommendation: Maintenance exclusions + staged upgrade approach**

## Phase 1: Immediate Protection (Before Next Training Run)

```bash
# Add "no minor or node upgrades" exclusion to block auto-upgrades during training
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "llm-training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# This allows CP security patches but blocks disruptive upgrades
```

## Phase 2: Control Plane Upgrade (Safe During Training)

The control plane can be upgraded without affecting running training jobs:

```bash
# Upgrade CP first - training continues uninterrupted
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.LATEST
```

**Why this is safe**: Regional control plane upgrades are non-disruptive. Training pods continue running on existing nodes. Only brief API unavailability (seconds) during each CP replica upgrade.

## Phase 3: Node Pool Upgrade Strategy (During Training Gap)

**Wait for training completion**, then upgrade nodes between training runs:

### Pre-Upgrade Validation
```bash
# Create small staging pool to test TCPXO compatibility
gcloud container node-pools create staging-h100-test \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --machine-type a3-megagpu-8g \
  --num-nodes 2 \
  --cluster-version 1.32.x-gke.LATEST \
  --placement-type COMPACT \
  --accelerator type=nvidia-h100-mega-80gb,count=8

# Deploy test workload and verify GPUDirect-TCPXO topology
kubectl apply -f tcpxo-test-job.yaml
# Verify: RDMA interfaces, GPU topology, inter-node bandwidth
```

### Node Pool Upgrade Configuration

For GPU pools with fixed reservations, **maxUnavailable is your primary lever**:

```bash
# Configure conservative GPU node pool upgrade
gcloud container node-pools update gpu-training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4

# Why maxSurge=0: H100 reservations typically have no surge capacity
# Why maxUnavailable=4: Conservative batch size for 512 nodes = ~128 batches
```

**Upgrade timing calculation**: 
- GKE upgrades ~20 nodes simultaneously regardless of settings
- 512 nodes ÷ 20 = ~26 batches minimum
- Each batch: ~10-15 minutes (drain + recreate + ready)
- **Total time: 4-7 hours** for full node pool

### Execute Node Pool Upgrade
```bash
# Only run this during training gap!
gcloud container node-pools upgrade gpu-training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.LATEST

# Monitor progress
watch 'kubectl get nodes -o wide | grep h100'
```

## Phase 4: Post-Upgrade Validation

### GPU Interconnect Verification
```bash
# Verify all nodes ready with correct version
kubectl get nodes -l accelerator=nvidia-h100-mega-80gb

# Test GPUDirect-TCPXO functionality
kubectl apply -f multi-node-gpu-test.yaml

# Check RDMA interfaces on upgraded nodes
kubectl debug node/NODE_NAME -it --image=busybox
# In debug container: check /sys/class/infiniband/
```

### Compact Placement Verification
```bash
# Verify nodes maintain physical co-location for RDMA
kubectl get nodes -o wide -l accelerator=nvidia-h100-mega-80gb
# Check that replacement nodes landed in same placement group
```

## Alternative: Blue-Green Strategy (If You Have 2x Capacity)

**Only if your reservation has 1,024+ H100s available:**

```bash
gcloud container node-pools update gpu-training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --strategy BLUE_GREEN \
  --node-pool-soak-duration 7200s \
  --standard-rollout-policy batch-node-count=20,batch-soak-duration=300s
```

**Advantage**: Zero training interruption - old pool serves while new pool provisions
**Disadvantage**: Requires 2x GPU capacity (1,024 H100s total during upgrade)

## Maintenance Schedule Recommendation

```bash
# Set maintenance window during typical training gaps
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-02-01T02:00:00Z" \
  --maintenance-window-duration 8h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"

# Use disruption intervals to prevent frequent upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-minor-version-disruption-interval 90d \
  --maintenance-patch-version-disruption-interval 30d
```

## Rollback Plan

If TCPXO breaks post-upgrade:
1. **Immediate**: Apply "no upgrades" exclusion to prevent further changes
2. **Create rollback node pool** at 1.31 with same TCPXO config
3. **Migrate training workload** to rollback pool
4. **Work with GKE support** for official CP rollback (if needed)

## Pre-Flight Checklist

```markdown
- [ ] Control plane upgraded to 1.32 (safe during training)
- [ ] Staging A3 Mega nodes tested at target 1.32 version
- [ ] GPUDirect-TCPXO topology verified on staging nodes
- [ ] Current training run completed and checkpointed
- [ ] Maintenance exclusion active to prevent auto-upgrades
- [ ] 8-hour weekend maintenance window scheduled
- [ ] Rollback node pool config prepared
- [ ] GPU reservation headroom confirmed (for surge) or maxUnavailable approach selected
```

## Key Success Factors

1. **Separate CP and node upgrades** - CP first (safe), nodes during gap
2. **Staging validation mandatory** - test TCPXO on target version
3. **Maintenance exclusions prevent disruption** during active training
4. **Conservative maxUnavailable** approach for fixed GPU reservations
5. **Plan 6-8 hours** for full node pool upgrade

This approach protects your multi-week training investment while safely modernizing the cluster infrastructure.