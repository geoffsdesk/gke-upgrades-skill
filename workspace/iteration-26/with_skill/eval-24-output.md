# GKE Channel Migration Analysis & Plan

## What You're Missing on "No Channel"

Your legacy "No channel" configuration is missing critical upgrade control features that are **only available on release channels**:

| Feature | Release Channels | No Channel |
|---------|-----------------|------------|
| **"No minor or node upgrades" exclusion** | ✅ Yes (cluster-level + per-nodepool) | ❌ **No** — only the 30-day "no upgrades" type is available |
| **"No minor upgrades" exclusion** | ✅ Yes | ❌ **No** |
| **Extended support (24 months)** | ✅ Yes | ❌ **No** |
| **Rollout sequencing** | ✅ Yes (advanced) | ❌ **No** |
| **Persistent exclusions (tracks EoS)** | ✅ Yes | ❌ **No** |
| **Granular auto-upgrade control** | ✅ Full (windows + exclusions + intervals) | ⚠️ Limited |
| **Per-nodepool maintenance exclusion** | ❌ No — use cluster-level exclusion scopes | ✅ Yes (persistent until EoS) |

**Key insight:** The most powerful upgrade control tools are **only available on release channels**. Customers who want maximum control should use release channels WITH exclusions, not avoid channels entirely.

## Your Current Pain Points Explained

**Forced upgrades at EoS:** When versions reach End of Support on "No channel," GKE force-upgrades both control plane AND node pools to the next supported minor version. This is systematic and unavoidable except for the 30-day "no upgrades" exclusion.

**Limited exclusion types:** Your only option is the broad "no upgrades" exclusion (30-day max). You can't selectively block minor versions while allowing patches — this granular control only exists on release channels.

**No long-term version control:** Without persistent exclusions, you must manually chain 30-day exclusions or accept forced upgrades. Release channels offer exclusions that automatically track EoS dates.

## Recommended Migration Strategy

### Target Configuration: Extended Channel + Persistent Exclusions

For maximum control while maintaining security posture:

```bash
# Migrate each cluster to Extended channel with persistent "no minor or node" exclusion
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --release-channel extended \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support \
    --maintenance-window-start "2024-12-07T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**What this gives you:**
- **Extended support:** Up to 24 months (cost only during extended period, no extra cost during standard 14-month period)
- **Auto-applied CP security patches only** — no minor or node auto-upgrades
- **Manual control** over when minor upgrades happen
- **Persistent exclusion** — automatically renews when you manually upgrade to new minor versions
- **Predictable timing** — patches limited to Saturday 2-6 AM window

### Migration Order & Timeline

**Phase 1: Dev/Test Clusters First (Week 1)**
```bash
# Migrate 2 non-production clusters first
gcloud container clusters update dev-cluster-1 \
    --zone us-central1-a \
    --release-channel extended \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

**Phase 2: Production Clusters (Week 2-3)**
- Migrate remaining 6 clusters using the same configuration
- Stagger by 2-3 days to observe behavior

**Phase 3: Validation & Optimization (Week 4)**
- Confirm patch-only auto-upgrades work as expected
- Test manual minor upgrade process on dev clusters

### Critical Migration Warnings

⚠️ **Version availability check:** Your current 1.31 version may not be immediately available in Extended channel. Check first:

```bash
gcloud container get-server-config --zone ZONE \
    --format="yaml(channels.EXTENDED.validVersions)"
```

If 1.31 isn't available in Extended yet, you'll be "ahead of channel" and won't receive auto-upgrades until Extended catches up. You'll still get patches, but not minor version progression.

⚠️ **Coordinate during maintenance window:** Apply a temporary "no upgrades" exclusion before changing channels to avoid unexpected auto-upgrades immediately after the switch:

```bash
# Before migration
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "pre-migration-freeze" \
    --add-maintenance-exclusion-start-time "2024-12-07T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-12-14T00:00:00Z" \
    --add-maintenance-exclusion-scope no_upgrades

# Migrate channel
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --release-channel extended

# Remove temporary exclusion after verifying behavior
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --remove-maintenance-exclusion-name "pre-migration-freeze"
```

## Alternative: Regular Channel with Minor Control

If Extended channel's cost model doesn't fit, use Regular channel (closest to your current "No channel" behavior):

```bash
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --release-channel regular \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

**Trade-offs:**
- ✅ Standard 14-month support (no extended cost)
- ✅ Same persistent exclusion benefits
- ❌ Faster patch cadence than Extended
- ❌ Minor version EoS enforcement at 14 months (vs 24 months on Extended)

## Post-Migration Workflow

### Controlled Minor Upgrades

With persistent "no minor or node" exclusions, you control when minor upgrades happen:

1. **Monitor for new minor versions:**
   ```bash
   gcloud container get-server-config --zone ZONE \
       --format="yaml(channels.EXTENDED.validVersions)"
   ```

2. **Test in dev first:**
   ```bash
   gcloud container clusters upgrade dev-cluster-1 \
       --zone ZONE \
       --cluster-version 1.32.X-gke.Y
   ```

3. **Validate, then roll to production:**
   ```bash
   # Production clusters
   gcloud container clusters upgrade prod-cluster-1 \
       --zone ZONE \
       --cluster-version 1.32.X-gke.Y
   ```

4. **Exclusion automatically renews** for the new version — no manual re-application needed.

### Patch Management

Control plane patches auto-apply within your maintenance window. To control patch frequency:

```bash
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --maintenance-patch-version-disruption-interval=7776000s  # 90 days max
```

## Expected Benefits Post-Migration

**Immediate:**
- No more surprise forced upgrades at EoS
- Granular exclusion control (patches vs minor versions)
- Persistent exclusions that auto-renew
- Maintenance windows for predictable timing

**Medium-term:**
- Extended support option (24 months on versions 1.27+)
- Rollout sequencing capability across your 8-cluster fleet
- Better integration with GKE's upgrade ecosystem

**Long-term:**
- Future-proofed against "No channel" deprecation
- Access to new release channel features as they're added
- Simplified ops — fewer manual exclusion renewals

## Migration Checklist

```
Pre-Migration Checklist
- [ ] Version 1.31 availability confirmed in Extended channel
- [ ] 8 clusters inventoried with current versions and workload types
- [ ] Migration order planned (dev → prod, staggered)
- [ ] Maintenance windows defined for each cluster
- [ ] Temporary "no upgrades" exclusions ready for migration window
- [ ] Platform team trained on new exclusion types and persistent behavior
- [ ] Monitoring configured for auto-upgrade events via Cloud Logging

Migration Execution (per cluster)
- [ ] Apply temporary "no upgrades" exclusion
- [ ] Migrate to Extended channel
- [ ] Add persistent "no minor or node" exclusion
- [ ] Configure maintenance window
- [ ] Remove temporary exclusion
- [ ] Validate auto-upgrade target: `gcloud container clusters get-upgrade-info`
- [ ] Document new configuration in runbooks

Post-Migration Validation
- [ ] No unexpected auto-upgrades for 2 weeks
- [ ] Patch auto-upgrades working within maintenance windows
- [ ] Manual minor upgrade tested on dev cluster
- [ ] Platform team comfortable with new workflow
```

This migration eliminates your forced upgrade pain while giving you **more** control than "No channel" ever provided. The Extended channel + persistent exclusions combination is the recommended path for platform teams requiring maximum upgrade control.