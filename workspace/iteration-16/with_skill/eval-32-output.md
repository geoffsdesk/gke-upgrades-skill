# Large-Scale GKE Cluster Upgrade Strategy

**Cluster:** 3,000 nodes, 8 pools (4 GPU, 4 CPU) | **Window:** Saturday 2am-10am (8 hours)

## Root Cause: Window Too Small for Scale

With GKE's maximum upgrade parallelism of ~20 nodes simultaneously, your 3,000-node cluster requires approximately **150 batches minimum**. At 2-3 minutes per batch, you're looking at **5-8 hours per node pool** — far exceeding your 8-hour window, especially with 8 pools upgrading sequentially.

## Recommended Strategy: Extended Windows + Staggered Pools

### 1. Extend maintenance windows to 24-48 hours

```bash
# Extend to full weekend window
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-12-07T02:00:00Z" \
  --maintenance-window-end "2024-12-08T02:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Rationale:** Large clusters need multi-day windows. Plan for 6-12 hours per 1,000-node pool. Your GPU pools may take longer due to workload drain time.

### 2. Use "no minor or node upgrades" exclusions for upgrade control

Instead of relying on auto-upgrades within short windows, control exactly when upgrades happen:

```bash
# Block auto-upgrades, plan manual upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "manual-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

This gives you **complete control** over when node pool upgrades happen while still allowing critical control plane patches.

### 3. Staggered node pool upgrade sequence

**Phase 1 — CPU pools first (lower risk):**
```bash
# Upgrade CPU pools sequentially
for POOL in cpu-pool-1 cpu-pool-2 cpu-pool-3 cpu-pool-4; do
  gcloud container node-pools upgrade $POOL \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version TARGET_VERSION
  # Wait for completion before next pool
done
```

**Phase 2 — GPU pools during training gaps:**
```bash
# Coordinate with ML teams for training downtime
for POOL in a100-pool h100-pool l4-pool t4-pool; do
  gcloud container node-pools upgrade $POOL \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version TARGET_VERSION
done
```

### 4. GPU-specific upgrade settings

For your GPU pools, use **maxUnavailable as the primary lever** (assuming fixed reservations):

```bash
# GPU pools: drain-first strategy (no surge capacity)
gcloud container node-pools update GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4  # Increase for faster upgrades

# CPU pools: surge strategy
gcloud container node-pools update CPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5% \
  --max-unavailable-upgrade 0
```

**GPU pool considerations:**
- **A100/H100 pools:** `maxUnavailable=1-2` (conservative, high-value hardware)
- **L4/T4 pools:** `maxUnavailable=2-4` (can tolerate more disruption)
- **Training workload protection:** Coordinate upgrades with ML teams. Use maintenance exclusions during active training campaigns.

## Alternative Approach: Split the Cluster

For a 3,000-node cluster, consider **splitting into multiple smaller clusters** (500-1,000 nodes each):

**Benefits:**
- Upgrades complete in 2-4 hours instead of days
- Better blast radius isolation
- Easier to manage different upgrade cadences per workload type
- GPU and CPU workloads can have different maintenance schedules

**Workload-based split example:**
- **Training cluster:** H100/A100 pools, Extended channel, manual upgrade control
- **Inference cluster:** L4/T4 pools, Regular channel, weekend auto-upgrades
- **CPU cluster:** Regular channel, standard maintenance windows

## Timeline Expectations for Your Scale

| Pool Size | Estimated Duration | Considerations |
|-----------|-------------------|----------------|
| 500-node CPU pool | 2-4 hours | maxSurge=5%, good surge quota |
| 300-node A100 pool | 4-6 hours | maxUnavailable=1, training coordination |
| 800-node L4 pool | 4-8 hours | maxUnavailable=2-4, inference workloads |

**Total time:** 20-30 hours for all pools if done sequentially.

## Monitoring During Large Upgrades

```bash
# Track progress across all pools
watch 'gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE --format="table(name,version,status)"'

# Monitor stuck nodes
kubectl get nodes -o wide | grep -v Ready

# Check operations status
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=5
```

## Immediate Action Plan

1. **This weekend:** Extend your maintenance window to 24-48 hours
2. **Next week:** Apply "no minor or node upgrades" exclusion to gain manual control
3. **Plan upgrade:** Schedule node pool upgrades in phases (CPU first, then GPU during ML team coordination)
4. **Long-term:** Consider cluster splitting if upgrades consistently exceed acceptable windows

Your scale requires moving from auto-upgrade reliance to **manual upgrade orchestration** with proper planning and coordination across teams.