# Large-Scale GKE Upgrade Plan (3,000+ Node Cluster)

Your cluster is hitting GKE's inherent upgrade parallelism limits. At 3,000 nodes with an 8-hour window, you need a fundamentally different approach than standard clusters.

## Core Problem Analysis

**GKE's upgrade constraints at your scale:**
- **Maximum parallelism:** ~20 nodes simultaneously per node pool (roadmap: increasing to 100)
- **Time calculation:** 3,000 nodes ÷ 20 = 150+ batches minimum
- **Duration estimate:** 150 batches × ~10 min/batch = 25+ hours (not 8 hours)
- **Window mismatch:** Your 8-hour Saturday window can't accommodate the actual upgrade duration

## Recommended Strategy: Staggered Pool Upgrades

Break the upgrade into manageable phases across multiple maintenance windows:

### Phase 1: CPU Pools (Week 1)
```bash
# Upgrade CPU pools first - less risk, no capacity constraints
# Estimated time: 4 CPU pools × 6-8 hours = can fit in 2 weekends

# Weekend 1: CPU pools 1-2
gcloud container node-pools upgrade CPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION

gcloud container node-pools upgrade CPU_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

### Phase 2: GPU Pools (Week 2-3)
```bash
# GPU pools require special handling due to capacity constraints
# Do these during training job gaps

# For GPU pools with fixed reservations (most common scenario):
gcloud container node-pools update A100_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2

# Then upgrade:
gcloud container node-pools upgrade A100_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

## GPU Pool Strategy Adjustments

**For your GPU pools, use drain-first strategy:**
- **A100/H100 pools:** `maxSurge=0, maxUnavailable=2-4` (assume fixed reservations, no surge capacity)
- **L4/T4 pools:** May have surge capacity - verify first: `gcloud compute reservations list`
- **Key insight:** `maxUnavailable` is your PRIMARY lever for GPU pools, not `maxSurge`

**GPU upgrade duration estimate:**
- 500-node A100 pool ÷ 20 parallelism = 25 batches × 15 min = ~6-7 hours per pool
- Schedule GPU pools on separate weekends to avoid capacity conflicts

## Extended Maintenance Window Options

**Option 1: Extend window duration**
```bash
# Increase to 16-hour window (Friday 10pm - Saturday 2pm)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-05T22:00:00Z" \
  --maintenance-window-end "2024-01-06T14:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=FR"
```

**Option 2: Multi-day upgrade exclusions**
```bash
# Apply "no upgrades" exclusion, then manually control timing
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "manual-upgrade-control" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-01-31T00:00:00Z" \
  --add-maintenance-exclusion-scope no_upgrades

# Then manually trigger upgrades during your planned windows
```

## Upgrade Order & Timing

**Recommended sequence:**
1. **Control plane first** (during low-traffic period)
2. **CPU pools** (Weeks 1-2) - stateless workloads, lower risk
3. **T4/L4 inference pools** (Week 3) - during inference traffic lows
4. **A100/H100 training pools** (Week 4) - coordinate with ML team job schedules

**Critical coordination for GPU pools:**
- **Check training schedules** - don't upgrade during multi-day training runs
- **Pause new job submissions** 1 hour before GPU pool upgrades
- **Verify checkpointing** - ensure in-flight jobs can resume post-upgrade

## Long-Running Workload Protection

For your training workloads exceeding GKE's 1-hour eviction timeout:

```bash
# Apply "no minor or node upgrades" exclusion to training pools during active campaigns
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Training pool workflow:**
1. Cordon training nodes before upgrade: `kubectl cordon -l cloud.google.com/gke-nodepool=TRAINING_POOL`
2. Wait for current jobs to complete naturally (don't force-drain)
3. Upgrade empty pool
4. Uncordon: `kubectl uncordon -l cloud.google.com/gke-nodepool=TRAINING_POOL`

## Monitoring & Validation

**Track upgrade progress:**
```bash
# Monitor across all pools
watch 'gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE --format="table(name,version,status)"'

# Node-level view
watch 'kubectl get nodes -o custom-columns="NAME:.metadata.name,POOL:.metadata.labels.cloud\.google\.com/gke-nodepool,VERSION:.status.nodeInfo.kubeletVersion" --sort-by=.metadata.labels.cloud\.google\.com/gke-nodepool'
```

**GPU-specific validation:**
```bash
# Verify GPU driver compatibility post-upgrade
kubectl describe nodes -l cloud.google.com/gke-accelerator | grep "nvidia.com/gpu"

# Test workload deployment on upgraded nodes
kubectl run gpu-test --image=nvidia/cuda:11.0-runtime-ubuntu18.04 --limits=nvidia.com/gpu=1 --rm -it -- nvidia-smi
```

## Alternative: Release Channel + Exclusion Strategy

For maximum control without weekend urgency:

```bash
# Move to Extended channel for 24-month support
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended

# Apply persistent "no minor or node" exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Only control plane patches auto-apply
# You manually control when minor/node upgrades happen
```

This gives you:
- Up to 24 months between forced upgrades
- Control plane security patches automatically applied
- Manual control over disruptive minor + node upgrades
- Flexibility to upgrade pools individually during business-appropriate times

## Summary

**For your 3,000-node cluster, never attempt to upgrade all pools in a single 8-hour window.** The physics don't work - you're hitting GKE's fundamental parallelism limits.

**Recommended approach:** 
1. **Immediate:** Apply "no upgrades" exclusion to stop auto-upgrades
2. **Week 1-2:** Upgrade control plane + CPU pools manually
3. **Week 3-4:** Upgrade GPU pools during training gaps
4. **Long-term:** Consider Extended channel + persistent exclusions for predictable timing

**Key insight:** At your scale, upgrade planning becomes fleet orchestration. The 8-hour window constraint forces you into a multi-weekend strategy whether you plan for it or not.