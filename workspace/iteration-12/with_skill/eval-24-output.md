# GKE "No Channel" Migration Plan

## Executive Summary

Your team is operating on a legacy configuration that significantly limits upgrade control capabilities. Moving to release channels will actually **give you MORE control**, not less — the opposite of what many teams assume.

## What You're Missing on "No Channel"

The "No channel" configuration lacks critical upgrade control features that are only available on release channels:

| Upgrade Control Feature | Release Channels | No Channel |
|------------------------|------------------|------------|
| **"No minor or node upgrades" exclusion** | ✅ Yes (cluster-level + per-nodepool) | ❌ **No** — most powerful control unavailable |
| **"No minor upgrades" exclusion** | ✅ Yes | ❌ **No** |
| **Persistent exclusions** (tracks EoS automatically) | ✅ Yes | ❌ **No** |
| **Per-nodepool maintenance exclusion** | ✅ Yes (all scopes) | ⚠️ Limited ("no upgrades" 30 days only) |
| **Extended support** (24 months) | ✅ Yes | ❌ **No** |
| **Rollout sequencing** (multi-cluster) | ✅ Yes | ❌ **No** |
| **Granular auto-upgrade control** | ✅ Full (windows + exclusions + intervals) | ⚠️ Limited |

### Key Problems You're Experiencing

1. **Forced upgrades at EoS**: When versions reach End of Support, "No channel" clusters are systematically force-upgraded. The only escape is a 30-day "no upgrades" exclusion.

2. **Limited exclusion types**: You can only use "no upgrades" exclusions (30-day max, blocks everything including security patches). The more sophisticated exclusion types that allow patches while blocking disruptive changes don't exist on "No channel".

3. **No Extended support option**: Versions 1.27+ can get up to 24 months of support on Extended channel — unavailable to "No channel" clusters.

4. **Manual EoS tracking**: You must manually track End of Support dates and apply exclusions. Release channels offer persistent exclusions that automatically renew.

## Recommended Migration Strategy

### Target Configuration: Regular Channel + Maintenance Exclusions

**Regular channel** provides the closest behavior to your current setup while unlocking advanced controls:
- Upgrade timing similar to your current Stable-paced minor releases
- All advanced exclusion types available
- Full SLA coverage
- Extended support option for future versions

### Migration Path for Your 8 Clusters

#### Phase 1: Staging Environment (1-2 clusters)
```bash
# Choose your least critical cluster first
# Add temporary "no upgrades" exclusion before channel migration
gcloud container clusters update STAGING_CLUSTER \
  --zone ZONE \
  --add-maintenance-exclusion-name "channel-migration-freeze" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades

# Migrate to Regular channel
gcloud container clusters update STAGING_CLUSTER \
  --zone ZONE \
  --release-channel regular

# Replace with persistent "no minor or node upgrades" exclusion
gcloud container clusters update STAGING_CLUSTER \
  --zone ZONE \
  --remove-maintenance-exclusion-name "channel-migration-freeze" \
  --add-maintenance-exclusion-name "platform-team-control" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-until-end-of-support \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

#### Phase 2: Production Rollout (remaining 6 clusters)
Stagger migrations over 2-3 weeks, using the same pattern. Monitor staging cluster behavior for confidence.

### Post-Migration: Enhanced Control Configuration

Once on Regular channel, configure the upgrade controls you never had:

```bash
# Set maintenance windows (off-peak hours)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start 2024-12-15T02:00:00Z \
  --maintenance-window-end 2024-12-15T06:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Configure disruption intervals (prevent back-to-back upgrades)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-patch-version-disruption-interval 14 \
  --maintenance-minor-version-disruption-interval 60

# For maximum control: "no minor or node upgrades" exclusion
# Allows control plane security patches, blocks all disruptive changes
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "platform-team-control" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-until-end-of-support \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

## Enhanced Upgrade Control Options

### Three Exclusion Types (Only Available on Release Channels)

1. **"No upgrades"** — Blocks everything including patches (30-day max)
   - Use for: Code freezes, BFCM, critical periods
   
2. **"No minor or node upgrades"** — Allows CP patches, blocks disruptive changes (up to EoS)
   - **Recommended for your team**: Gets security patches while maintaining control
   
3. **"No minor upgrades"** — Allows patches + node upgrades, blocks minor versions (up to EoS)
   - Use if comfortable with node churn but not K8s API changes

### Persistent Exclusions
```bash
# This exclusion automatically renews when a new minor version is adopted
# No more manual tracking of EoS dates
--add-maintenance-exclusion-until-end-of-support
```

### Future: Extended Channel Option
For versions 1.27+, you can migrate to Extended channel for up to 24 months of support:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```
**Note**: Minor upgrades are NOT automated on Extended channel — you control the timing completely.

## Migration Checklist

```
Pre-Migration Checklist
- [ ] Inventory all 8 clusters: names, zones, current versions
- [ ] Verify all clusters are at supported versions (1.31 is fine)
- [ ] Choose staging cluster for Phase 1 testing
- [ ] Document current maintenance practices
- [ ] Plan rollout sequence for remaining 7 clusters
- [ ] Communicate migration timeline to stakeholders

Migration Steps (per cluster)
- [ ] Apply temporary "no upgrades" exclusion
- [ ] Migrate to Regular channel: `--release-channel regular`
- [ ] Remove temporary exclusion
- [ ] Add persistent "no minor or node upgrades" exclusion
- [ ] Configure maintenance window for predictable timing
- [ ] Set disruption intervals to prevent rapid-fire upgrades
- [ ] Verify cluster auto-upgrade status: `gcloud container clusters get-upgrade-info`
- [ ] Update monitoring/alerting for new configuration

Post-Migration Validation
- [ ] Confirm exclusions are active and properly scoped
- [ ] Verify maintenance windows are configured
- [ ] Test that patches still flow to control plane
- [ ] Validate that minor/node upgrades are blocked as expected
- [ ] Document new operational procedures for team
```

## Expected Benefits

1. **Better control**: "No minor or node upgrades" exclusion gives you security patches while blocking disruptive changes — impossible on "No channel"

2. **Less manual work**: Persistent exclusions automatically renew, eliminating EoS date tracking

3. **Predictable timing**: Maintenance windows + disruption intervals give you deterministic upgrade behavior

4. **Future flexibility**: Extended support, rollout sequencing, and enhanced features become available

5. **Reduced forced upgrades**: More sophisticated exclusion options reduce emergency upgrade scenarios

## Timeline Recommendation

- **Week 1**: Migrate staging cluster, validate behavior
- **Week 2-3**: Migrate production clusters in batches of 2-3
- **Week 4**: Configure enhanced controls across all clusters

The migration itself is non-disruptive — it only changes the upgrade policy, not the cluster version. Your workloads continue running normally.

**Key insight**: Release channels + exclusions give you MORE control than "No channel", not less. This migration will solve your forced upgrade issues while providing upgrade control capabilities you never had before.