# Extended Release Channel Migration Plan

## Extended Channel Overview & Tradeoffs

### Benefits of Extended Channel
- **Extended support period:** Up to 24 months (vs 14 months on Regular)
- **Cost only during extended period:** No extra charges during standard 14-month support
- **Control plane minor upgrade control:** Minor versions are NOT auto-upgraded (except at end of extended support)
- **Same patch timing as Regular:** Security patches arrive at Regular channel speed - no delay
- **Full SLA coverage:** Same reliability guarantees as Regular/Stable

### Key Tradeoffs & Considerations

**⚠️ Manual minor version management required:**
- Extended channel does NOT auto-upgrade the control plane to new minor versions
- You must plan and initiate control plane minor upgrades manually
- Node versions still follow the control plane minor version automatically (unless blocked by exclusions)

**Patch behavior (same as Regular):**
- Security patches are auto-applied at Regular channel timing
- No delay compared to Regular - patches flow through immediately

**Cost structure:**
- **Standard support period (months 1-14):** No additional cost
- **Extended support period (months 15-24):** Additional cost applies
- Only versions 1.27+ are eligible for extended support

**Version availability constraint:**
- If your current version (1.31) isn't available in Extended channel yet, your cluster will be "ahead of channel"
- You won't receive auto-upgrades until Extended channel reaches 1.31
- Check current Extended channel versions before migrating

## Migration Steps

### 1. Pre-migration checks

```bash
# Check current cluster state
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, releaseChannel.channel)"

# Check Extended channel version availability
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels.EXTENDED)"
```

**Version compatibility check:** Verify 1.31 is available in Extended channel. If not, you have two options:
- Wait until Extended channel reaches 1.31
- Downgrade to the latest Extended-supported version first

### 2. Apply temporary upgrade exclusion (recommended)

```bash
# Prevent auto-upgrades during channel transition
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades
```

### 3. Migrate to Extended channel

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

### 4. Configure ongoing maintenance policy

Since Extended doesn't auto-upgrade minor versions, configure your preferred maintenance approach:

**Option A - Maximum control (recommended for compliance environments):**
```bash
# Allow patches only, block minor and node upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "minor-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Option B - Allow node upgrades with manual minor control:**
```bash
# Block minor upgrades only, allow patches and node upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "minor-control" \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

### 5. Set maintenance windows for patches

```bash
# Configure maintenance window for patch auto-upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### 6. Remove temporary exclusion

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion "channel-migration"
```

### 7. Verify configuration

```bash
# Confirm Extended channel enrollment
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel)"

# Check maintenance exclusions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy)"
```

## Ongoing Operations on Extended Channel

### Minor Version Upgrade Process
When you're ready to upgrade to a new minor version:

```bash
# 1. Check available versions
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels.EXTENDED)"

# 2. Upgrade control plane (manual)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# 3. Node pools will auto-upgrade to match (unless blocked by exclusions)
```

### Patch Management
- Patches auto-apply during maintenance windows
- No action required for patch updates
- Same timing as Regular channel

## Alternative: Extended Channel for Maximum Control

For ultimate upgrade control in production environments:

```bash
# Complete control configuration
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --maintenance-patch-version-disruption-interval=7776000s \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

This gives you:
- 24-month support lifecycle
- Manual control over minor AND node upgrades  
- Patches limited to once every 90 days
- Patches only during Saturday 2-6 AM window

## Migration Timeline

1. **Immediate:** Apply temporary exclusion and migrate channel (~5 minutes)
2. **Within 7 days:** Configure maintenance policy and remove temporary exclusion
3. **Ongoing:** Manual minor version upgrades as needed
4. **Month 15-24:** Extended support cost applies (for versions that reach extended period)

## Recommendations

- **Use Option A** (no minor or node upgrades exclusion) for maximum control
- **Test in dev/staging first** with the same Extended channel configuration
- **Monitor GKE release schedule** for minor version availability in Extended
- **Plan minor upgrades** during scheduled maintenance windows
- **Consider rollout sequencing** if you have multiple clusters to orchestrate upgrades

The Extended channel is ideal for your production environment - you get 24-month support with manual control over disruptive upgrades while still receiving timely security patches.