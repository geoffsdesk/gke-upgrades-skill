# Extended Release Channel Migration Plan

## Key Tradeoffs of Extended Channel

### Benefits
- **24-month support** instead of 14 months (versions 1.27+)
- **Maximum flexibility around EoS enforcement** - minor upgrades are NOT automated during extended support period
- **Same SLA as Regular/Stable** during standard support (first 14 months)
- **Control over minor upgrade timing** - you initiate minor upgrades manually during extended support

### Tradeoffs & Costs
- **Additional cost during extended support period** (months 15-24) - no extra charge during standard support
- **Manual minor upgrade responsibility** - during extended support, YOU must plan and execute minor upgrades (patches are still auto-applied)
- **No automated minor upgrades** during extended support - requires internal processes and planning
- **Same cadence as Regular** during standard support - no change in upgrade timing for first 14 months

## Migration Process

### Current State Assessment
```bash
# Check your current version and channel
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, releaseChannel.channel)"
```

### Migration Steps

**1. Migrate to Extended channel:**
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

**2. Verify migration:**
```bash
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel)"
```

### Version Compatibility Warning

Since you're currently on 1.31, you need to verify if 1.31 is available in Extended channel:

```bash
# Check available versions in Extended channel
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels.EXTENDED)"
```

**Critical consideration:** If 1.31 is not yet available in Extended channel, your cluster will be "ahead of channel" after migration and will NOT receive auto-upgrades until Extended channel catches up to 1.31. You'll still receive patches, but no minor version upgrades until the channel reaches your current version.

## Operational Changes for Extended Channel

### During Standard Support Period (months 1-14)
- **No change in behavior** - same auto-upgrade cadence as Regular channel
- **Same maintenance windows and exclusions** work as before
- **No additional cost**

### During Extended Support Period (months 15-24)
- **Minor upgrades become manual** - you must plan and initiate them
- **Patches remain automatic** - security updates still auto-apply
- **Additional cost applies** - contact Google Cloud billing for current rates
- **EoS enforcement delayed** - happens at 24 months instead of 14 months

### Required Process Changes

**1. Internal minor upgrade planning:**
```bash
# You'll need to manually trigger minor upgrades during extended support
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

**2. Version tracking and planning:**
- Monitor when versions enter extended support period
- Plan minor upgrades proactively before 24-month EoS
- Maintain upgrade testing processes for manual upgrades

## Recommended Approach

### Multi-Environment Strategy
```
Dev → Regular channel (faster feedback)
Staging → Regular channel  
Production → Extended channel (maximum control)
```

### Alternative: Regular + Maintenance Exclusions
If the primary goal is upgrade control rather than 24-month support, consider staying on Regular channel with maintenance exclusions:

```bash
# "No minor or node upgrades" exclusion (tracks EoS automatically)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "prod-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

This gives you:
- Manual control over minor upgrades
- Automatic security patches on control plane
- No additional cost
- Standard 14-month support

## Migration Checklist

```markdown
Extended Channel Migration Checklist
- [ ] Verify 1.31 availability in Extended channel
- [ ] Understand cost implications for extended support period (months 15-24)
- [ ] Plan internal processes for manual minor upgrades
- [ ] Migrate cluster to Extended channel
- [ ] Update monitoring/alerting for manual upgrade requirements
- [ ] Document new operational procedures
- [ ] Test manual upgrade process in dev/staging first
```

## When Extended Channel Makes Sense

✅ **Good fit if you:**
- Need true 24-month support for compliance/stability
- Have dedicated platform teams to manage manual upgrades
- Want maximum flexibility around EoS enforcement
- Can absorb additional costs during extended support

❌ **Consider alternatives if you:**
- Primarily want upgrade control (use Regular + exclusions)
- Don't have processes for manual minor upgrade planning
- Cost-sensitive during extended support period
- Prefer automated lifecycle management

The Extended channel is designed for customers who need maximum control and extended support, but it shifts responsibility for minor upgrade planning to your team during the extended support period.