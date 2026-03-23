# Extended Release Channel Migration Plan

## Extended Channel Overview

The Extended release channel provides **24-month support** (vs. 14 months for Regular/Stable) for versions 1.27+ with additional cost during the extended support period.

### Key Tradeoffs

| Feature | Regular Channel | Extended Channel |
|---------|----------------|-----------------|
| **Support duration** | 14 months | Up to 24 months |
| **Version availability** | Same as Regular timing | Same as Regular timing |
| **Auto-upgrade behavior** | Patches + minors automated | **Patches only** automated during extended period |
| **Minor version upgrades** | Automated throughout lifecycle | **Manual required** during extended support (months 15-24) |
| **Cost** | Standard | **Additional charge during extended period only** (months 15-24) |
| **SLA** | Full SLA | Full SLA |
| **EoS enforcement** | At 14 months | Delayed until end of extended support (24 months) |

### Critical Considerations

**1. Manual minor upgrades required**
- During extended support period (months 15-24), minor version upgrades are **NOT automated**
- Your team must plan and execute minor upgrades proactively
- Only security patches continue to auto-apply
- This adds operational overhead vs. Regular channel's full automation

**2. Cost impact**
- No additional cost during standard support period (months 1-14)  
- Additional charges apply only during extended period (months 15-24)
- Cost varies by cluster size and usage

**3. Version progression**
- Extended gets the same versions at the same time as Regular
- The difference is how long each version stays supported, not when it arrives

## Migration Steps

### 1. Pre-flight checks
```bash
# Verify current version and channel
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="table(name, currentMasterVersion, releaseChannel.channel)"

# Check if version 1.31 supports Extended (yes, 1.27+ supported)
gcloud container get-server-config --region REGION \
  --format="yaml(channels.EXTENDED)"
```

### 2. Switch to Extended channel
```bash
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel extended
```

### 3. Configure maintenance controls (recommended)
```bash
# Add "no minor or node upgrades" exclusion for maximum control
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "prod-minor-control" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Set maintenance window for patch timing
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-window-start "2024-01-01T02:00:00Z" \
  --maintenance-window-end "2024-01-01T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Recommended Strategy

### Option A: Extended + Manual Minor Control (Recommended)
- Switch to Extended channel
- Use "no minor or node upgrades" exclusion to block automated minor upgrades
- Plan manual minor upgrades during scheduled maintenance windows
- Let security patches auto-apply within maintenance windows
- Benefits: Maximum control, 24-month support, predictable upgrade timing

### Option B: Extended + Automated (months 1-14 only)  
- Switch to Extended channel
- Accept automated minor upgrades during standard support period
- Switch to manual control when entering extended support period (months 15-24)
- Benefits: Less initial overhead, but requires process change mid-lifecycle

## Operational Considerations

### Process Changes Required
1. **Upgrade planning:** Establish quarterly minor upgrade reviews during extended support
2. **Monitoring:** Track version EoS dates more closely since you'll stay on versions longer
3. **Testing:** Maintain staging environment on Regular channel to validate upcoming versions
4. **Cost tracking:** Monitor additional Extended channel costs during months 15-24

### Multi-environment Strategy
```
Dev/Staging: Regular channel (gets versions early for testing)
Production: Extended channel (24-month support, manual minor control)
```

This allows you to test upcoming versions in dev/staging while maintaining maximum stability and support duration in production.

## Validation After Migration

```bash
# Confirm channel migration
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="value(releaseChannel.channel)"

# Check maintenance exclusions applied
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="table(maintenancePolicy.window.maintenanceExclusions[].name,maintenancePolicy.window.maintenanceExclusions[].scope)"

# Verify auto-upgrade target (should respect exclusions)
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

## Summary

Extended channel is ideal for your production clusters if you:
- ✅ Want 24-month support to reduce upgrade frequency
- ✅ Can handle manual minor upgrade planning during extended period  
- ✅ Are comfortable with additional cost during months 15-24
- ✅ Value predictable, controlled upgrade timing over full automation

The migration itself is straightforward - the operational process changes during extended support are the main consideration.