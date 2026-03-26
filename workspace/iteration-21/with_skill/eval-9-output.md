# Large Cluster Node Pool Upgrade Acceleration Plan

## Current bottlenecks analysis

Your 600-node cluster with 24+ hour upgrades is hitting GKE's maximum upgrade parallelism limit (~20 nodes simultaneously). With current settings, you're looking at ~30 batches minimum per pool, which explains the extended timeline.

## Recommended acceleration strategies

### 1. Aggressive maxUnavailable for GPU pools (primary lever)

Since your A100 pools use fixed reservations, **maxUnavailable is your ONLY effective lever** — there's no surge capacity available.

```bash
# GPU pools: Maximize concurrent drains
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

**Impact:** If each GPU pool has ~150 nodes, increasing from default `maxUnavailable=1` to `maxUnavailable=4` reduces batches from 150 to ~38, cutting GPU pool upgrade time by ~75%.

**Trade-off:** Temporary capacity loss during upgrade. For inference workloads, this may cause request queuing. For training, coordinate with job scheduling.

### 2. Optimize CPU pool surge settings

```bash
# CPU pools: Percentage-based surge (scales with pool size)
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

**Calculation:** For 150-node CPU pools, `maxSurge=10` creates 10 concurrent replacement nodes (capped at GKE's ~20 node batch limit). This reduces batches from 150 to ~15, cutting CPU upgrade time by ~90%.

### 3. Skip-level node upgrades (major time saver)

Instead of sequential minor upgrades:
```bash
# After control plane reaches target (e.g., 1.33)
# Skip levels on node pools: 1.31 → 1.33 directly
gcloud container node-pools upgrade ALL_POOLS \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.33.x-gke.xxx
```

**Impact:** Reduces total upgrade cycles. Instead of 1.31→1.32→1.33 (2 full cluster upgrade cycles), do 1.31→1.33 in one cycle.

### 4. Parallel node pool upgrades (manual trigger)

GKE auto-upgrades node pools sequentially. Manually trigger them in parallel:

```bash
# Start all pools simultaneously
gcloud container node-pools upgrade CPU_POOL_1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET &
gcloud container node-pools upgrade CPU_POOL_2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET &
gcloud container node-pools upgrade GPU_POOL_1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET &
gcloud container node-pools upgrade GPU_POOL_2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET &
```

**Impact:** 4x reduction in wall-clock time vs sequential upgrades.

### 5. Stagger by workload criticality

Start with lowest-risk pools first to validate settings:

**Weekend 1 (validation run):**
- CPU_POOL_1 (dev/test workloads) → validate new surge settings
- GPU_POOL_1 (inference) → validate maxUnavailable impact

**Weekend 2 (production run):**
- CPU_POOL_2 + GPU_POOL_2 in parallel → apply validated settings

## Optimized maintenance configuration

```bash
# Extend weekend window to 12 hours
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T20:00:00Z" \
  --maintenance-window-end "2024-01-07T08:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Apply "no upgrades" exclusion during weekdays
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "weekday-freeze" \
  --add-maintenance-exclusion-start-time "2024-01-01T08:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-01-31T20:00:00Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Expected timeline with optimizations

| Pool type | Nodes | Old time | New time | Improvement |
|-----------|-------|----------|----------|-------------|
| CPU pools (2×150) | 300 | ~15 hours | ~2 hours | 87% faster |
| GPU pools (2×150) | 300 | ~15 hours | ~4 hours | 73% faster |
| **Total (parallel)** | 600 | ~24+ hours | **~4-6 hours** | **75-80% faster** |

## Risk mitigation

### GPU pool capacity management
- **Monitor inference request queuing** during maxUnavailable=4 drains
- **Coordinate with training job scheduling** — avoid upgrades during multi-day runs
- **Validate A100 driver compatibility** with target GKE version in staging first

### CPU pool resource monitoring
- **Pre-allocate surge quota:** 20 extra CPU instances per pool (10 maxSurge × 2 pools)
- **Scale down non-critical workloads** before weekend window to free capacity
- **Monitor pod "musical chairs"** — if pods land on nodes about to be drained, reduce maxSurge to 5

## Monitoring commands during upgrade

```bash
# Track progress across all pools
watch 'kubectl get nodes -L cloud.google.com/gke-nodepool | grep -E "Ready|NotReady|SchedulingDisabled"'

# Monitor GPU utilization during drain
kubectl top nodes -l cloud.google.com/gke-accelerator=nvidia-tesla-a100

# Check for stuck pods
kubectl get pods -A | grep -E "Pending|Terminating" | wc -l

# Monitor surge quota usage
gcloud compute project-info describe --format="value(quotas[metric=CPUS].usage)"
```

## Implementation plan

1. **Week 1:** Test aggressive settings on one pool during maintenance window
2. **Week 2:** Apply to all pools with parallel manual triggers
3. **Week 3+:** Configure permanent maintenance exclusions to prevent weekday auto-upgrades

This approach should bring your 600-node upgrade well within an 8-hour weekend window while maintaining workload availability.