# Extended Release Channel Migration Plan

## Extended Channel Overview

Extended channel provides up to **24 months of support** (vs. 14 months standard) for versions 1.27+, but has key behavioral differences from Regular:

### Key Differences from Regular Channel

| Aspect | Regular Channel | Extended Channel |
|--------|----------------|------------------|
| **Minor version auto-upgrades** | Yes (automated) | **NO** - manual only (except at end of extended support) |
| **Patch auto-upgrades** | Yes, at Regular timing | Yes, at **same timing as Regular** (no delay) |
| **Cost** | Standard | **Extra cost during extended period only** (months 15-24) |
| **Support period** | 14 months | Up to 24 months |
| **Version availability** | Same as Regular | Same as Regular |
| **SLA** | Full | Full |

**Critical insight:** Extended channel does NOT auto-upgrade minor versions during the standard 14-month period. You'll need to manually trigger minor upgrades when you want them, giving you maximum control over timing.

## Migration Process

### Pre-Migration Checklist

- [ ] **Version compatibility check**: Verify 1.31 is available in Extended channel
- [ ] **Timeline planning**: Extended support for 1.31 will be available until ~mid-2026
- [ ] **Cost impact**: No extra charges during first 14 months, additional cost only during months 15-24
- [ ] **Operational model**: Plan for manual minor version upgrades going forward

### Migration Commands

```bash
# 1. Check current status
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="value(releaseChannel.channel,currentMasterVersion)"

# 2. Apply temporary "no upgrades" exclusion before channel change
# This prevents immediate auto-upgrades after switching
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-start "2024-01-15T00:00:00Z" \
  --add-maintenance-exclusion-end "2024-01-22T00:00:00Z" \
  --add-maintenance-exclusion-scope no_upgrades

# 3. Migrate to Extended channel
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel extended

# 4. Remove temporary exclusion after validating new channel behavior
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --remove-maintenance-exclusion "channel-migration"
```

### Post-Migration Verification

```bash
# Verify channel change
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="value(releaseChannel.channel)"

# Check auto-upgrade target (should show patch-only targets)
gcloud container clusters get-upgrade-info CLUSTER_NAME \
  --region REGION
```

## Recommended Extended Channel Configuration

For maximum production control with Extended channel:

```bash
# Configure persistent "no minor or node" exclusion for ultimate control
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --maintenance-window-start "2024-01-20T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

This gives you:
- **Security patches applied automatically** to control plane (within Saturday 2-6 AM window)
- **No automatic minor version upgrades** (you control timing)
- **No automatic node upgrades** (you control timing)
- **Exclusion tracks EoS** automatically (no need to renew)

## Operational Changes with Extended Channel

### What Changes
- **Minor upgrades become manual**: You'll trigger `gcloud container clusters upgrade --cluster-version` when ready
- **Node upgrades become manual**: You'll trigger `gcloud container node-pools upgrade` when ready  
- **Patches still automatic**: Control plane patches flow at Regular channel timing during maintenance windows

### What Stays the Same
- **Patch timing**: No delay vs. Regular channel
- **Version availability**: New versions arrive at same time as Regular
- **Support quality**: Full SLA throughout 24-month period

## Cost Implications

- **Months 1-14**: No additional cost (standard support period)
- **Months 15-24**: Additional cost applies only during extended period
- **Migration timing**: Since you're at 1.31, you'll hit extended period around mid-2025

## Migration Timing Considerations

**Option A - Immediate migration (recommended)**:
- Switch now while on 1.31
- Benefit from manual minor upgrade control immediately
- No cost impact until mid-2025

**Option B - Wait until needed**:
- Stay on Regular until closer to 1.31 EoS
- Risk: Less time to validate the new operational model

## Multi-Cluster Strategy

For production environments with dev/staging/prod:

**Recommended approach:**
```bash
# All environments on Extended channel
# Use maintenance exclusions + rollout sequencing for control
# Manually trigger upgrades: dev → staging → prod
```

**Alternative approach:**
```bash
# Dev: Regular channel (faster feedback)
# Prod: Extended channel (maximum control)
# Use "no minor" exclusions to keep versions aligned
```

## Rollback Plan

If Extended channel doesn't meet expectations:
- Can migrate back to Regular channel anytime
- Existing maintenance exclusions translate between channels
- No downgrade of cluster version required

Would you like me to create a detailed runbook for your specific cluster names and maintenance windows?