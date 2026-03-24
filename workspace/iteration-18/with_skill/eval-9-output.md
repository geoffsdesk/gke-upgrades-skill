# GKE Large Cluster Upgrade Optimization

## Current Bottlenecks Analysis

With 600 nodes, your upgrades are hitting GKE's maximum parallelism limit of ~20 nodes simultaneously. This means ~30 batches minimum, and with default surge settings, you're looking at 24+ hours total time.

**Key constraint:** GPU pools with fixed reservations have NO surge capacity available. Your `maxSurge` setting is irrelevant for GPU pools — `maxUnavailable` is the only effective lever.

## Recommended Optimization Strategy

### 1. Optimize Node Pool Upgrade Settings

**CPU Pools (with surge capacity):**
```bash
# Increase maxSurge for CPU pools (5% of pool size, minimum 1)
# Assuming ~150 nodes per CPU pool: 5% = 7-8 nodes

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

**GPU Pools (fixed reservations - maxUnavailable is the primary lever):**
```bash
# Increase maxUnavailable for GPU pools (can go higher if workloads tolerate capacity dips)
# Assuming ~150 nodes per GPU pool, start with 2-4 unavailable

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

**Time impact:** This should reduce total upgrade time from 24+ hours to ~12-16 hours.

### 2. Extend Maintenance Window Strategy

**Option A - Split maintenance windows:**
```bash
# Weekend 1: CPU pools only
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-duration 8h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Add temporary exclusion for GPU pools
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "gpu-pools-hold" \
  --add-maintenance-exclusion-start "2024-01-06T00:00:00Z" \
  --add-maintenance-exclusion-end "2024-01-06T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**Option B - Longer weekend window:**
```bash
# Friday night through Sunday morning (36-hour window)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-05T22:00:00Z" \
  --maintenance-window-duration 36h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=FR"
```

### 3. Pool Upgrade Sequencing

Upgrade CPU pools first (lower risk), then GPU pools:

```bash
# Manual approach - trigger CPU pools first
gcloud container node-pools upgrade CPU_POOL_1 CPU_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION

# Wait for CPU completion, then GPU
gcloud container node-pools upgrade GPU_POOL_1 GPU_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

### 4. GPU-Specific Considerations

**For training workloads:** Use maintenance exclusions to protect long-running jobs:
```bash
# Block node upgrades during training campaigns
gcloud container node-pools update GPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**For inference workloads:** Consider autoscaled blue-green to avoid inference latency spikes:
```bash
# Enable autoscaling first
gcloud container node-pools update GPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 50 \
  --total-max-nodes 150 \
  --strategy=BLUE_GREEN \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

### 5. Alternative: Skip-Level Node Upgrades

If control plane is already 2+ versions ahead, use skip-level upgrades:
```bash
# Example: Upgrade nodes from 1.31 directly to 1.33 (skip 1.32)
gcloud container node-pools upgrade ALL_POOLS \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.33.X-gke.Y
```

This reduces the number of upgrade cycles from 3 to 1.

## Recommended Implementation Plan

### Phase 1: Immediate Optimization (next upgrade)
1. Apply optimized surge/unavailable settings above
2. Extend weekend maintenance window to 16-20 hours
3. Use manual pool sequencing (CPU first, then GPU)

### Phase 2: Long-term Strategy
1. Evaluate splitting CPU and GPU workloads into separate clusters for independent upgrade schedules
2. Implement autoscaled blue-green for GPU inference pools
3. Use maintenance exclusions for GPU training pools during campaigns

## Expected Results

- **Time reduction:** From 24+ hours to 12-16 hours
- **Window fit:** 16-20 hour weekend window should accommodate full upgrade
- **Risk mitigation:** CPU pools upgrade first, validate before GPU
- **Workload protection:** GPU workloads get appropriate upgrade strategy

## Monitoring Commands

```bash
# Track upgrade progress
watch 'kubectl get nodes -o wide | grep -E "Ready|NotReady" | wc -l'

# Monitor node pool status
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="status=RUNNING"

# Check for stuck pods during upgrade
kubectl get pods -A | grep -E "Terminating|Pending"
```

The key insight: **GPU pools with fixed reservations can ONLY use `maxUnavailable` for speed control**, while CPU pools can leverage both `maxSurge` and parallel upgrades. Optimize each pool type differently.