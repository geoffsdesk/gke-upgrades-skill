# GKE Upgrade Optimization for Large Standard Cluster

## Current State Analysis
- **600-node cluster, 4 node pools** (2 CPU, 2 GPU A100)
- **24+ hour upgrade duration** vs 8-hour maintenance window
- **Fixed GPU reservations** (likely no surge capacity available)

## Root Cause: Upgrade Parallelism Bottleneck

Your upgrade duration is constrained by GKE's maximum node upgrade parallelism (~20 nodes simultaneously). With 600 nodes, you're looking at ~30 batches minimum, which explains the extended timeline.

## Optimization Strategy

### 1. GPU Pool Configuration (Critical)

For A100 pools with fixed reservations, use **drain-first mode** with increased parallelism:

```bash
# GPU pools: Use maxUnavailable as primary lever (no surge capacity)
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

**Key insight**: `maxUnavailable` is your ONLY effective lever for GPU pools with fixed reservations. Increasing from 1→4 reduces batch count from 150→38 per pool (assuming ~150 nodes per GPU pool).

### 2. CPU Pool Configuration (Aggressive Surge)

For CPU pools, use percentage-based surge with higher parallelism:

```bash
# CPU pools: Aggressive surge settings (assuming ~150 nodes per pool)
# 5% of 150 = 7-8 nodes per batch
gcloud container node-pools update CPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 8 \
  --max-unavailable-upgrade 0

gcloud container node-pools update CPU_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 8 \
  --max-unavailable-upgrade 0
```

### 3. Upgrade Sequencing Strategy

**Option A: Sequential by Pool Type (Recommended)**
```bash
# Phase 1: CPU pools first (lower risk, validate settings)
gcloud container node-pools upgrade CPU_POOL_1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION
gcloud container node-pools upgrade CPU_POOL_2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION

# Phase 2: GPU pools during training gaps
gcloud container node-pools upgrade GPU_POOL_1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION
gcloud container node-pools upgrade GPU_POOL_2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION
```

**Option B: Custom Blue-Green for GPU (If Training Tolerates Full Restart)**
For multi-day training workloads that can checkpoint/resume:
1. Scale training to zero, save checkpoints
2. Recreate GPU pools entirely at target version
3. Restart training from checkpoint

### 4. Maintenance Window Optimization

**Extended maintenance window approach**:
```bash
# Set longer maintenance window (12-16 hours) starting Friday night
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-02-09T22:00:00Z" \
  --maintenance-window-end "2024-02-10T14:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=FR"
```

### 5. Pre-Upgrade Preparation

**GPU workload coordination**:
```bash
# Before upgrade: Cordon GPU nodes and wait for training completion
kubectl cordon -l cloud.google.com/gke-nodepool=GPU_POOL_1
kubectl cordon -l cloud.google.com/gke-nodepool=GPU_POOL_2

# Monitor until training jobs complete naturally
kubectl get pods -A --field-selector spec.nodeName="" | grep training
```

## Expected Performance Improvement

| Pool Type | Current (est.) | Optimized | Time Reduction |
|-----------|---------------|-----------|----------------|
| CPU Pool 1 (150 nodes) | ~8 batches × 30min = 4h | ~19 batches × 20min = 6.3h | Slight increase due to surge provisioning |
| CPU Pool 2 (150 nodes) | ~8 batches × 30min = 4h | ~19 batches × 20min = 6.3h | Slight increase due to surge provisioning |
| GPU Pool 1 (150 nodes) | ~150 batches × 20min = 50h | ~38 batches × 20min = 12.7h | **75% reduction** |
| GPU Pool 2 (150 nodes) | ~150 batches × 20min = 50h | ~38 batches × 20min = 12.7h | **75% reduction** |

**Total estimated time**: ~14 hours (fits in 16-hour weekend window)

## Implementation Runbook

```bash
# 1. Pre-flight: Configure surge settings
gcloud container node-pools update CPU_POOL_1 --cluster CLUSTER_NAME --zone ZONE --max-surge-upgrade 8 --max-unavailable-upgrade 0
gcloud container node-pools update CPU_POOL_2 --cluster CLUSTER_NAME --zone ZONE --max-surge-upgrade 8 --max-unavailable-upgrade 0
gcloud container node-pools update GPU_POOL_1 --cluster CLUSTER_NAME --zone ZONE --max-surge-upgrade 0 --max-unavailable-upgrade 4
gcloud container node-pools update GPU_POOL_2 --cluster CLUSTER_NAME --zone ZONE --max-surge-upgrade 0 --max-unavailable-upgrade 4

# 2. Control plane upgrade (Friday evening)
gcloud container clusters upgrade CLUSTER_NAME --zone ZONE --master --cluster-version TARGET_VERSION

# 3. CPU pools (Friday night - Saturday morning)
gcloud container node-pools upgrade CPU_POOL_1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION
gcloud container node-pools upgrade CPU_POOL_2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION

# 4. GPU pools (Saturday afternoon - Sunday morning)
# Ensure training jobs are checkpointed first
gcloud container node-pools upgrade GPU_POOL_1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION
gcloud container node-pools upgrade GPU_POOL_2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION
```

## Risk Mitigation

- **Capacity dip on GPU pools**: The 4-node `maxUnavailable` setting creates temporary capacity loss. Coordinate with training teams.
- **Increased CPU surge quota**: Monitor quota utilization during CPU pool upgrades.
- **Training job coordination**: Essential to cordon GPU nodes before upgrade starts.

This approach should bring your upgrade time from 24+ hours down to ~14 hours, fitting within an extended weekend maintenance window.