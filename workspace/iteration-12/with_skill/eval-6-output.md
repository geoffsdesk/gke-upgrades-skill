# GKE Release Channel Migration: Rapid → Stable

## Migration Overview

Moving from Rapid to Stable is a **conservative shift** that will significantly slow your upgrade cadence and improve stability. Here's what changes:

| Aspect | Rapid (current) | Stable (target) | Impact |
|--------|----------------|-----------------|---------|
| **Version arrival** | First (~2 weeks after K8s release) | After Regular validation | **Slower access** to new features |
| **Stability** | Early adopter, no SLA for upgrade stability | Fully validated, full SLA | **Higher stability** |
| **Upgrade frequency** | ~Weekly releases | Less frequent | **Fewer disruptions** |
| **Support period** | 14 months | 14 months | No change |

## Key Implications

### 1. **Version progression will slow significantly**
- Currently on 1.32 (likely latest available)
- After migration, you'll stay on 1.32 until it's promoted to Stable channel
- New minor versions (1.33, 1.34) will arrive months later than on Rapid

### 2. **No immediate version change**
Your cluster will stay at 1.32 — channel migration doesn't trigger upgrades, it only changes future upgrade behavior.

### 3. **Auto-upgrade target changes**
Your cluster's auto-upgrade target will shift to whatever version is currently the auto-upgrade target in Stable channel (likely 1.31 or earlier).

## Pre-Migration Assessment

**Check current Stable channel versions:**
```bash
gcloud container get-server-config --zone YOUR_ZONE \
  --format="yaml(channels.STABLE)"
```

**Verify your current setup:**
```bash
# Current channel and version
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel,currentMasterVersion)"

# Current auto-upgrade target
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

## Migration Steps

### 1. **Apply migration command**
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel stable
```

### 2. **Verify migration**
```bash
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel)"
```

### 3. **Check new auto-upgrade target**
```bash
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

## Post-Migration Behavior

### Potential downgrade scenario
If Stable channel's auto-upgrade target is **older** than your current 1.32:
- **Control plane:** May be downgraded to the Stable target (requires GKE support)
- **Node pools:** May be downgraded to match

**Recommendation:** If Stable's target is older than 1.32, consider applying a temporary maintenance exclusion to prevent immediate downgrade:

```bash
# Block downgrades while Stable catches up to 1.32
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "channel-migration-hold" \
  --add-maintenance-exclusion-start-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-end-time "$(date -u -d '+90 days' +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### Future upgrade cadence
- **Before:** Weekly potential upgrades, immediate access to new K8s versions
- **After:** Upgrades only after validation in Rapid→Regular→Stable promotion path
- **Timeline:** New minor versions will arrive ~2-3 months later than on Rapid

## Risk Assessment

### Low Risk Migration
✅ **Channel migration itself is safe** — no immediate version changes
✅ **Stable channel has full SLA coverage** — more reliable than Rapid
✅ **Can always migrate back** to Rapid if needed

### Considerations
⚠️ **Slower security patches** — patches arrive later than Rapid
⚠️ **Delayed feature access** — new K8s features arrive months later  
⚠️ **Possible temporary version hold** — if Stable target < current version

## Timeline Expectations

Based on typical promotion patterns:
- **Immediate:** Channel migration completes in minutes
- **1-2 weeks:** Auto-upgrade target adjusts to Stable channel's current target
- **2-3 months:** Next minor version (1.33) arrives in Stable after validation

## Rollback Plan

If you need to revert:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel rapid
```

## Recommendation

This migration aligns well with production best practices. Most production workloads benefit from Stable channel's validation and reduced change frequency. The tradeoff of slower feature access is usually acceptable for production stability.

**Next step:** Check what version Stable channel is currently targeting, then execute the migration during your next maintenance window.