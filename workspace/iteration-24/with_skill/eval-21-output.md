# GKE Extended Channel Migration Plan

## Extended Channel Overview

Extended channel provides **up to 24 months of support** vs the standard 14 months, giving you maximum flexibility for upgrade timing. Here are the key characteristics:

| Aspect | Regular Channel | Extended Channel |
|--------|----------------|------------------|
| **Support period** | 14 months | Up to 24 months |
| **Minor version auto-upgrades** | Yes (automatic) | **No** (manual only, except at end of extended support) |
| **Patch auto-upgrades** | Yes | Yes |
| **Version availability** | Same timeline as Regular | Same as Regular during standard support period |
| **Additional cost** | None | **Yes, during extended period only** (months 15-24) |
| **EoS enforcement** | At 14 months | Delayed until end of extended support (24 months) |

## Key Tradeoffs

### ✅ **Advantages**
- **Maximum upgrade control**: Minor upgrades are manual-only, giving you complete control over when they happen
- **Extended compliance window**: 24-month support helps with slow enterprise change cycles
- **Delayed EoS enforcement**: No forced upgrades until month 24 (vs month 14)
- **Same patch cadence**: Security patches still auto-apply during maintenance windows

### ⚠️ **Considerations**
- **Manual minor upgrade responsibility**: You must plan and execute minor version upgrades yourself — they won't happen automatically
- **Additional cost during extended period**: Extra charges apply only during months 15-24 of a version's lifecycle
- **Operational overhead**: Requires internal processes to track when minor upgrades are needed
- **Security debt risk**: If you delay minor upgrades too long, you accumulate security patches and deprecated API changes

## Migration Steps

### 1. Pre-migration checks

```bash
# Check current version availability in Extended channel
gcloud container get-server-config --zone YOUR_ZONE \
  --format="yaml(channels.EXTENDED.validVersions)"

# Verify 1.31 is available in Extended
# If not, you may need to wait or upgrade first
```

### 2. Apply temporary maintenance exclusion (recommended)

```bash
# Prevent auto-upgrades immediately after channel switch
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-start-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-end-time "$(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-scope no_upgrades
```

### 3. Switch to Extended channel

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

### 4. Configure long-term maintenance strategy

Since minor upgrades won't be automatic, set up your preferred control pattern:

**Option A: Pure manual control**
```bash
# Remove the temporary exclusion, rely on manual upgrades only
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion "channel-migration"
```

**Option B: Patch-only auto-upgrades (recommended)**
```bash
# Replace temporary exclusion with persistent "no minor or node" exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion "channel-migration" \
  --add-maintenance-exclusion-name "minor-version-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

### 5. Set up maintenance windows for patches

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-12-01T02:00:00Z" \
  --maintenance-window-end "2024-12-01T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```

## Operational Process with Extended Channel

### For patch upgrades (automatic)
- Patches auto-apply during your maintenance windows
- Monitor via Cloud Logging and scheduled upgrade notifications (72h advance notice)

### For minor upgrades (manual process required)
1. **Monitor GKE release schedule** for new minor versions
2. **Test in dev/staging** clusters first
3. **Plan upgrade window** considering your workload patterns
4. **Execute manually** when ready:

```bash
# Control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.xxx

# Then node pools (Standard clusters only)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxx
```

## Cost Implications

- **Months 1-14**: No additional cost (same as Regular channel)
- **Months 15-24**: Additional cost during extended support period
- **Cost only applies** to versions using extended support — if you upgrade before month 15, no extra charge

## Migration Checklist

```markdown
Extended Channel Migration Checklist

Pre-migration
- [ ] Current version (1.31) available in Extended channel verified
- [ ] Team understands manual minor upgrade responsibility
- [ ] Internal process defined for tracking minor upgrade needs
- [ ] Budget approved for extended support costs (months 15-24)

Migration
- [ ] Temporary maintenance exclusion applied
- [ ] Channel switched to Extended
- [ ] Post-switch behavior verified (patches only, no minor auto-upgrades)
- [ ] Long-term maintenance exclusion configured
- [ ] Maintenance windows configured for patch timing

Post-migration
- [ ] Monitoring set up for GKE release schedule
- [ ] Manual minor upgrade process documented
- [ ] Team trained on Extended channel operational model
```

## Recommended Configuration for Production

For maximum control with security patch currency:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --maintenance-window-start "2024-12-01T02:00:00Z" \
  --maintenance-window-end "2024-12-01T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SUN"
```

This gives you:
- Extended 24-month support
- Automatic security patches (Sunday 2-6 AM)
- Complete manual control over minor and node upgrades
- Protection from forced EoS upgrades until month 24

**Warning**: Extended channel is ideal for teams that want maximum control but requires operational discipline around minor upgrade planning. If you prefer a "set and forget" approach, Regular channel with maintenance windows may be better suited for your needs.