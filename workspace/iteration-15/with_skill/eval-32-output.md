# Large-Scale GKE Cluster Upgrade Strategy

Your 8-hour maintenance window is insufficient for a 3,000-node cluster. At GKE's maximum upgrade parallelism of ~20 nodes simultaneously, you're looking at **150+ batches minimum** — that's 12-30+ hours depending on your surge settings and node readiness times.

## Immediate Solutions

### 1. Extend Maintenance Window to Multi-Day
**Replace your 8-hour Saturday window with a 72-hour weekend window:**
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-end "2024-01-08T10:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### 2. Optimize Surge Settings Per Pool Type

**CPU pools (assume stateless workloads):**
```bash
# For 400-500 node CPU pools, use 5% surge
gcloud container node-pools update CPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 20 \
  --max-unavailable-upgrade 0
```

**GPU pools (limited/no surge capacity):**
```bash
# For GPU pools with fixed reservations
gcloud container node-pools update GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2
```
⚠️ **Key insight**: `maxUnavailable` is your PRIMARY lever for GPU pools. Increase from 1 to 2-4 only if your training/inference workloads can tolerate temporary capacity loss.

### 3. Sequential Pool Upgrade Strategy

**Don't upgrade all 8 pools simultaneously.** Stagger them:

**Phase 1 (Friday night):** CPU pools only
```bash
# Trigger CPU pools manually to start before maintenance window
for pool in cpu-pool-1 cpu-pool-2 cpu-pool-3 cpu-pool-4; do
  gcloud container node-pools upgrade $pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version TARGET_VERSION
done
```

**Phase 2 (Saturday):** GPU pools during training gaps
```bash
# Only after CPU pools complete
for pool in a100-pool h100-pool l4-pool t4-pool; do
  gcloud container node-pools upgrade $pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version TARGET_VERSION
done
```

## Advanced Solutions

### 4. Split into Multiple Clusters
**3,000 nodes in a single cluster is operationally complex.** Consider splitting by workload type:
- **Training cluster**: A100/H100 pools (500-1000 nodes)
- **Inference cluster**: L4/T4 pools (500-1000 nodes)  
- **Batch/web cluster**: CPU pools (1000-1500 nodes)

This gives you:
- Faster individual cluster upgrades (4-8 hours each)
- Independent maintenance windows
- Blast radius isolation
- Easier capacity planning

### 5. GPU-Specific Upgrade Strategy

**For A100/H100 training pools:**
- Use maintenance exclusions to freeze during active training campaigns
- Schedule upgrades during natural training gaps (between experiments)
- Consider AI Host Maintenance for parallel updates when training allows full restart

```bash
# Block upgrades during training campaign
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-q1" \
  --add-maintenance-exclusion-start-time "2024-01-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-02-15T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### 6. Nodepool Upgrade Concurrency (Preview - April 2026)
GKE is adding concurrent nodepool upgrades for auto-upgrades. This will significantly reduce your total upgrade time by upgrading multiple pools simultaneously instead of sequentially.

## Upgrade Planning Template

```bash
# Pre-upgrade: Check current versions
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
  --format="table(nodePools[].name,nodePools[].version,nodePools[].instanceGroupUrls[].basename())"

# Control plane first (30 minutes)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# Phase 1: CPU pools (6-12 hours estimated)
# Phase 2: GPU pools (8-16 hours estimated) 
# Total: 14-28 hours for full fleet
```

## Maintenance Window Configuration

**Recommended approach for your scale:**
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-05T22:00:00Z" \
  --maintenance-window-end "2024-01-07T14:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=FR"
```
*Friday 10pm → Sunday 2pm = 40-hour window*

## Monitoring During Large Upgrades

```bash
# Monitor overall progress
watch 'gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE --format="table(name,version,status)"'

# Track node readiness by pool
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | sort -k6'

# Check for stuck pods blocking drain
kubectl get pods -A | grep -E "Terminating|Pending" | wc -l
```

## Key Recommendations

1. **Extend maintenance window to 40+ hours** (Friday night → Sunday afternoon)
2. **Upgrade CPU pools first**, GPU pools second during training gaps
3. **Use maxUnavailable=2-4 for GPU pools** if workloads can tolerate capacity dips
4. **Consider cluster splitting** — 3 clusters of 1,000 nodes upgrade faster than 1 cluster of 3,000
5. **Plan 24-48 hours total** for your current scale

Your 8-hour window works for ~500-1,000 node clusters, not 3,000. At this scale, you need enterprise-grade maintenance planning with multi-day windows and workload-aware sequencing.