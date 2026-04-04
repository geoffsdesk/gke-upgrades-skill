# GKE Upgrade Acceleration Plan for Large Standard Cluster

## Current Performance Analysis

With **GKE's ~20 node upgrade parallelism limit**, your 600-node cluster requires ~30 batches minimum, which explains the 24+ hour duration. Here's how to dramatically reduce upgrade time:

## Primary Acceleration Strategy: maxUnavailable for GPU Pools

**For GPU pools with fixed reservations (your primary bottleneck):**
```bash
# Current: likely maxSurge=1, maxUnavailable=0 (default)
# Problem: Only 1 GPU node upgrading at a time

# Accelerated: Use maxUnavailable as the primary lever
gcloud container node-pools update GPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4

gcloud container node-pools update GPU_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4
```

**Impact:** This increases GPU upgrade parallelism from 1→4 per pool (8 total), reducing GPU upgrade time from ~15 hours to ~4 hours.

**Trade-off:** Temporary 4-node capacity loss per pool during upgrade. Only use if your GPU workloads can tolerate this reduction.

## Secondary Strategy: Optimize CPU Pool Settings

**For CPU pools (likely have surge capacity):**
```bash
# Calculate 5% of pool size, minimum 1
# Example: 200-node pool → 5% = 10 nodes
gcloud container node-pools update CPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 10 \
  --max-unavailable-upgrade 0

gcloud container node-pools update CPU_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 8 \
  --max-unavailable-upgrade 0
```

**Impact:** CPU pools upgrade 5-10x faster with higher parallelism.

## Advanced Strategy: Parallel Node Pool Upgrades

Upgrade multiple node pools **simultaneously** instead of sequentially:

```bash
# Start all node pool upgrades in parallel (don't wait between pools)
gcloud container node-pools upgrade CPU_POOL_1 \
  --cluster CLUSTER_NAME --zone ZONE \
  --cluster-version TARGET_VERSION --async &

gcloud container node-pools upgrade CPU_POOL_2 \
  --cluster CLUSTER_NAME --zone ZONE \
  --cluster-version TARGET_VERSION --async &

gcloud container node-pools upgrade GPU_POOL_1 \
  --cluster CLUSTER_NAME --zone ZONE \
  --cluster-version TARGET_VERSION --async &

gcloud container node-pools upgrade GPU_POOL_2 \
  --cluster CLUSTER_NAME --zone ZONE \
  --cluster-version TARGET_VERSION --async &

# Monitor all operations
watch 'gcloud container operations list --cluster CLUSTER_NAME --zone ZONE'
```

**Impact:** Total upgrade time becomes the duration of your **slowest pool** rather than the sum of all pools.

## Maintenance Window Strategy

**Option A: Fit within 8-hour window**
- Start Friday 10 PM, complete by Saturday 6 AM
- Parallel upgrades + optimized settings should fit
- Monitor closely; be prepared to extend if needed

**Option B: Extend maintenance window**
```bash
# 12-hour window Friday night → Saturday morning
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-05T22:00:00Z" \
  --maintenance-window-end "2024-01-06T10:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=FR"
```

## GPU-Specific Considerations

**Before increasing maxUnavailable on GPU pools:**
1. **Verify workload tolerance:** Can your training/inference handle 4 fewer A100s temporarily?
2. **Check reservation headroom:** Confirm your reservation can't provide surge capacity
3. **Coordinate with ML teams:** Schedule during natural gaps between training runs

**GPU driver compatibility check:**
```bash
# Test target version + driver in a staging pool first
gcloud container node-pools create staging-gpu-test \
  --cluster STAGING_CLUSTER \
  --zone ZONE \
  --cluster-version TARGET_VERSION \
  --accelerator type=nvidia-tesla-a100,count=1 \
  --num-nodes 1
```

## Expected Timeline with Optimizations

| Pool | Nodes | Strategy | Est. Duration |
|------|-------|----------|---------------|
| CPU Pool 1 | 200 | maxSurge=10 | ~2 hours |
| CPU Pool 2 | 150 | maxSurge=8 | ~2 hours |
| GPU Pool 1 | 125 | maxUnavailable=4 | ~3 hours |
| GPU Pool 2 | 125 | maxUnavailable=4 | ~3 hours |
| **Total (parallel)** | **600** | **All simultaneous** | **~3-4 hours** |

## Alternative: Autoscaled Blue-Green for GPU Pools

If GPU workload disruption is unacceptable, consider autoscaled blue-green:

```bash
gcloud container node-pools update GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-blue-green-upgrade \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25
```

**Trade-off:** Requires 25% extra GPU capacity initially, but zero disruption to running workloads.

## Risk Mitigation

1. **Test in staging first** with identical pool sizes and settings
2. **GPU staging validation mandatory** — verify driver compatibility
3. **Monitor PDBs:** Ensure they don't block the accelerated drain
4. **Rollback plan:** Create replacement pools at old version if needed

This approach should reduce your upgrade time from 24+ hours to **under 4 hours**, fitting within your weekend maintenance window.