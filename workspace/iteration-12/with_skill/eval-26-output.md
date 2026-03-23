# GKE 1.30 End of Support Impact Analysis

## What happens at EoS for each cluster type

### Regular channel clusters (3 clusters)
**What happens:** Automatic force-upgrade to 1.31 (next supported minor version)
- Control plane upgrades first, then all node pools
- Respects maintenance windows but ignores most maintenance exclusions
- Only "no upgrades" exclusions can temporarily defer (max 30 days)
- Upgrade follows your configured surge settings

### Extended channel clusters (2 clusters) 
**What happens:** **No immediate action** — you're protected
- Extended support continues until **up to 24 months** from 1.30's original release
- You have additional time to plan and execute upgrades on your schedule
- Only security patches are auto-applied; minor upgrades remain manual
- Extra cost applies only during the extended support period (after standard EoS)

### Legacy "No channel" cluster (1 cluster)
**What happens:** Systematic force-upgrade enforcement
- Control plane: Auto-upgraded to 1.31
- Node pools: Force-upgraded even if "no auto-upgrade" is configured
- Only the 30-day "no upgrades" exclusion can defer temporarily
- **This is the most disruptive scenario** — you have the least control

## Preparation options by cluster type

### For Regular channel clusters (immediate action needed)

**Option 1: Let auto-upgrade happen (easiest)**
```bash
# Set maintenance windows for predictable timing
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2025-02-01T02:00:00Z" \
  --maintenance-window-end "2025-02-01T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Configure appropriate surge settings for each node pool
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

**Option 2: Manual upgrade before EoS (more control)**
```bash
# Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.31.3-gke.1146000

# Then upgrade node pools with skip-level (1.30 → 1.31 directly)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.3-gke.1146000
```

**Option 3: Temporary deferral (emergency only)**
```bash
# 30-day "no upgrades" exclusion - buys time but not a long-term solution
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "eos-defer" \
  --add-maintenance-exclusion-start-time "2025-01-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-02-14T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

### For Extended channel clusters (you have time)

**Recommended: Plan manual upgrades during your next maintenance cycle**
- You're protected from force-upgrade until end of extended support
- Plan to upgrade to 1.31+ in the next 3-6 months on your schedule
- Remember: minor version upgrades are manual on Extended channel

```bash
# Check your current auto-upgrade target (should show no minor target)
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# When ready, manually upgrade:
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.31.3-gke.1146000
```

### For legacy "No channel" cluster (highest priority)

**Strongly recommend: Migrate to a release channel first**
```bash
# Option A: Migrate to Regular channel (closest to current behavior)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular

# Option B: Migrate to Extended channel (maximum flexibility)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

**Why migrate first:**
- "No channel" has the most limited upgrade control tools
- Missing key exclusion types like "no minor or node upgrades"  
- Force-upgrade behavior is more aggressive
- You'll get better control by moving to a release channel + exclusions

## Pre-upgrade checklist for all clusters

```
1.30 → 1.31 Upgrade Preparation
- [ ] Review GKE 1.31 release notes for breaking changes
- [ ] Check for deprecated API usage (most common upgrade failure):
      `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated`
- [ ] Verify PDBs are not overly restrictive (allow some disruption)
- [ ] Ensure all workloads have controllers (no bare pods)
- [ ] Test third-party operators/controllers against 1.31
- [ ] Back up StatefulSet persistent volumes
- [ ] Configure monitoring to capture baseline metrics before upgrade
```

## Timeline recommendations

**Immediate (next 2 weeks):**
1. Migrate the "No channel" cluster to Extended or Regular channel
2. Set maintenance windows on Regular channel clusters
3. Begin testing 1.31 in dev/staging environments

**Within 1 month:**
4. Manually upgrade Regular channel clusters during planned maintenance windows
5. Update monitoring and alerting for the new version

**Within 3 months:**
6. Plan Extended channel cluster upgrades for your next maintenance cycle

## Monitoring EoS dates

```bash
# Check current EoS timeline for each cluster
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Look for these fields in output:
# - endOfStandardSupportTimestamp  
# - endOfExtendedSupportTimestamp (Extended channel only)
# - autoUpgradeTarget (what version it will upgrade to)
```

**Bottom line:** Your Extended channel clusters are protected and give you time to plan. Your Regular channel clusters need immediate attention. The "No channel" cluster should be migrated to a release channel immediately for better upgrade control.