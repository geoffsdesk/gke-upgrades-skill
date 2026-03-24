# Extended Release Channel Migration Plan

## Extended Channel Overview

Extended channel provides **up to 24 months of support** (vs 14 months on Regular/Stable) but comes with important behavioral changes:

### Key Differences from Regular Channel

| Aspect | Regular Channel | Extended Channel |
|--------|----------------|------------------|
| **Minor version auto-upgrades** | ✅ Automatic | ❌ **Manual only** (except at end of extended support) |
| **Patch auto-upgrades** | ✅ Automatic | ✅ Automatic |
| **Support period** | 14 months | Up to 24 months |
| **Extra cost** | None | **Only during extended period** (months 15-24) |
| **Version availability** | Same as Regular | Same as Regular |

**Critical behavior change:** On Extended channel, **you must manually trigger minor version upgrades** (1.31→1.32, 1.32→1.33, etc.). Only patches are auto-applied. This shifts operational responsibility to your team.

## Migration Path & Compatibility Check

**Good news:** Your current 1.31 version is compatible with Extended channel (Extended supports versions 1.27+).

### Pre-Migration Verification
```bash
# Check current version and channel
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="value(currentMasterVersion,releaseChannel.channel)"

# Verify 1.31 availability in Extended channel
gcloud container get-server-config --region REGION \
  --format="yaml(channels.EXTENDED)"
```

## Migration Steps

### 1. Apply Maintenance Exclusion (Recommended)
Apply a temporary "no upgrades" exclusion before switching to prevent unexpected auto-upgrades immediately after the channel change:

```bash
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name="channel-migration" \
  --add-maintenance-exclusion-start="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-end="$(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-scope=no_upgrades
```

### 2. Switch to Extended Channel
```bash
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel=extended
```

### 3. Configure Maintenance Controls
Set up maintenance windows and persistent exclusions for production control:

```bash
# Set maintenance window (example: Saturdays 2-6 AM UTC)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-window-start "2026-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Add persistent "no minor or node upgrades" exclusion
# This allows CP patches but requires manual minor upgrades
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name="production-control" \
  --add-maintenance-exclusion-scope=no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

### 4. Remove Temporary Exclusion
```bash
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --remove-maintenance-exclusion="channel-migration"
```

## Operational Changes Required

### 1. Manual Minor Version Upgrade Process
You'll need to establish a process for planning and executing minor upgrades:

```bash
# Check available versions
gcloud container get-server-config --region REGION \
  --format="yaml(channels.EXTENDED)"

# When ready to upgrade minor version (e.g., 1.31 → 1.32)
# Control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version=1.32.x-gke.xxx

# Then node pools
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version=1.32.x-gke.xxx
```

### 2. Proactive Planning Schedule
- **Quarterly reviews:** Check for new minor versions and plan upgrade timing
- **Security patches:** Still automatic, but monitor for critical patches that might accelerate minor upgrade needs
- **EoS tracking:** Extended support ends at 24 months - plan the next minor upgrade before then

## Cost Implications

| Time Period | Cost |
|-------------|------|
| **Months 1-14** (standard support) | **No extra cost** - same as Regular channel |
| **Months 15-24** (extended support) | **Additional charge per cluster** |

**Cost optimization:** You only pay extra during the extended period. If you upgrade to newer minors within the 14-month standard support window, there's no additional cost.

## Recommended Production Configuration

For maximum control while maintaining security:

```bash
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel=extended \
  --add-maintenance-exclusion-scope=no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --maintenance-patch-version-disruption-interval=90d \
  --maintenance-window-start "2026-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

This gives you:
- ✅ Extended 24-month support
- ✅ Automatic security patches (limited to once per 90 days)
- ✅ Manual control over minor and node upgrades  
- ✅ Predictable maintenance windows

## Migration Checklist

```
Extended Channel Migration
- [ ] Current version 1.31 confirmed compatible with Extended channel
- [ ] Temporary "no upgrades" exclusion applied
- [ ] Channel switched to Extended
- [ ] Maintenance window configured for patch-only upgrades
- [ ] Persistent "no minor or node upgrades" exclusion added
- [ ] Temporary migration exclusion removed
- [ ] Team process established for manual minor upgrades
- [ ] Quarterly minor version review schedule created
- [ ] Cost implications communicated to stakeholders
- [ ] Documentation updated for new operational model
```

## Key Tradeoffs Summary

**Benefits:**
- 24-month support window reduces upgrade pressure
- Still get automatic security patches
- Maximum control over disruptive changes
- Ideal for compliance/regulated environments

**Considerations:**
- Extra cost during months 15-24
- Manual minor upgrades become your operational responsibility
- Need proactive planning to avoid EoS enforcement at 24 months
- Team must track Kubernetes deprecations across longer cycles

Extended channel is excellent for production environments that prioritize stability and want maximum control over when disruptive changes happen, while still maintaining security posture through automatic patches.