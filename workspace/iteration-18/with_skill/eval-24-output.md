# GKE Legacy "No Channel" Migration Analysis & Plan

## What You're Missing on "No Channel"

The legacy "No channel" configuration lacks critical upgrade control features that are **only available on release channels**:

| Feature | Release channels | No channel |
|---------|-----------------|------------|
| **"No minor or node upgrades" exclusion** | ✅ Yes (cluster-level + per-nodepool) | ❌ **No** — only the 30-day "no upgrades" type is available |
| **"No minor upgrades" exclusion** | ✅ Yes | ❌ **No** |
| **Per-nodepool maintenance exclusion** | ✅ Yes | ⚠️ Yes (but limited to "no upgrades" 30 days) |
| **Extended support (24 months)** | ✅ Yes | ❌ **No** |
| **Rollout sequencing** | ✅ Yes (advanced) | ❌ **No** |
| **Persistent exclusions (tracks EoS)** | ✅ Yes | ❌ **No** |
| **Granular auto-upgrade control** | ✅ Full (windows + exclusions + intervals) | ⚠️ Limited |

**Key insight:** The most powerful upgrade control tools (channel-specific maintenance exclusion scopes) are **only available on release channels**. This is the opposite of what many users assume — channels provide MORE control, not less.

## Why Your EoS Issues Will Get Worse

**Current EoS behavior on "No channel":**
- Control plane EoS minor versions are auto-upgraded to the next supported minor version
- EoS node pools are auto-upgraded EVEN when "no auto-upgrade" is configured
- This enforcement is systematic — there is **no way to avoid it** except the 30-day "no upgrades" exclusion
- You can only defer EoS upgrades by 30 days maximum (one exclusion at a time)

**Legacy channel EoS enforcement timeline:**
- Enforcement for ≤1.29 was completed in 2025
- **Systematic enforcement for every EoS version applies from 1.32 onward**
- At 1.31, you're approaching this stricter enforcement regime

## Migration Recommendation: Extended Channel

For maximum control while solving your EoS issues, migrate to **Extended channel**:

```bash
# Migrate all 8 clusters to Extended channel
for cluster in cluster1 cluster2 cluster3 cluster4 cluster5 cluster6 cluster7 cluster8; do
  gcloud container clusters update $cluster \
    --zone ZONE \
    --release-channel extended
done
```

**Why Extended channel is perfect for your use case:**
- **Up to 24 months of support** (vs 14 months on other channels)
- **Minor version upgrades are NOT automated** (except at end of extended support)
- Only patches are auto-applied — you control when minor upgrades happen
- Delays EoS enforcement until end of extended support
- Additional cost applies ONLY during the extended support period (months 15-24)

## Migration Path & Exclusion Strategy

### Step 1: Pre-migration exclusion setup
Apply temporary "no upgrades" exclusion before channel change to prevent immediate auto-upgrades:

```bash
# Add 30-day exclusion before migration
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "migration-freeze" \
  --add-maintenance-exclusion-start "2024-01-15T00:00:00Z" \
  --add-maintenance-exclusion-end "2024-02-14T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

### Step 2: Channel migration
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

### Step 3: Set up persistent control (the key advantage)
```bash
# Add persistent "no minor or node upgrades" exclusion
# This automatically tracks EoS and gives maximum control
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "platform-team-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

### Step 4: Configure maintenance windows
```bash
# Set predictable maintenance windows for the patches that will auto-apply
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-20T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Your New Upgrade Control Model

**What happens automatically:**
- ✅ Control plane security patches (within your maintenance window)
- ❌ Minor version upgrades (blocked by exclusion)
- ❌ Node pool upgrades (blocked by exclusion)

**What you control manually:**
- When minor version upgrades happen (you initiate with `gcloud container clusters upgrade`)
- When node pool upgrades happen (you initiate per pool)
- Rollback timing during two-step upgrades (1.33+ feature)

## Migration Warnings & Validation

**Version availability check before migrating:**
```bash
# Verify 1.31 is available in Extended channel
gcloud container get-server-config --zone ZONE --format="yaml(channels.EXTENDED)"
```

If 1.31 is not yet available in Extended, your clusters will be "ahead of channel" and won't receive auto-upgrades until Extended reaches 1.31. You'll still get patches, but not minor upgrades.

**Post-migration validation:**
```bash
# Confirm channel migration
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel)"

# Check exclusion is active
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy)"

# Verify auto-upgrade target (should be patch-only within 1.31)
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

## Alternative: Regular Channel (if cost is a concern)

If Extended channel's additional cost during months 15-24 is problematic:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

This gives you the same control mechanisms but with standard 14-month support. You'll need to plan minor upgrades more frequently to avoid EoS.

## Implementation Timeline for 8 Clusters

**Week 1-2: Migration preparation**
- [ ] Validate 1.31 availability in Extended channel across all regions
- [ ] Document current cluster configurations and workloads
- [ ] Plan maintenance windows (stagger across clusters to avoid simultaneous issues)

**Week 3-4: Staged migration**
- [ ] Migrate 2 non-production clusters first
- [ ] Apply exclusions and validate behavior
- [ ] Monitor for 1 week

**Week 5-6: Production migration**
- [ ] Migrate remaining 6 clusters
- [ ] Implement monitoring for exclusion status and EoS dates
- [ ] Update runbooks and operational procedures

## Monitoring Your New Control Model

**Set up alerting for EoS approaching:**
```bash
# Check EoS status across your fleet
for cluster in cluster1 cluster2 cluster3 cluster4 cluster5 cluster6 cluster7 cluster8; do
  echo "=== $cluster ==="
  gcloud container clusters get-upgrade-info $cluster --region REGION \
    --format="table(name,endOfStandardSupportTimestamp,endOfExtendedSupportTimestamp)"
done
```

**Cloud Logging query for upgrade events:**
```
resource.type="gke_cluster"
protoPayload.metadata.operationType=~"(UPDATE_CLUSTER|UPGRADE_MASTER)"
```

## Key Benefits After Migration

1. **Predictable EoS handling:** 24-month support with advance warning
2. **Patch-only auto-upgrades:** Security updates without disruption
3. **Manual minor upgrade control:** You decide when to take breaking changes
4. **Persistent exclusions:** No more 30-day renewal cycles
5. **Better tooling:** Rollout sequencing, disruption intervals, rollback-safe upgrades

The migration solves your core pain points while giving you enterprise-grade upgrade lifecycle management that scales across your 8-cluster fleet.