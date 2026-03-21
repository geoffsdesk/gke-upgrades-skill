# GKE Node Pool Upgrade Optimization Plan

**Cluster:** 600-node Standard cluster  
**Challenge:** 24+ hour upgrades exceeding 8-hour weekend maintenance window  
**Goal:** Complete upgrades within available window

## Current bottlenecks analysis

With 600 nodes and GKE's ~20-node maximum upgrade parallelism, you're looking at ~30 batches minimum per pool. At current settings, this explains your 24+ hour duration.

## Optimization strategy

### 1. Stagger node pool upgrades (immediate impact)

**Don't upgrade all 4 pools simultaneously.** Upgrade CPU pools first (Friday evening), then GPU pools (Saturday):

```bash
# Friday evening: CPU pools only
gcloud container node-pools upgrade CPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION

gcloud container node-pools upgrade CPU_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION

# Saturday: GPU pools (during planned training gaps)
gcloud container node-pools upgrade GPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

### 2. Aggressive surge settings for CPU pools

```bash
# Before upgrading CPU pools - increase parallelism
gcloud container node-pools update CPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 10 \
  --max-unavailable-upgrade 0

gcloud container node-pools update CPU_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 10 \
  --max-unavailable-upgrade 0
```

**Rationale:** Setting `maxSurge=10` increases parallelism significantly. Even though GKE caps at ~20 nodes simultaneously across the entire cluster, higher surge allows faster batch processing within each pool.

### 3. GPU pool strategy (maxUnavailable approach)

Since you have **fixed A100 reservations with no surge capacity**:

```bash
# GPU pools: Use maxUnavailable (no surge needed)
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

**Rationale:** `maxUnavailable=3` drains 3 GPU nodes simultaneously before creating replacements. No extra GPU quota needed, but creates temporary capacity dip. Adjust based on training workload tolerance.

### 4. Skip-level upgrades where possible

**Reduce total upgrade cycles** by skipping intermediate versions:

```bash
# If currently on 1.29, upgrade node pools directly to 1.31 (skip 1.30)
# Control plane must be upgraded to 1.31 first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.31.X-gke.Y

# Then skip-level upgrade node pools
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.X-gke.Y
```

### 5. Alternative: Auto-scale blue-green for GPU pools

If training workloads can tolerate full pool replacement:

```bash
gcloud container node-pools update GPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --enable-blue-green-upgrade \
  --blue-green-upgrade-policy-node-pool-soak-duration=30s \
  --blue-green-upgrade-policy-batch-soak-duration=30s
```

**Pros:** Faster than surge for large pools, creates full replacement capacity upfront  
**Cons:** Needs capacity for entire replacement GPU pool (expensive), all training jobs restart

## Estimated timeline with optimizations

| Phase | Duration | Details |
|-------|----------|---------|
| **Control plane** | 10-15 min | Always first, no parallelization |
| **CPU pools (parallel)** | 3-4 hours | With maxSurge=10, ~150 nodes each |
| **GPU pools (staggered)** | 2-3 hours each | With maxUnavailable=3, depends on pool size |
| **Total** | **8-10 hours** | Fits weekend window with buffer |

## Pre-upgrade checklist additions

```markdown
Large Cluster Optimization
- [ ] Node pool upgrade order planned: CPU → GPU
- [ ] CPU pool surge settings: maxSurge=10, maxUnavailable=0
- [ ] GPU pool unavailable settings: maxSurge=0, maxUnavailable=3
- [ ] Skip-level upgrade path confirmed (e.g., 1.29→1.31 directly)
- [ ] Training workloads checkpointed before GPU pool upgrade window
- [ ] GPU reservation capacity confirmed (no surge needed with maxUnavailable approach)
- [ ] Weekend maintenance window extended to 10 hours if possible
```

## Monitoring commands

```bash
# Track parallel progress across pools
watch 'gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE --format="table(name,version,status)"'

# Monitor node replacement in real-time
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | sort -k6'

# Check GPU node availability during unavailable-mode upgrade
kubectl get nodes -l cloud.google.com/gke-accelerator=nvidia-tesla-a100 -o wide
```

This approach should bring your upgrade time from 24+ hours down to 8-10 hours, fitting your weekend maintenance window.