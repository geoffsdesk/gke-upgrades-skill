# Large-Scale GKE Upgrade Strategy (3,000-Node Cluster)

You're hitting GKE's built-in upgrade parallelism limits. With **~20 nodes upgrading simultaneously** (increasing to 100), your 3,000-node cluster needs **150+ batches minimum** — far exceeding your 8-hour window.

## Immediate Solutions

### 1. Extend maintenance windows (simplest fix)
```bash
# 48-hour weekend window
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --maintenance-window-start "2024-01-06T02:00:00Z" \
    --maintenance-window-end "2024-01-08T02:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### 2. Stagger node pool upgrades across multiple weekends

**Weekend 1 — CPU pools only:**
```bash
# Apply temporary exclusion to GPU pools
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "gpu-pools-freeze" \
    --add-maintenance-exclusion-start-time "2024-01-06T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-01-13T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades

# Manually upgrade CPU pools during Saturday window
for pool in cpu-pool-1 cpu-pool-2 cpu-pool-3 cpu-pool-4; do
    gcloud container node-pools upgrade $pool \
        --cluster CLUSTER_NAME \
        --zone ZONE \
        --cluster-version TARGET_VERSION
done
```

**Weekend 2 — GPU pools (with special handling):**
```bash
# Remove CPU exclusion, upgrade GPU pools
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --remove-maintenance-exclusion-name "gpu-pools-freeze"
```

## GPU Pool Upgrade Strategy

Your GPU pools require different handling due to capacity constraints:

### For A100/H100 pools (assume fixed reservations):
```bash
gcloud container node-pools update a100-pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 2
    # Drains 2 nodes at a time, no surge capacity needed
```

### For L4/T4 pools (if surge capacity exists):
```bash
gcloud container node-pools update l4-pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 1 \
    --max-unavailable-upgrade 0
    # Conservative 1 surge node at a time
```

## Long-term Architecture Changes

### Option A: Split into multiple clusters
- **GPU cluster:** 4 GPU pools (~800-1,200 nodes)
- **CPU cluster:** 4 CPU pools (~1,800-2,200 nodes)
- **Benefits:** Parallel upgrades, isolated blast radius, separate maintenance windows
- **Migration:** Use cluster-to-cluster workload migration

### Option B: Regional cluster with zone-based rolling
If you're currently zonal, migrate to regional:
```bash
# Regional clusters upgrade zone-by-zone within each pool
# Still limited by 20-node parallelism per zone, but spreads across 3 zones
```

## Training Workload Protection

For multi-day GPU training jobs:
```bash
# "No minor or node upgrades" exclusion during training campaigns
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "training-protection" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
    # Allows CP security patches, blocks disruptive node upgrades
```

## Upgrade Timeline Estimation

**Current constraint:** ~20 nodes/batch × 8-hour window = 160 nodes maximum per weekend

**Your scale:** 3,000 nodes ÷ 160 = **19 weekends** at current parallelism

**With staggered approach:**
- Weekend 1: CPU pools (~2,000 nodes) — needs 48-72 hour window
- Weekend 2: GPU pools (~1,000 nodes) — 8-hour window sufficient with maxUnavailable tuning

## Monitoring During Large Upgrades

```bash
# Track upgrade progress
watch 'gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES" --limit=5'

# Monitor node versions
watch 'kubectl get nodes -o wide | grep -E "NAME|1.28|1.29" | head -20'

# Check for stuck pods
kubectl get pods -A | grep -E "Terminating|Pending" | wc -l
```

## Recommended Configuration

```bash
# Extended maintenance window + staggered pools
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --maintenance-window-start "2024-01-06T02:00:00Z" \
    --maintenance-window-end "2024-01-08T10:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Disruption budget to prevent back-to-back upgrades
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --maintenance-minor-version-disruption-interval=1209600s  # 14 days between minor upgrades
```

**Key insight:** At 3,000+ nodes, you're beyond what a single 8-hour window can handle. Either extend windows to 48+ hours OR split the cluster. The staggered pool approach is your immediate path forward while planning longer-term architecture changes.