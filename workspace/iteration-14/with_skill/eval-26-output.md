# GKE 1.30 End of Support Impact & Preparation Plan

## EoS Enforcement by Cluster Type

### Regular Channel Clusters (3 clusters)
**What happens:** When 1.30 reaches EoS in the Regular channel, these clusters will be **automatically upgraded** to the next supported minor version (likely 1.31). Both control plane and all node pools will be upgraded together according to your cluster-level maintenance policies.

**Timing:** Regular channel clusters follow standard EoS enforcement - upgrades occur when the version is no longer supported in the channel.

**Your control:** Maintenance windows and exclusions are respected, but the upgrade will eventually happen. You cannot permanently avoid it.

### Extended Channel Clusters (2 clusters)
**What happens:** These clusters will **continue running 1.30** beyond the standard EoS date. Extended channel provides up to 24 months of support for versions 1.27+, so your 1.30 clusters can stay on that version much longer.

**Key difference:** Minor version upgrades on Extended channel are **NOT automated** (except at the very end of extended support). You must manually initiate minor upgrades when you're ready.

**Cost impact:** Extended support incurs additional charges only during the extended period (after standard EoS). No extra cost during the standard support window.

### Legacy "No Channel" Cluster (1 cluster)
**What happens:** This cluster will face **systematic EoS enforcement**. When 1.30 reaches EoS:
- Control plane: Force-upgraded to next supported minor version
- Node pools: Force-upgraded even if auto-upgrade is disabled

**Critical limitation:** Your "No channel" cluster has very limited options to defer this upgrade - only the 30-day "no upgrades" exclusion can temporarily delay enforcement.

## Preparation Options by Cluster

### For Regular Channel Clusters

**Option 1: Let auto-upgrade happen (recommended)**
```bash
# Ensure maintenance windows are configured for off-peak hours
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-02-04T02:00:00Z" \
  --maintenance-window-end "2024-02-04T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Option 2: Control the timing with maintenance exclusions**
```bash
# Block all upgrades during critical business periods (max 30 days)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "holiday-freeze" \
  --add-maintenance-exclusion-start-time "2024-11-20T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-15T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# Or allow patches but block minor upgrades (up to EoS)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "minor-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Option 3: Proactive manual upgrade**
```bash
# Upgrade before auto-upgrade kicks in
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.xxxx
```

### For Extended Channel Clusters

**Option 1: Stay on 1.30 longer (recommended)**
- No action required - clusters will continue running 1.30
- Monitor the extended support end date
- Plan manual upgrade when ready

**Option 2: Proactive upgrade to 1.31+**
```bash
# Manual upgrade when you choose
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.xxxx
```

### For Legacy "No Channel" Cluster

**Option 1: Migrate to Extended channel (recommended)**
```bash
# Move to Extended for maximum flexibility around EoS
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```
⚠️ **Warning:** If your current 1.30 version isn't yet available in Extended, your cluster will be "ahead of channel" and won't receive auto-upgrades until Extended catches up.

**Option 2: Migrate to Regular channel**
```bash
# Move to Regular (similar to current behavior but with better tools)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular
```

**Option 3: Apply 30-day "no upgrades" exclusion**
```bash
# Temporary deferral only - not a long-term solution
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "eos-delay" \
  --add-maintenance-exclusion-start-time "START_TIME" \
  --add-maintenance-exclusion-end-time "END_TIME" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Recommended Action Plan

### Immediate Actions

1. **Check current 1.30 EoS timeline:**
```bash
# Check auto-upgrade status and EoS dates for each cluster
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

2. **Migrate the "No channel" cluster:**
```bash
# Move to Extended channel for maximum control
gcloud container clusters update NO_CHANNEL_CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

### Short-term Strategy

**Regular channel clusters:**
- Configure maintenance windows for predictable upgrade timing
- Add "no minor or node upgrades" exclusions if you want to control exactly when the upgrade happens
- Plan to manually trigger upgrades during your preferred maintenance window

**Extended channel clusters:**
- Monitor extended support timeline
- Plan manual upgrades for a future maintenance window when convenient
- Take advantage of the flexibility to upgrade on your schedule

**Former "No channel" cluster:**
- After migrating to Extended, treat it like your other Extended clusters
- Configure proper maintenance exclusions using the more powerful tools now available

### Long-term Recommendations

1. **Standardize on Extended channel** for production clusters that need maximum upgrade control
2. **Use Regular channel** for dev/staging environments that can tolerate automatic upgrades
3. **Never use "No channel"** for new clusters - it lacks the advanced maintenance exclusion features

## Key Differences Summary

| Cluster Type | EoS Behavior | Your Control | Cost Impact |
|-------------|-------------|-------------|------------|
| **Regular (3)** | Auto-upgrade to 1.31 | Maintenance windows + exclusions | None |
| **Extended (2)** | Stay on 1.30 longer | Manual upgrades only | Additional cost during extended period |
| **No channel (1)** | Force-upgrade with limited options | Very limited (30-day exclusion only) | None |

The Extended channel clusters give you the most flexibility, while the "No channel" cluster is the most constrained. Migrating that legacy cluster to a release channel should be your top priority.