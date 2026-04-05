# Extended Release Channel Migration Plan

## Extended Channel Overview

Extended channel provides **up to 24 months** of support for versions 1.27+ (vs. 14 months standard). Key characteristics:

| Aspect | Extended Channel | Regular Channel |
|--------|------------------|-----------------|
| **Support duration** | Up to 24 months | 14 months |
| **Extra cost** | Only during extended period (months 15-24) | None |
| **Patch timing** | Same as Regular | Standard timing |
| **Minor version auto-upgrades** | NO (except at end of extended support) | YES |
| **Manual control** | Maximum — you control when minors happen | Standard auto-upgrade behavior |

## Key Tradeoffs

### ✅ Advantages
- **Longer support window** — 24 months vs 14 months reduces upgrade frequency
- **Maximum control over minor upgrades** — only patches are auto-applied, minors require manual initiation
- **Cost during standard period** — no extra charge for first 14 months
- **Compliance-friendly** — ideal for regulated environments requiring slow change cycles

### ⚠️ Considerations
- **Extra cost during extended support** — additional charges apply only during months 15-24
- **Manual minor upgrade responsibility** — you must plan and execute minor version upgrades
- **Patches still auto-apply** — security patches arrive at the same cadence as Regular channel
- **Node version management** — nodes will auto-upgrade to match control plane minor version unless blocked by exclusions

## Migration Strategy

### Pre-Migration Checks

```bash
# Check current version availability in Extended channel
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels.extended)"

# Verify 1.31 is available in Extended
# If not, you'll be "ahead of channel" until Extended catches up
```

⚠️ **Version availability warning:** If your current version (1.31) isn't yet available in Extended channel, your cluster will be "ahead of channel" and won't receive auto-upgrades until Extended's version reaches 1.31.

### Migration Commands

```bash
# Step 1: Apply temporary "no upgrades" exclusion (prevents immediate auto-upgrade)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d "+7 days" +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades

# Step 2: Switch to Extended channel
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended

# Step 3: Configure for maximum control (recommended)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --maintenance-window-start "2024-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Step 4: Remove temporary exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "channel-migration"
```

## Recommended Configuration for Production

For maximum control while maintaining security posture:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --maintenance-patch-version-disruption-interval=7776000s \
  --maintenance-window-start "2024-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

This gives you:
- ✅ **24-month support** with cost only during extended period
- ✅ **Auto-applied security patches** (no minor or node auto-upgrades)  
- ✅ **Patches limited to once every 90 days** within Saturday 2-6 AM window
- ✅ **Manual control** over when minor upgrades happen
- ✅ **Persistent exclusion** that tracks End of Support automatically

## Operational Changes

### What Changes
- **Minor upgrades become manual** — you must initiate them when ready
- **Planning responsibility** — track when minor versions approach EoS
- **Cost visibility** — monitor extended support charges after month 14

### What Stays the Same  
- **Security patches auto-apply** — same timing as Regular channel
- **Node pool behavior** — nodes track control plane minor version (unless blocked by "no minor or node" exclusion)
- **Maintenance windows** — still respected for patch timing

## Minor Upgrade Workflow on Extended

When you're ready for a minor version upgrade:

```bash
# Check available versions
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels.extended)"

# Upgrade control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# Upgrade node pools (if not using "no minor or node" exclusion)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

## Cost Planning

- **Months 1-14:** No extra cost (same as Regular channel)
- **Months 15-24:** Additional extended support charges apply
- **After 24 months:** Automatic upgrade to next supported minor version

## Recommendation

✅ **Proceed with Extended channel migration** for production clusters needing maximum stability and control. The combination of 24-month support + manual minor upgrade control + persistent exclusions makes Extended ideal for regulated environments and disruption-intolerant workloads.

The "no minor or node upgrades" exclusion is the key configuration — it prevents both control plane minor upgrades AND node upgrades while still allowing security patches. This gives you the maximum control you likely want for production.