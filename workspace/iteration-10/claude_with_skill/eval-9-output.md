# GKE Large Cluster Upgrade Optimization Plan

## Current State Analysis

**Cluster:** 600 nodes across 4 pools (2 CPU, 2 GPU A100 with reservations)
**Problem:** 24+ hour upgrades vs. 8-hour maintenance window
**Constraint:** GPU pools have fixed reservations (no surge capacity)

## Speed Optimization Strategy

### 1. Increase CPU Pool Parallelism

GKE's maximum upgrade parallelism is ~20 nodes simultaneously regardless of `maxSurge` setting. For your CPU pools:

```bash
# CPU pools - aggressive surge settings
gcloud container node-pools update CPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 20 \
  --max-unavailable-upgrade 0

gcloud container node-pools update CPU_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 20 \
  --max-unavailable-upgrade 0
```

This maximizes CPU pool upgrade speed by hitting GKE's parallelism ceiling.

### 2. GPU Pool Strategy (Reservation-Constrained)

Since A100 reservations typically have no surge capacity:

```bash
# GPU pools - maxUnavailable mode (no extra GPUs needed)
gcloud container node-pools update GPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 3

gcloud container node-pools update GPU_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 3
```

**Key insight:** For GPU pools, `maxUnavailable` is your primary speed lever, not `maxSurge`. Increase to 3-5 nodes for faster completion while maintaining some capacity.

### 3. Skip-Level Node Pool Upgrades

If control plane allows (within 2 minor version skew), upgrade node pools directly to the target version:

```bash
# Example: Skip from 1.31 → 1.33 directly (skip 1.32)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.33.x-gke.xxxx
```

This cuts upgrade time roughly in half by eliminating intermediate version stops.

### 4. Sequential Pool Upgrade Timing

Don't upgrade all pools simultaneously. Stagger for optimal resource utilization:

**Hour 0-2:** CPU pools (parallel, fast with high surge)
**Hour 2-6:** GPU pools (sequential, slower with unavailable-only mode)

### 5. Alternative: Auto-Scale Blue-Green for GPU

If you can get temporary quota expansion for the upgrade window:

```bash
# Enable auto-scale blue-green upgrade (preview)
gcloud container node-pools update GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling-blue-green-upgrade
```

This cordons the old pool and auto-scales a replacement, potentially faster than maxUnavailable mode.

## Estimated Time Savings

| Pool Type | Current Estimate | Optimized | Savings |
|-----------|-----------------|-----------|---------|
| CPU pools (400 nodes) | ~16 hours | ~4-6 hours | 10-12 hours |
| GPU pools (200 nodes) | ~8 hours | ~4-5 hours | 3-4 hours |
| **Total** | **24+ hours** | **~8-10 hours** | **14-16 hours** |

## Pre-Flight Checklist for Large GPU Clusters

```
Large Cluster Upgrade Checklist
- [ ] Training workloads checkpointed or scheduled between runs
- [ ] PDBs configured but not overly restrictive (allow some disruptions)
- [ ] GPU driver compatibility verified with target GKE version
- [ ] CUDA version change impact assessed (GKE auto-installs drivers)
- [ ] A100 reservation headroom confirmed (for any surge attempts)
- [ ] Compact placement preserved in upgraded nodes
- [ ] Multi-day maintenance window available as fallback
```

## Upgrade Runbook

```bash
# 1. Control plane first (parallel to preparation)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# 2. Configure surge settings
# CPU pools - maximize parallelism
gcloud container node-pools update CPU_POOL_1 \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 20 --max-unavailable-upgrade 0

# GPU pools - unavailable mode only
gcloud container node-pools update GPU_POOL_1 \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 0 --max-unavailable-upgrade 3

# 3. Start CPU pools first (parallel)
gcloud container node-pools upgrade CPU_POOL_1 \
  --cluster CLUSTER_NAME --zone ZONE \
  --cluster-version TARGET_VERSION &

gcloud container node-pools upgrade CPU_POOL_2 \
  --cluster CLUSTER_NAME --zone ZONE \
  --cluster-version TARGET_VERSION &

# 4. Monitor CPU completion, then start GPU pools
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=CPU_POOL_1'

# 5. Start GPU pools after CPU completes
gcloud container node-pools upgrade GPU_POOL_1 \
  --cluster CLUSTER_NAME --zone ZONE \
  --cluster-version TARGET_VERSION

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

## Fallback Options

If optimized approach still exceeds 8 hours:

1. **Split across multiple weekends:** Upgrade CPU pools one weekend, GPU pools the next
2. **Extended maintenance window:** Request 12-16 hour window
3. **Rolling blue-green:** Manual blue-green with new pools, migrate workloads over multiple weekends

## GPU-Specific Warnings

- **Driver version coupling:** Target GKE version changes GPU drivers automatically
- **Training job protection:** Use maintenance exclusions during active training campaigns
- **Reservation interaction:** maxUnavailable drains first, consuming reservation slots briefly

This optimization should bring your 600-node cluster upgrade within the 8-hour window while respecting GPU reservation constraints.