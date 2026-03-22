# GKE Node Pool Upgrade Optimization Plan

## Current situation analysis

Your 600-node cluster with 4 pools is hitting GKE's ~20 node parallel upgrade limit, resulting in ~30 batches minimum per pool. With sequential pool upgrades, you're looking at 120+ total batches — explaining the 24+ hour duration.

## Recommended optimization strategy

### 1. Increase surge parallelism for CPU pools

```bash
# Configure aggressive surge for CPU pools (assuming stateless workloads)
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

**Rationale:** Higher `maxSurge` increases parallelism. Even though GKE caps at ~20 nodes simultaneously, this ensures the queue stays full and reduces coordination overhead between batches.

### 2. GPU pools — use maxUnavailable strategy

Since you have fixed A100 reservations (no surge capacity available):

```bash
# Configure GPU pools for drain-first upgrades
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

**Rationale:** `maxUnavailable=3` allows 3 GPU nodes to upgrade simultaneously. This causes temporary capacity reduction but requires zero additional GPU quota.

### 3. Skip-level node pool upgrades

If your control plane is already at the target version, upgrade node pools directly to that version instead of sequential minor versions:

```bash
# Example: Jump from 1.31 directly to 1.33, skipping 1.32
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.33.x-gke.xxxx
```

**Impact:** Reduces total upgrade operations by 50% if you're currently doing sequential upgrades.

### 4. Manual pool sequencing within the maintenance window

Instead of letting GKE upgrade all pools sequentially, manually orchestrate them:

```bash
# Start CPU pools first (can run in parallel if quota allows)
gcloud container node-pools upgrade CPU_POOL_1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade CPU_POOL_2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &

# Monitor progress and start GPU pools once CPU pools are ~50% complete
# This overlaps upgrade windows instead of waiting for full completion
```

### 5. Consider autoscaled blue-green for GPU pools (preview)

For the GPU pools specifically, consider GKE's autoscaled blue-green upgrade strategy:

```bash
gcloud container node-pools update GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-blue-green-upgrade \
  --node-pool-soak-duration 300s \
  --autoscale-blue-green-upgrade
```

**Benefits:**
- Cordons old GPU pool, auto-scales replacement based on demand
- No extra GPU capacity needed upfront
- Better for long-running training jobs that can't tolerate eviction
- Faster than drain-and-replace for large pools

## Timeline projection with optimizations

**Before optimization:** 600 nodes ÷ 20 parallel = 30 batches × 4 pools = 120 total batches ≈ 24+ hours

**After optimization:**
- CPU pools: 2 pools × ~15 batches = 30 batches (can run in parallel) ≈ 4-6 hours
- GPU pools: 2 pools × ~20 batches (maxUnavailable=3) ≈ 6-8 hours
- **Total with sequencing overlap:** 8-10 hours

## GPU-specific considerations

### Training job protection
```bash
# Add maintenance exclusion during active training campaigns
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-q1" \
  --add-maintenance-exclusion-start-time 2024-01-15T00:00:00Z \
  --add-maintenance-exclusion-end-time 2024-03-31T23:59:59Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### Driver compatibility check
```bash
# Verify CUDA driver version for target GKE version
gcloud container get-server-config --zone ZONE --format="yaml(validNodeVersions)"
# Test in a staging cluster first — GKE auto-installs drivers matching the target version
```

## Monitoring during upgrade

```bash
# Track upgrade progress across all pools
watch 'kubectl get nodes -L cloud.google.com/gke-nodepool -o wide | grep -E "(Ready|NotReady|SchedulingDisabled)"'

# Monitor GPU workload disruption
kubectl get pods -n gpu-workloads -o wide --field-selector spec.nodeName=""
```

## Alternative: Split weekend maintenance window

If 8-10 hours still doesn't fit your weekend window, consider:

1. **Weekend 1:** Upgrade control plane + CPU pools (4-6 hours)
2. **Weekend 2:** Upgrade GPU pools during training gaps (4-6 hours)

This leverages the fact that node pools can be up to 2 minor versions behind the control plane.

With these optimizations, you should comfortably complete the upgrade within a single 8-hour weekend maintenance window, reducing your upgrade time by 60-70%.