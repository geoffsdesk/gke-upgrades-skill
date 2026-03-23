# GKE Node Pool Upgrade Acceleration Plan

## Current Bottleneck Analysis

Your 24+ hour upgrade time is caused by GKE's default upgrade parallelism (~20 nodes simultaneously) and conservative surge settings. With 600 nodes, you're looking at 30+ sequential batches minimum.

## Optimization Strategy

### 1. **Increase maxSurge for CPU pools (primary acceleration)**

Current default is likely `maxSurge=1`. For your 600-node cluster, calculate percentage-based surge:

**CPU Pool 1 (assuming ~200 nodes):**
```bash
gcloud container node-pools update CPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 10 \
  --max-unavailable-upgrade 0
```

**CPU Pool 2 (assuming ~200 nodes):**
```bash
gcloud container node-pools update CPU_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 10 \
  --max-unavailable-upgrade 0
```

**Calculation:** 5% of 200 nodes = 10 nodes surge per pool. This reduces CPU pool upgrade time from ~10 hours to ~2 hours each.

### 2. **GPU pools: Use maxUnavailable strategy**

GPU nodes with fixed reservations can't surge (no extra capacity). Use `maxUnavailable` as the primary lever:

**GPU Pool 1:**
```bash
gcloud container node-pools update GPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2
```

**GPU Pool 2:**
```bash
gcloud container node-pools update GPU_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2
```

This drains 2 GPU nodes simultaneously per pool (no extra GPUs needed, but temporary capacity reduction).

### 3. **Stagger pool upgrades strategically**

Don't upgrade all pools simultaneously. Sequence them to maximize resource utilization:

**Weekend upgrade sequence:**
1. **Friday evening:** Upgrade CPU pools (2-3 hours each with surge)
2. **Saturday morning:** Upgrade GPU Pool 1 during training gap
3. **Saturday afternoon:** Upgrade GPU Pool 2 during training gap

### 4. **Pre-upgrade optimization**

**Scale down non-critical workloads** before the weekend:
```bash
# Example: scale down dev workloads
kubectl scale deployment non-critical-app --replicas=0 -n dev
```

**Checkpoint training jobs** and schedule gaps for GPU upgrades.

## Expected Time Reduction

| Pool | Current Time | Optimized Time | Improvement |
|------|-------------|---------------|-------------|
| CPU Pool 1 (200 nodes) | ~10 hours | ~2 hours | 80% reduction |
| CPU Pool 2 (200 nodes) | ~10 hours | ~2 hours | 80% reduction |
| GPU Pool 1 (100 nodes) | ~5 hours | ~2.5 hours | 50% reduction |
| GPU Pool 2 (100 nodes) | ~5 hours | ~2.5 hours | 50% reduction |
| **Total** | **24+ hours** | **~6-8 hours** | **70% reduction** |

## Advanced Option: Blue-Green for Mission-Critical Pools

If any pool is absolutely critical and you have quota headroom, consider blue-green:

```bash
gcloud container node-pools update CRITICAL_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --node-pool-soak-duration 300s \
  --surge-upgrade-type blue-green
```

This doubles resource usage temporarily but provides fast rollback and zero capacity dip.

## Pre-Upgrade Checklist

```markdown
- [ ] PDBs reviewed — not overly restrictive (allow some disruptions)
- [ ] Non-critical workloads scaled down
- [ ] Training jobs checkpointed with scheduled gaps for GPU upgrades
- [ ] CPU pool surge settings increased: maxSurge=10, maxUnavailable=0
- [ ] GPU pool unavailable settings: maxSurge=0, maxUnavailable=2
- [ ] Upgrade sequence planned: CPU pools Friday → GPU pools Saturday
- [ ] Monitoring active to track progress
```

## Monitoring Progress

```bash
# Real-time node status by pool
watch 'kubectl get nodes -L cloud.google.com/gke-nodepool -o wide | grep -E "NAME|Ready|NotReady"'

# Track upgrade operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=5
```

This optimization should bring your total upgrade time down to 6-8 hours, fitting comfortably within your weekend maintenance window.