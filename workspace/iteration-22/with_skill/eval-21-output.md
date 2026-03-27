# Extended Release Channel Migration Plan

## Current State Assessment
- **Current**: Regular channel, GKE 1.31
- **Target**: Extended channel for 24-month support
- **Cluster type**: Production

## Extended Channel Tradeoffs

### Benefits
- **Up to 24 months support** (vs 14 months on Regular)
- **Maximum control over minor upgrades** - only patches auto-apply, minor upgrades are manual-only (except at end of extended support)
- **Same SLA as Regular/Stable** during standard support period
- **Cost-effective compliance path** - extended cost only applies during months 15-24

### Limitations & Considerations
- **Manual minor upgrade responsibility** - you must plan and execute minor upgrades proactively, they don't happen automatically
- **Additional cost during extended period** - extra charges apply only during months 15-24 of version lifecycle
- **Same patch cadence as Regular** - you still get security patches automatically
- **Version availability dependency** - 1.31 must be available in Extended before you can migrate

## Migration Process

### Pre-Migration Checks

```bash
# 1. Verify 1.31 is available in Extended channel
gcloud container get-server-config --zone YOUR_ZONE \
  --format="yaml(channels.EXTENDED.validVersions)" | grep "1.31"

# 2. Check current cluster status
gcloud container clusters describe CLUSTER_NAME \
  --zone YOUR_ZONE \
  --format="table(name, currentMasterVersion, releaseChannel.channel)"
```

### Migration Steps

```bash
# 1. Apply temporary "no upgrades" exclusion (prevent auto-upgrade during migration)
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-start $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end $(date -u -d "+7 days" +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_upgrades

# 2. Migrate to Extended channel
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --release-channel extended

# 3. Configure maintenance controls for Extended
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "manual-minor-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# 4. Remove temporary migration exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --remove-maintenance-exclusion-name "channel-migration"

# 5. Verify migration
gcloud container clusters describe CLUSTER_NAME \
  --zone YOUR_ZONE \
  --format="value(releaseChannel.channel)"
```

## Post-Migration Operating Model

### What Happens Automatically
- **Patches continue auto-applying** within your current minor version (1.31.x)
- **Maintenance windows still control timing** of patch upgrades
- **24-month support clock starts** from when 1.31 first appeared in Extended

### What Becomes Manual
- **Minor version upgrades** (1.31 → 1.32 → 1.33) require manual initiation
- **Proactive planning needed** - monitor GKE release schedule for EoS dates
- **Coordination with maintenance windows** for manual upgrades

### Recommended Extended Channel Configuration

```bash
# Full production-ready Extended setup
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --release-channel extended \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA" \
  --maintenance-patch-version-disruption-interval 2592000s  # 30 days between patches
```

This gives you:
- Extended support (24 months)
- Auto-applied security patches only (no minor/node auto-upgrades)  
- Saturday 2-6 AM maintenance window
- Minimum 30 days between patch upgrades
- Manual control over when minor upgrades happen

## Key Operational Changes

### Planning Process
1. **Monitor GKE release schedule** for version EoS dates
2. **Plan minor upgrades 2-3 months before EoS** of your current version
3. **Test in dev/staging** before production minor upgrades
4. **Budget for extended support costs** during months 15-24

### Manual Minor Upgrade Process
```bash
# When ready to upgrade minor version (e.g., 1.31 → 1.32)
# 1. Control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone YOUR_ZONE \
  --master \
  --cluster-version 1.32.x-gke.xxxx

# 2. Then node pools (skip-level within 2-minor-version skew when possible)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone YOUR_ZONE \
  --cluster-version 1.32.x-gke.xxxx
```

## Cost Implications

- **Months 1-14**: Same cost as Regular channel (no premium)
- **Months 15-24**: Additional Extended support fee applies
- **Cost only during extended period** - you're not paying extra during standard support

## Alternative: Enhanced Regular Channel Control

If you want similar control without Extended channel complexity:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --release-channel regular \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

This gives you:
- Automatic patches AND node pool upgrades
- Manual minor version control
- 14-month support (vs 24-month Extended)
- No extended support costs

## Recommendation

✅ **Proceed with Extended channel** if:
- You need 24-month support for compliance/change management
- You're comfortable with manual minor upgrade responsibility  
- You want maximum control over disruptive changes

⚠️ **Consider Regular + "no minor" exclusion** if:
- 14-month support is sufficient
- You want automatic node pool upgrades
- You want to avoid extended support costs

The Extended channel is ideal for your production use case - it provides the longest support window while maintaining security patch automation.