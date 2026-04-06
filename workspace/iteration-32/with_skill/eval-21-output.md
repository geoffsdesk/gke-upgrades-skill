# Extended Release Channel Migration Plan

## Extended Channel Overview

Extended channel provides up to **24 months of support** for Kubernetes versions 1.27+ (vs. 14 months on Regular/Stable). Here are the key tradeoffs:

### Benefits
- **Extended support period**: Up to 24 months vs. 14 months standard
- **No automatic minor version upgrades**: Control plane minor upgrades are manual (except at end of extended support)
- **Maximum flexibility around EoS enforcement**: Delays forced upgrades until end of extended support
- **Same patch timing as Regular**: Security patches arrive at the same cadence, no delay
- **Full SLA coverage**: Same reliability guarantees as Regular/Stable channels

### Tradeoffs
- **Additional cost**: Only during the extended support period (months 15-24). No extra cost during standard support (months 1-14)
- **Manual minor upgrade responsibility**: You must plan and initiate control plane minor upgrades yourself
- **Node auto-upgrade behavior**: Nodes still auto-upgrade to follow the control plane minor version unless blocked by exclusions
- **Rollout sequencing incompatible**: Can't orchestrate upgrades across fleets with different channels

## Migration Strategy

Since you're currently on Regular at 1.31, here's the recommended approach:

### Option 1: Direct Migration (Recommended)
```bash
# Check if 1.31 is available in Extended channel first
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels.EXTENDED.validVersions)"

# If 1.31 is available in Extended, migrate directly
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

### Option 2: If 1.31 Not Yet in Extended
If 1.31 isn't available in Extended yet, you have two choices:

**Wait for 1.31 to reach Extended** (recommended):
- Monitor the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule)
- Switch once 1.31 becomes available in Extended

**Or downgrade first** (more complex):
```bash
# Downgrade to a version available in Extended (e.g., 1.30)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30.X-gke.X

# Then migrate to Extended
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

## Migration Precautions

### Prevent Unexpected Upgrades
Apply a temporary exclusion before switching channels to control timing:

```bash
# Add temporary "no upgrades" exclusion during migration
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-start YYYY-MM-DDTHH:MM:SSZ \
  --add-maintenance-exclusion-end YYYY-MM-DDTHH:MM:SSZ \
  --add-maintenance-exclusion-scope no_upgrades

# Switch channel
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended

# Remove exclusion when ready
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion "channel-migration"
```

## Recommended Extended Channel Configuration

For maximum production control, combine Extended channel with maintenance controls:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --maintenance-patch-version-disruption-interval=7776000s \
  --maintenance-window-start "2024-12-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

This configuration provides:
- **24-month support** with manual minor version control
- **Auto-applied security patches** only (no minor or node auto-upgrades)
- **Patches limited to once every 90 days** within Saturday 2-6 AM maintenance window
- **Manual control over minor upgrades** when you're ready

## Operational Changes

### What Changes
- **Minor upgrades become manual**: Plan and trigger them yourself
- **Node pool behavior**: Nodes will still auto-upgrade to match the control plane minor version unless blocked by exclusions
- **Patch behavior**: Remains automatic at Regular channel timing
- **Cost**: Additional charges only during extended support period (months 15-24)

### What Stays the Same
- **Patch auto-upgrades**: Continue automatically
- **Maintenance windows**: Still respected
- **Cluster reliability**: Same SLA as Regular channel
- **Node pool management**: Same upgrade strategies available

## Timeline Planning

1. **Now**: Migrate to Extended channel (if 1.31 available)
2. **Month 14-15**: Extended support period begins, additional cost starts
3. **Month 24**: End of extended support, must upgrade or face forced upgrade
4. **Ongoing**: Manual minor upgrades when new features needed or approaching EoS

## Multi-Cluster Considerations

If you have dev/staging/prod environments:

**Option A: All Extended** (Maximum control)
- All environments on Extended channel
- Use maintenance exclusions to control upgrade timing
- Cannot use rollout sequencing (requires same channel)

**Option B: Mixed channels** (Natural progression)
- Dev: Regular channel
- Prod: Extended channel  
- Dev gets versions first, validate, then manually upgrade prod
- Cannot use automated rollout sequencing

## Verification Commands

After migration:
```bash
# Confirm channel change
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel)"

# Check auto-upgrade behavior
gcloud container clusters get-upgrade-info CLUSTER_NAME \
  --region REGION

# Verify maintenance configuration
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy)"
```

## Next Steps

1. **Verify 1.31 availability** in Extended channel for your region
2. **Plan migration timing** during a maintenance window
3. **Configure maintenance exclusions** if you want maximum control
4. **Update operational procedures** to include manual minor upgrade planning
5. **Monitor costs** starting at month 15 of version lifecycle

The Extended channel is ideal for your production use case - it gives you the 24-month support window while maintaining security patch automation. The manual minor upgrade requirement actually aligns well with production change control processes.