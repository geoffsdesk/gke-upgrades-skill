# Fast Node Pool Upgrade Plan for Large Standard Cluster

## Current situation analysis

Your 24+ hour upgrade time with a 600-node cluster indicates you're likely hitting GKE's default upgrade parallelism limits. With only an 8-hour weekend maintenance window, you need to dramatically reduce upgrade time through strategy optimization and sequencing.

## Recommended approach: Optimized surge + skip-level upgrades

### 1. Skip-level node pool upgrades (biggest time saver)

Instead of upgrading nodes through each minor version sequentially, use skip-level (N+2) upgrades to jump directly to your target:

```bash
# Example: Skip 1.32 entirely, go directly 1.31 → 1.33
gcloud container node-pools upgrade CPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.33.x-gke.xxx
```

**Time savings:** ~50% reduction by eliminating intermediate upgrades.

### 2. Aggressive surge settings for CPU pools

Increase parallelism within GKE's ~20 node simultaneous upgrade limit:

```bash
# CPU pools: High surge for speed
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

**Why these settings:** `maxSurge=10` increases parallelism without causing capacity dips. Even though you set 10, GKE's actual limit is ~20 nodes across the entire cluster, but this ensures your pools can consume that parallelism.

### 3. GPU pool strategy (capacity-aware)

Since you have **fixed A100 reservations**, assume **zero surge capacity available**:

```bash
# GPU pools: maxUnavailable strategy (no extra GPUs needed)
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

**Why `maxUnavailable=3`:** This drains 3 GPU nodes at once before creating replacements. No extra A100s needed, but causes temporary capacity reduction. Adjust based on your workload tolerance.

### 4. Sequential pool upgrade with optimized ordering

Upgrade pools in this order to minimize total time:

```bash
# 1. Start with CPU pools simultaneously (they have surge capacity)
gcloud container node-pools upgrade CPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION &

gcloud container node-pools upgrade CPU_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION &

# Wait for CPU pools to complete, then GPU pools
# Monitor: watch 'kubectl get nodes -L cloud.google.com/gke-nodepool'

# 2. Once CPU complete, start GPU pools
gcloud container node-pools upgrade GPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION

# 3. Finally the second GPU pool
gcloud container node-pools upgrade GPU_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

**Why this sequence:** CPU pools with surge finish fastest. GPU pools without surge take longer but don't interfere with each other's capacity.

## Alternative: Autoscaled blue-green for GPU pools

If you want to eliminate GPU capacity dips entirely and your training workloads can tolerate controlled transitions:

```bash
# Enable autoscaled blue-green for GPU pools
gcloud container node-pools update GPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaled-blue-green-upgrade
```

**Trade-off:** This requires temporary **2x GPU capacity** during transition (old + new pools), but may be faster than drain-based upgrades if you have the reservation headroom.

## Time estimation with optimizations

**Before optimization:** 24+ hours
- All pools sequential, default surge settings
- ~20 nodes in parallel across 600 total = 30+ batches

**After optimization:** 6-8 hours (within your window)
- Skip-level upgrades (50% time reduction)
- Aggressive surge on CPU pools
- Parallel CPU pool upgrades
- Optimized GPU pool settings

**Breakdown:**
- CPU pools (parallel): ~2-3 hours with `maxSurge=10`
- GPU pools (sequential): ~3-4 hours with `maxUnavailable=3`
- Total: ~6-7 hours

## Pre-upgrade preparation

```bash
# 1. Configure all surge settings first
# (Use commands above for each pool)

# 2. Verify no workload blockers
kubectl get pdb -A | grep "0.*0"  # Check for overly restrictive PDBs

# 3. Pre-position surge capacity (CPU pools only)
# Verify you have quota for +20 extra CPU nodes temporarily

# 4. Set maintenance window
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start 2024-01-06T02:00:00Z \
  --maintenance-window-end 2024-01-06T10:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Monitoring during upgrade

```bash
# Track progress across all pools
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "NAME|CURRENT|TARGET"'

# Check for stuck operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=5

# Monitor GPU workloads specifically
kubectl get pods -A -l accelerator=nvidia-tesla-a100 | grep -v Running
```

## If you still exceed 8 hours

Consider splitting the upgrade across two weekends:
- **Weekend 1:** Control plane + CPU pools only
- **Weekend 2:** GPU pools only (they can be up to 2 minor versions behind CP)

This ensures your most disruptive components (GPU training workloads) get dedicated maintenance time.

With these optimizations, you should comfortably fit within your 8-hour weekend window while maintaining workload availability.