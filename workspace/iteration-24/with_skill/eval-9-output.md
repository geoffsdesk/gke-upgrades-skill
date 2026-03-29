# GKE Large Cluster Upgrade Acceleration Plan

## Current bottlenecks analysis

Your 600-node cluster is hitting GKE's **maximum upgrade parallelism of ~20 nodes simultaneously**. With current settings, you're looking at ~30 batches minimum (600÷20), which explains the 24+ hour duration.

## Recommended acceleration strategies

### 1. Skip-level node pool upgrades (highest impact)

**Current approach:** Sequential minor upgrades (e.g., 1.31→1.32→1.33)
**Optimized approach:** 
- Control plane: Sequential minors (1.31→1.32→1.33) — required
- Node pools: Skip-level jump (1.31→1.33 directly) — saves 50% of upgrade cycles

```bash
# After control plane reaches 1.33, upgrade all node pools directly
gcloud container node-pools upgrade cpu-pool-1 \
  --cluster CLUSTER_NAME --zone ZONE \
  --cluster-version 1.33.x-gke.xxx &

gcloud container node-pools upgrade cpu-pool-2 \
  --cluster CLUSTER_NAME --zone ZONE \
  --cluster-version 1.33.x-gke.xxx &

# GPU pools after CPU pools complete
gcloud container node-pools upgrade gpu-pool-1 \
  --cluster CLUSTER_NAME --zone ZONE \
  --cluster-version 1.33.x-gke.xxx &

gcloud container node-pools upgrade gpu-pool-2 \
  --cluster CLUSTER_NAME --zone ZONE \
  --cluster-version 1.33.x-gke.xxx &
```

### 2. Parallel node pool upgrades (medium impact)

GKE upgrades one pool at a time by default. Manually trigger multiple pools concurrently:

```bash
# Start CPU pools simultaneously (lower risk)
gcloud container node-pools upgrade cpu-pool-1 \
  --cluster CLUSTER_NAME --zone ZONE \
  --cluster-version TARGET_VERSION &

gcloud container node-pools upgrade cpu-pool-2 \
  --cluster CLUSTER_NAME --zone ZONE \
  --cluster-version TARGET_VERSION &
```

**Important:** Don't run all 4 pools simultaneously — the ~20 node parallelism limit is cluster-wide. Running 2 CPU pools (300 nodes) concurrently maximizes the parallelism ceiling.

### 3. GPU pool optimization (critical for fixed reservations)

Your A100 pools with fixed reservations have **no surge capacity available**. Configure for drain-first strategy:

```bash
# GPU pools: maxUnavailable is your ONLY lever
gcloud container node-pools update gpu-pool-1 \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2

gcloud container node-pools update gpu-pool-2 \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2
```

**Trade-off:** `maxUnavailable=2` means 2 A100 nodes unavailable at once per pool. Only increase if your GPU workloads can tolerate the temporary capacity loss.

### 4. CPU pool surge optimization

For CPU pools with available quota, use percentage-based surge:

```bash
# Assuming 150-node CPU pools: 5% = ~8 nodes surge
gcloud container node-pools update cpu-pool-1 \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 8 \
  --max-unavailable-upgrade 0

gcloud container node-pools update cpu-pool-2 \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 8 \
  --max-unavailable-upgrade 0
```

### 5. Upgrade sequencing strategy

**Recommended order:**
1. Control plane (sequential minor upgrades)
2. CPU pools in parallel (lower risk, test surge/drain settings)
3. GPU pools after CPU completion (higher risk, fixed reservation constraints)

**Timeline estimate with optimizations:**
- Control plane: ~45 minutes per minor version
- CPU pools (parallel): ~8-12 hours for 300 nodes with optimized surge
- GPU pools (sequential): ~8-10 hours for 300 nodes with maxUnavailable=2

**Total: ~18-20 hours** (down from 24+)

## Extended maintenance window configuration

Since you still exceed the 8-hour window, configure a longer weekend window:

```bash
# Extended Saturday maintenance window (12+ hours)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T20:00:00Z" \
  --maintenance-window-duration 16h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Alternative: Blue-green for GPU pools

If you have **2x A100 reservation capacity**, consider blue-green for GPU pools to avoid the drain-first capacity dip:

```bash
gcloud container node-pools update gpu-pool-1 \
  --cluster CLUSTER_NAME --zone ZONE \
  --strategy BLUE_GREEN \
  --node-pool-soak-duration 3600s \
  --standard-rollout-policy batch-node-count=2,batch-soak-duration=300s
```

**Caveat:** This doubles GPU resource usage during upgrade. Only viable if your reservation has 2x capacity.

## Pre-upgrade checklist for large clusters

```bash
# Verify quota headroom for surge
gcloud compute project-info describe --format="yaml(quotas)"

# Check PDBs aren't overly restrictive
kubectl get pdb -A -o wide | grep "0$"

# Confirm no bare pods
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# GPU driver compatibility test in staging
# Create test pool with target version, deploy sample GPU workload
```

## Monitoring during upgrade

```bash
# Track progress across all pools
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "Ready|NotReady"'

# Monitor upgrade operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE \
  --filter="operationType:UPGRADE" --limit=5
```

## Expected improvement

**Current:** 24+ hours
**Optimized:** 16-20 hours with:
- Skip-level node upgrades (-4-6 hours)
- Parallel CPU pool upgrades (-2-4 hours) 
- Optimized GPU pool settings (-2-3 hours)

This should fit within a Saturday 8PM-4PM maintenance window (20 hours) or require only a modest extension to your current weekend schedule.