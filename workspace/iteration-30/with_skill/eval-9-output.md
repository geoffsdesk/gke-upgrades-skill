# Optimizing Large Cluster Upgrade Speed

## Current bottleneck analysis

With 600 nodes and 24+ hour upgrade times, you're hitting GKE's **maximum upgrade parallelism limit of ~20 nodes simultaneously** (roadmap: increasing to 100). For a 150-node pool, that's ~7-8 batches minimum, plus time for each node to drain/recreate.

**Key constraint:** Your 8-hour weekend window is insufficient for the current sequential approach.

## Recommended optimization strategy

### 1. GPU pools: Use maxUnavailable (not maxSurge)

Since you have fixed GPU reservations, surge capacity likely doesn't exist:

```bash
# Configure GPU pools for drain-first upgrades
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

**Reasoning:** `maxUnavailable=4` with ~20-node parallelism gives you batches of 4 nodes draining simultaneously. For a 150-node GPU pool: ~38 batches instead of 150 sequential operations.

### 2. CPU pools: Increase percentage-based maxSurge

Assuming adequate CPU quota for surge capacity:

```bash
# For 200-node CPU pools, 5% = 10 surge nodes
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

**Trade-off:** Higher maxSurge = faster upgrades but brief 5% capacity overage during surge.

### 3. Parallel node pool upgrades

**Critical change:** Trigger multiple node pool upgrades simultaneously instead of waiting for each to complete:

```bash
# Start all pools in parallel (requires manual coordination)
gcloud container node-pools upgrade CPU_POOL_1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade CPU_POOL_2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade GPU_POOL_1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade GPU_POOL_2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
```

**Impact:** Instead of 4 sequential 6-hour upgrades (24 hours), you get 4 parallel 6-hour upgrades (~6-8 hours total).

### 4. Upgrade sequencing strategy

To fit within your 8-hour window:

**Phase 1 (Hours 0-1):** Start all 4 pools simultaneously after pre-flight checks
**Phase 2 (Hours 1-6):** Monitor progress, address any stuck drains
**Phase 3 (Hours 6-8):** Validation and cleanup

## Alternative: Extend maintenance window with exclusions

If parallel upgrades still risk exceeding 8 hours, use a **maintenance exclusion pattern**:

```bash
# Before upgrade weekend: Apply 30-day "no upgrades" exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "large-upgrade-window" \
  --add-maintenance-exclusion-start-time "2024-MM-DDTHH:MM:SSZ" \
  --add-maintenance-exclusion-end-time "2024-MM-DDTHH:MM:SSZ" \
  --add-maintenance-exclusion-scope no_upgrades

# Manual upgrade during your preferred window
# Remove exclusion after completion
```

This gives you flexibility beyond the 8-hour weekend constraint.

## Workload-specific considerations

### GPU workload protection
- **Training jobs:** Ensure checkpointing is enabled. Consider cordoning GPU nodes and waiting for current jobs to complete before starting the upgrade.
- **Inference workloads:** The `maxUnavailable=4` approach will cause brief GPU capacity dips. Monitor queue depth and latency.

### CPU workload resilience
- **Verify PDBs aren't overly restrictive** — they're the #1 cause of stuck upgrades
- **Scale down non-critical workloads** during the upgrade window to free quota for surge nodes

## Expected timeline with optimizations

**Before:** 4 pools × 6 hours sequential = 24 hours
**After:** 4 pools × 6-8 hours parallel = 6-8 hours

This fits within your 8-hour weekend window with buffer for troubleshooting.

## Monitoring during parallel upgrades

```bash
# Monitor all pools simultaneously
watch 'gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE'

# Check for stuck pods across all namespaces
kubectl get pods -A | grep -v Running | grep -v Completed

# Track operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES"
```

## Validation checklist after parallel completion

```markdown
- [ ] All 4 node pools at target version
- [ ] All 600 nodes showing Ready status  
- [ ] No pods stuck in Terminating/Pending
- [ ] GPU reservations restored to expected capacity
- [ ] Training/inference workloads resumed successfully
- [ ] Application smoke tests passing
```

The key insight: **GKE's per-cluster parallelism limit applies across all pools**, so running 4 pools in parallel doesn't reduce the ~20 nodes/minute upgrade rate — but it eliminates the sequential wait time between pools, compressing your 24-hour upgrade into 6-8 hours.