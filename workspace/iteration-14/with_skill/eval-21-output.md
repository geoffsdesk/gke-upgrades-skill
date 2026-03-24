# Extended Release Channel Migration Plan

## Current State Analysis
- **Current:** Regular channel at 1.31
- **Target:** Extended channel for 24-month support
- **Key consideration:** 1.31 is supported on Extended channel ✅

## Extended Channel Tradeoffs

### Benefits
- **Extended support period:** Up to 24 months vs 14 months standard
- **Reduced upgrade frequency:** Minor upgrades are NOT automated (except at end of extended support)
- **Maximum flexibility around EoS:** Delays EoS enforcement until end of extended support
- **Full SLA coverage:** Same reliability guarantees as Regular/Stable
- **Better compliance fit:** Slower change cycles for regulated environments

### Tradeoffs to Consider
- **Additional cost:** Extra charges apply ONLY during months 15-24 of support (no cost during standard 14-month period)
- **Manual minor upgrade responsibility:** You must plan and execute minor upgrades yourself — they won't happen automatically
- **Patch-only auto-upgrades:** Only patches are auto-applied; minor versions require user initiation
- **Operational overhead:** Need internal processes to track and schedule minor upgrades before extended support expires

### Cost Impact
```
Months 1-14: No additional cost (standard support period)
Months 15-24: Additional cost per cluster during extended period only
```

## Migration Process

### Pre-Migration Checks
```bash
# Verify 1.31 availability in Extended channel
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels.EXTENDED)"

# Check current cluster state
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, releaseChannel.channel)"
```

### Migration Command
```bash
# Switch to Extended channel
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended

# Verify migration
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel)"
```

### Post-Migration Configuration

**Set up maintenance exclusions for maximum control:**
```bash
# Block minor upgrades, allow patches (recommended pattern)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades" \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

This creates a persistent exclusion that:
- Allows security patches (recommended)
- Blocks minor version auto-upgrades
- Automatically tracks EoS and renews when you do manual minor upgrades

## Operational Model on Extended Channel

### What Happens Automatically
- ✅ Security patches applied during maintenance windows
- ✅ Node pool patches (respects maintenance windows/exclusions)
- ✅ Standard 14-month support lifecycle

### What You Must Manage
- 🔧 **Minor version upgrades:** Plan and execute before extended support expires
- 🔧 **Version tracking:** Monitor when your current minor version approaches end of extended support
- 🔧 **Upgrade planning:** Schedule minor upgrades during low-traffic periods

### Recommended Workflow
1. **Quarterly review:** Check version support timeline
2. **Annual minor upgrade:** Plan 1-2 minor version bumps per year
3. **Extended support utilization:** Use months 15-24 for gradual upgrade planning, not emergency catch-up

## Multi-Environment Strategy

**Recommended approach with Extended channel:**
```
Dev/Staging: Regular channel (gets updates first for testing)
Production: Extended channel (controlled minor upgrades)
```

**Upgrade flow:**
1. Dev/staging automatically receives new minor versions via Regular channel
2. Validate new versions in dev/staging for 2-3 months
3. Manually upgrade production to validated version using Extended channel flexibility

## Migration Timeline

```bash
# Immediate (safe to execute now)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended

# Result: 1.31 on Extended channel
# - Continues receiving patches automatically  
# - No minor auto-upgrades
# - 24-month support clock starts from when 1.31 was released
```

## Monitoring and Alerts

Set up tracking for Extended channel clusters:

```bash
# Check auto-upgrade status
gcloud container clusters get-upgrade-info CLUSTER_NAME \
  --region ZONE

# Monitor end of extended support timeline
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(autopilot.endOfExtendedSupportTimestamp)"
```

**Recommended alerts:**
- End of extended support 90 days out
- New minor versions available for manual upgrade
- Patch upgrade failures

## Summary Recommendation

✅ **Migrate to Extended channel** — good fit for your production use case:
- 1.31 is available, so migration is seamless
- Gives you 24-month runway for 1.31
- Patches continue automatically (security maintained)
- You control minor upgrade timing

The operational trade-off (manual minor upgrades) aligns well with production stability requirements. The additional cost only applies during the extended period (months 15-24), giving you time to plan.

**Next steps:**
1. Migrate to Extended channel (safe, immediate)
2. Add "no minor upgrades" maintenance exclusion
3. Establish quarterly version planning process
4. Set up EoS monitoring alerts