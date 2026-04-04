# Extended Release Channel Migration Plan

## Extended Channel Overview

Extended channel provides up to **24 months of support** for versions 1.27+ with these key characteristics:

**Benefits:**
- Extended support period (24 months vs standard 14 months)
- **Manual control over minor version upgrades** — control plane minor upgrades are NOT automated (except at end of extended support)
- **Patches still auto-apply at Regular channel timing** — no delay on security patches
- Additional cost only during the extended support period (months 15-24)
- Full SLA coverage throughout entire support period

**Tradeoffs:**
- **You must manually initiate control plane minor upgrades** (except final EoS enforcement)
- Node auto-upgrades still follow the control plane minor version unless blocked by exclusions
- Additional cost during extended support period (months 15-24 of version lifecycle)
- Same version availability timing as Regular channel — no faster access to new features

## Migration Strategy from Regular → Extended

### Current State Assessment
- **Current:** Regular channel at 1.31
- **Extended support:** Available for 1.31 (all versions 1.27+ get extended support)
- **Cost impact:** No additional cost until 1.31 reaches end of standard support (~month 15)

### Step-by-Step Migration

**1. Pre-migration checks:**
```bash
# Verify current channel and version
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="table(name, currentMasterVersion, releaseChannel.channel)"

# Check if 1.31 is available in Extended channel
gcloud container get-server-config --region REGION \
  --format="yaml(channels.EXTENDED.validVersions)"
```

**2. Apply temporary maintenance exclusion (recommended):**
```bash
# Prevent unexpected auto-upgrades immediately after channel switch
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-start $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end $(date -u -d "+7 days" +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_upgrades
```

**3. Switch to Extended channel:**
```bash
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel extended
```

**4. Verify migration:**
```bash
# Confirm channel change
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="value(releaseChannel.channel)"

# Check auto-upgrade target
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

**5. Remove temporary exclusion:**
```bash
# After verifying stable state
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --remove-maintenance-exclusion "channel-migration"
```

## Operational Changes with Extended Channel

### Upgrade Control Strategy

**Recommended configuration for maximum control:**
```bash
# Add persistent "no minor or node" exclusion for full control
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --maintenance-window-start "2024-12-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SUN"
```

This gives you:
- Control plane patches auto-applied (security updates continue)
- Manual control over when minor upgrades happen
- Manual control over when node pool upgrades happen
- Patches limited to Sunday 2-6 AM window

### Minor Version Upgrade Workflow

When you decide to upgrade to a new minor version:

**1. Check available versions:**
```bash
gcloud container get-server-config --region REGION \
  --format="yaml(channels.EXTENDED.validVersions)"
```

**2. Upgrade control plane (manual initiation required):**
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version TARGET_VERSION
```

**3. Upgrade node pools (also manual unless exclusion is removed):**
```bash
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version TARGET_VERSION
```

## Cost Implications

- **Months 1-14:** Same cost as Regular channel (no additional charge)
- **Months 15-24:** Additional extended support fee applies
- **Current impact:** Since you're on 1.31, you won't see additional costs until 1.31 reaches month 15 of its lifecycle

## Best Practices for Extended Channel

**1. Establish upgrade cadence:**
- Plan minor upgrades every 6-12 months during extended support
- Don't wait until final EoS enforcement — maintain reasonable currency

**2. Multi-cluster strategy:**
```bash
# Dev cluster on Regular for early testing
gcloud container clusters update dev-cluster \
  --region REGION \
  --release-channel regular

# Prod cluster on Extended for stability
gcloud container clusters update prod-cluster \
  --region REGION \
  --release-channel extended
```

**3. Monitor EoS dates:**
```bash
# Check end of support timeline
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION \
  --format="table(endOfStandardSupportTimestamp, endOfExtendedSupportTimestamp)"
```

## Migration Checklist

```
Extended Channel Migration Checklist
- [ ] Verify 1.31 available in Extended channel
- [ ] Apply temporary "no upgrades" exclusion before migration
- [ ] Switch cluster to Extended channel
- [ ] Verify channel change completed
- [ ] Configure persistent maintenance exclusions for control
- [ ] Set up maintenance windows for patch timing
- [ ] Remove temporary migration exclusion
- [ ] Document new minor upgrade workflow for team
- [ ] Set calendar reminders for periodic minor version evaluation
- [ ] Update monitoring/alerting for manual upgrade requirements
```

## Key Operational Changes

**Before (Regular channel):**
- Minor versions auto-upgraded based on channel progression
- Node pools auto-upgraded to match control plane

**After (Extended channel):**
- **You initiate control plane minor upgrades** when ready
- **You initiate node pool upgrades** (unless exclusions removed)
- Patches continue auto-applying for security
- 24-month support runway for each version

This gives you maximum control over disruptive upgrades while maintaining security patch currency.