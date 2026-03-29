# GKE Release Channel Migration Plan

## Executive Summary
Your "No channel" clusters are missing critical upgrade control features that would actually give you MORE control, not less. The legacy "No channel" configuration lacks the most powerful maintenance exclusion types and modern upgrade controls. **Release channels + maintenance exclusions provide superior control compared to "No channel".**

## What You're Missing on "No Channel"

| Feature | Release channels | No channel |
|---------|-----------------|------------|
| **"No minor or node upgrades" exclusion** | ✅ Yes (cluster-level + per-nodepool) | ❌ **No** — only the 30-day "no upgrades" type is available |
| **"No minor upgrades" exclusion** | ✅ Yes | ❌ **No** |
| **Persistent exclusions (tracks EoS)** | ✅ Yes (`--until-end-of-support`) | ❌ **No** — must chain 30-day exclusions |
| **Extended support (24 months)** | ✅ Yes | ❌ **No** |
| **Granular auto-upgrade control** | ✅ Full (windows + exclusions + intervals) | ⚠️ Limited |
| **Rollout sequencing** | ✅ Yes (advanced) | ❌ **No** |

**Key insight:** The most powerful upgrade control tools (channel-specific maintenance exclusions like "no minor or node upgrades") are **only available on release channels**. Customers who want maximum control should use release channels WITH exclusions, not avoid channels entirely.

## Your Current EoS Risk

**Legacy "No channel" EoS behavior:** When a version reaches End of Support:
- Control plane EoS minor versions are auto-upgraded to the next supported minor version
- EoS node pools are auto-upgraded **EVEN when "no auto-upgrade" is configured**
- This enforcement is systematic — there is no way to avoid it except the 30-day "no upgrades" exclusion
- You can only defer with chained 30-day exclusions (max 3 per cluster), accumulating security debt

At GKE 1.31, you're approaching the EoS enforcement window. This creates forced upgrade pressure with limited deferral options.

## Recommended Migration Path

### Option 1: Regular Channel (Recommended for Most)
**Best for:** Production workloads wanting predictable upgrade cadence with full control

```bash
# Step 1: Apply temporary "no upgrades" exclusion before channel change
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-start-time "2024-12-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-08T00:00:00Z" \
  --add-maintenance-exclusion-scope no_upgrades

# Step 2: Migrate to Regular channel
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular

# Step 3: Configure powerful "no minor or node upgrades" exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "production-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Step 4: Remove temporary exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "channel-migration"
```

**Result:** You get security patches automatically on the control plane, but complete control over when minor and node upgrades happen. No 30-day limits, no chained exclusions.

### Option 2: Extended Channel (Maximum Control)
**Best for:** Compliance environments, customers wanting manual minor upgrades only

```bash
# Same migration steps, but use --release-channel extended
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Extended channel benefits:**
- Up to 24 months of support (cost only during extended period)
- Minor version upgrades are NOT automated (except at end of extended support)
- Only patches are auto-applied
- Maximum flexibility around EoS enforcement

## Migration Warnings & Considerations

**Version availability check:** Before migrating, verify 1.31 is available in your target channel:
```bash
gcloud container get-server-config --zone ZONE --format="yaml(channels)"
```

If 1.31 isn't available in Regular/Extended yet, your cluster will be "ahead of channel" and won't receive auto-upgrades until the channel catches up. You'll still get patches, but not minor upgrades.

**Coordinate timing:** Apply the temporary "no upgrades" exclusion BEFORE changing channels to avoid unexpected auto-upgrades immediately after the switch.

**Exclusion translation:** When moving from "No channel" with per-nodepool "disable auto-upgrade" settings, only exclusions of type "no_upgrades" translate between configurations. The powerful "no minor or node" exclusions are release-channel-only.

## Recommended Configuration Post-Migration

For maximum control while maintaining security posture:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --maintenance-window-start "2024-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

This gives you:
- **Automatic security patches** on control plane (within Saturday 2-6 AM window)
- **No automatic minor or node upgrades** — you control timing via manual triggers
- **No time limits** on the exclusion — it tracks EoS automatically
- **Superior control** compared to "No channel" limitations

## Migration Sequence for 8 Clusters

**Recommended approach:**
1. **Start with dev/staging clusters** to validate the new configuration
2. **Soak for 1-2 weeks** to ensure patch behavior meets expectations
3. **Production clusters in batches** — 2-3 at a time, not all simultaneously
4. **Keep clusters on the same channel** to avoid version drift

**Multi-environment channel strategy:**
- **All environments on Regular:** Ensures version consistency, use exclusions for timing control
- **Alternative:** Dev=Regular, Prod=Extended — channel progression is deterministic, gives natural dev→prod sequencing

## Expected Behavior Changes

**On "No channel" today:**
- Upgraded at Stable pace for minor, Regular pace for patches
- Only 30-day "no upgrades" exclusion available
- Per-nodepool auto-upgrade disable (limited)

**On Regular channel with "no minor or node" exclusion:**
- **Control plane:** Gets security patches automatically (respects maintenance windows)
- **Node pools:** No automatic upgrades — you trigger manually when ready
- **Exclusion:** Permanent until you trigger an upgrade, then auto-renews for new version
- **EoS handling:** Delayed until end of extended support if using Extended channel

## Commands for All 8 Clusters

Create a migration script:

```bash
#!/bin/bash
CLUSTERS=("cluster-1" "cluster-2" "cluster-3" "cluster-4" "cluster-5" "cluster-6" "cluster-7" "cluster-8")
ZONES=("us-central1-a" "us-central1-b" "us-east1-a" "us-east1-b" "us-west1-a" "us-west1-b" "europe-west1-a" "europe-west1-b")

for i in "${!CLUSTERS[@]}"; do
  CLUSTER=${CLUSTERS[$i]}
  ZONE=${ZONES[$i]}
  
  echo "Migrating $CLUSTER in $ZONE..."
  
  # Apply temporary exclusion
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --add-maintenance-exclusion-name "channel-migration" \
    --add-maintenance-exclusion-start-time "2024-12-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-12-08T00:00:00Z" \
    --add-maintenance-exclusion-scope no_upgrades
  
  # Migrate to Regular channel
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --release-channel regular
  
  # Configure permanent control exclusion
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support \
    --maintenance-window-start "2024-01-01T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
  
  # Remove temporary exclusion
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --remove-maintenance-exclusion-name "channel-migration"
  
  echo "Migration complete for $CLUSTER"
  sleep 30  # Brief pause between clusters
done
```

## Next Steps

1. **Validate channel availability** for version 1.31 in your target regions
2. **Start with 1-2 dev clusters** using the migration commands above
3. **Monitor for 1 week** — verify patch behavior and no unexpected upgrades
4. **Roll out to remaining clusters** in batches
5. **Document your new upgrade workflow** — when you want minor upgrades, remove the exclusion, trigger manually, then re-apply

**Key message:** Release channels give you MORE control, not less. The "No channel" configuration is the legacy path with limited options. Modern GKE upgrade control is channels + exclusions + windows.