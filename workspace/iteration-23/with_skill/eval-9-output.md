# Accelerated Node Pool Upgrade Strategy for Large Standard Cluster

## Current State Analysis
- **Cluster:** 600 nodes across 4 pools (2 CPU, 2 GPU A100)
- **Problem:** 24+ hour upgrades vs 8-hour maintenance window
- **Constraint:** GPU pools have fixed reservations (no surge capacity)

## Root Cause: GKE Upgrade Parallelism Limits
- **Current parallelism:** ~20 nodes simultaneously regardless of `maxSurge` setting
- **Your math:** 600 nodes ÷ 20 = 30 batches minimum
- **Time per batch:** ~30-60 minutes (drain + provision + ready)
- **Total time:** 15-30 hours — exactly what you're seeing

## Acceleration Strategy

### 1. Optimize Node Pool Upgrade Settings

**CPU pools (surge capacity available):**
```bash
# Increase maxSurge to batch limit
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

**GPU pools (fixed reservations, no surge):**
```bash
# Use maxUnavailable as primary lever
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

### 2. Parallel Node Pool Upgrades

**Stagger upgrades to fit within 8-hour window:**
```bash
# Start CPU pools first (fastest, have surge capacity)
gcloud container node-pools upgrade CPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION &

gcloud container node-pools upgrade CPU_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION &

# Wait 2 hours, then start GPU pools
sleep 7200
gcloud container node-pools upgrade GPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION &

gcloud container node-pools upgrade GPU_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION &
```

### 3. Skip-Level Node Pool Upgrades

If your control plane is multiple versions ahead:
```bash
# Check current versions
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Skip intermediate versions (within 2-minor-version skew)
# Example: nodes at 1.31, CP at 1.33 → upgrade nodes directly to 1.33
```

### 4. Extended Maintenance Window Strategy

**Option A — Multi-weekend approach:**
- **Weekend 1:** Control plane + CPU pools (should complete in 8 hours)
- **Weekend 2:** GPU pools only (reduced scope, faster)

**Option B — Extended Saturday window:**
```bash
# Configure 12-hour weekend window
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T20:00:00Z" \
  --maintenance-window-end "2024-01-07T08:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Expected Time Reduction

With optimized settings:
- **CPU pools:** 5-8 hours (300 nodes, maxSurge=20)
- **GPU pools:** 4-6 hours (300 nodes, maxUnavailable=4)
- **Parallel execution:** CPU and GPU pools can overlap
- **Total time:** 8-12 hours (within extended window)

## GPU Pool Considerations

**Critical for A100 with fixed reservations:**
- `maxUnavailable=4` drains 4 nodes before creating replacements
- No surge capacity needed — stays within reservation limits
- Temporary capacity reduction during drain phase
- Increase `maxUnavailable` only if GPU workloads can tolerate capacity dips

## Pre-Upgrade Optimization

```bash
# Verify no stuck PDBs (common blocker in large clusters)
kubectl get pdb -A -o wide | grep "0.*0"

# Check for bare pods (won't reschedule)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Pause cluster autoscaler during upgrade window
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --no-enable-autoscaling
```

## Monitoring Commands

```bash
# Track upgrade progress across all pools
watch 'gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE --format="table(name, version, status)"'

# Monitor node versions
watch 'kubectl get nodes -o custom-columns=POOL:.metadata.labels.cloud\.google\.com/gke-nodepool,VERSION:.status.nodeInfo.kubeletVersion | sort'

# Check for stuck pods
kubectl get pods -A --field-selector=status.phase=Pending | wc -l
```

## Rollback Plan

If upgrade exceeds window:
```bash
# Check in-progress operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="status=RUNNING"

# Note: Cannot cancel node pool upgrades mid-flight
# Plan next weekend to complete remaining pools
```

## Long-term Recommendations

1. **Consider cluster splitting:** 600-node clusters approach operational complexity limits
2. **Use rollout sequencing:** For future fleet-wide upgrades with controlled progression
3. **Evaluate Autopilot:** Google manages all node upgrades, eliminating this operational overhead

This strategy should get your upgrades within the 8-12 hour range, fitting your maintenance window with minor extension.