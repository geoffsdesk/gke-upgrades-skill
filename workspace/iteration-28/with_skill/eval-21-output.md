# Extended Release Channel Migration Plan

## Extended Channel Overview

The Extended release channel provides up to **24 months of support** for Kubernetes versions 1.27+ (vs. 14 months for Regular/Stable). Here are the key tradeoffs:

### Benefits
- **Extended support period**: Up to 24 months vs. 14 months standard
- **Manual control over minor upgrades**: Control plane minor versions are NOT auto-upgraded (except at end of extended support)
- **Same patch timing as Regular**: Security patches arrive at the same cadence as Regular channel
- **Migration path from "No channel"**: Recommended for customers wanting maximum flexibility around EoS enforcement
- **Cost only during extended period**: No extra charge during the standard 14-month support period

### Tradeoffs
- **Additional cost**: Only applies during months 15-24 of extended support
- **Manual minor upgrade responsibility**: You must plan and initiate control plane minor upgrades yourself
- **Node pools still follow control plane**: Node auto-upgrades track the control plane's minor version unless blocked by exclusions
- **Requires active management**: Not fully "hands-off" like Regular channel

## Migration Steps

### 1. Pre-migration checks

```bash
# Verify current version is available in Extended channel
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels.EXTENDED)"

# Check current cluster state
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, releaseChannel.channel, nodePools[].version)"
```

**⚠️ Critical**: Version 1.31 should be available in Extended channel, but verify before proceeding. If it's not available yet, your cluster will be "ahead of channel" and won't receive auto-upgrades until Extended catches up to 1.31.

### 2. Apply temporary upgrade exclusion (recommended)

```bash
# Prevent auto-upgrades immediately after channel switch
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time $(date -u -d "+7 days" +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_upgrades
```

### 3. Switch to Extended channel

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

### 4. Configure maintenance controls for Extended

Since Extended doesn't auto-upgrade minor versions, consider your node upgrade strategy:

**Option A: Maximum control (recommended)**
```bash
# Block node minor upgrades to prevent version skew
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --remove-maintenance-exclusion-name "channel-migration"
```

**Option B: Allow node patch upgrades only**
```bash
# Allow nodes to get patches but not minor versions
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --remove-maintenance-exclusion-name "channel-migration"
```

### 5. Set maintenance window for patches

```bash
# Control when patches are applied
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Operational Model on Extended Channel

### What happens automatically:
- ✅ **Control plane patches**: Applied automatically within maintenance windows
- ✅ **Node patches**: Applied if no "node upgrade" exclusion is active
- ✅ **Security updates**: Same timing as Regular channel

### What requires manual action:
- ⚠️ **Control plane minor upgrades**: You initiate when ready
- ⚠️ **Planning for EoS**: Monitor when extended support ends
- ⚠️ **Node minor upgrades**: If using "no minor or node" exclusions

### Recommended workflow:

1. **Monitor new minor versions** via [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule)
2. **Test in staging** when new minor becomes available
3. **Manually upgrade control plane** during planned maintenance windows:
   ```bash
   gcloud container clusters upgrade CLUSTER_NAME \
     --zone ZONE \
     --master \
     --cluster-version NEW_MINOR_VERSION
   ```
4. **Upgrade node pools** after control plane validation

## Cost Implications

- **Months 1-14**: No additional cost (same as Regular channel)
- **Months 15-24**: Additional cost for extended support
- **Billing**: Charged per cluster-month during extended period

The cost is reasonable for production clusters where stability and controlled upgrade timing outweigh the incremental expense.

## Migration Timeline

**Immediate** (after channel switch):
- Patches continue automatically
- Minor versions require manual trigger

**15 months from now** (when standard support ends):
- Extended support billing begins
- Still no forced minor upgrades

**24 months from now** (end of extended support):
- Must upgrade to supported version or migrate to newer minor

## Alternative: Stay on Regular with Controls

If the manual minor upgrade responsibility seems burdensome, consider staying on Regular with tight controls:

```bash
# Stay on Regular but control minor upgrades manually
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

This gives you 14-month support with manual minor upgrade control, avoiding the Extended channel complexity and cost.

## Recommendation

**Proceed with Extended channel migration** if:
- You want maximum time on each minor version (24 months)
- Your team can handle manual minor upgrade planning
- The extended support cost is acceptable for production stability

**Consider staying on Regular** if:
- 14 months of support is sufficient
- You prefer fully automated minor upgrades
- You want to minimize operational overhead

The Extended channel is particularly valuable for regulated environments (financial services, healthcare) where change control processes make frequent minor upgrades challenging.