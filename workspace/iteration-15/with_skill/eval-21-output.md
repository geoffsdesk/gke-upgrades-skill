# Extended Release Channel Migration Plan

## Key Tradeoffs

### Benefits of Extended Channel
- **Up to 24 months support** for versions 1.27+ (vs 14 months standard)
- **Same SLA as Regular/Stable** - full production support
- **Delayed EoS enforcement** - more flexibility around version lifecycle
- **Better for compliance environments** requiring slower upgrade cycles

### Important Limitations
- **Minor upgrades NOT automated** during extended support period - only patches auto-apply
- **Additional cost** applies ONLY during months 15-24 (extended period) - no extra charge during standard 14-month period
- **Manual planning required** - you must proactively schedule minor upgrades before extended support expires
- **Same version arrival timing as Regular** - Extended doesn't delay when new versions become available, just extends how long old versions are supported

### Operational Impact
**Current state (Regular):** Fully automated minor upgrades according to GKE's schedule
**After Extended:** You control when minor upgrades happen, but must plan and execute them yourself

## Migration Steps

### 1. Pre-migration Check
```bash
# Verify current version is available in Extended channel
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels.EXTENDED.validVersions)"

# Check if 1.31 is listed - if not, your cluster will be "ahead of channel"
```

### 2. Switch to Extended Channel
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

### 3. Configure Upgrade Control
Since you'll need to manage minor upgrades manually, set up maintenance exclusions:

```bash
# Block automatic minor upgrades - you'll control timing
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "manual-minor-control" \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

This allows patches but blocks minor upgrades until you manually trigger them.

## Migration Timing Warning

⚠️ **Version Availability Check Required**

If Kubernetes 1.31 is not yet available in the Extended channel:
- Your cluster will be "ahead of channel" 
- You'll receive NO auto-upgrades (including patches) until Extended catches up to 1.31
- Check the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) for Extended channel version progression

## Recommended Workflow After Migration

### Quarterly Planning Process
1. **Review available versions** in Extended channel
2. **Plan minor upgrade** during maintenance window
3. **Test in staging** (keep staging on Regular for early validation)
4. **Execute production upgrade** manually when ready

### Manual Minor Upgrade Commands
```bash
# When ready to upgrade (e.g., 1.31 → 1.32)
# 1. Control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.xxxx

# 2. Node pools (after CP completes)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxxx
```

## Multi-Environment Strategy

**Recommended approach:**
- **Dev/Staging:** Keep on Regular channel for early issue detection
- **Production:** Extended channel with manual minor upgrades
- **Sync timing:** Upgrade staging 2-4 weeks before production to validate

This gives you the Extended channel's flexibility while maintaining a validation pipeline.

## Cost Considerations

- **Months 1-14:** Same cost as any release channel
- **Months 15-24:** Additional Extended support fee applies
- **Planning horizon:** Budget for extended support costs if you plan to use versions beyond 14 months

## Alternative: "No Minor" Exclusions on Regular

If the main goal is upgrade control (not 24-month support), consider staying on Regular with:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

This gives you manual minor upgrade control without Extended channel complexity, but you're still bound by the 14-month support lifecycle.

## Validation After Migration

```bash
# Confirm channel change
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel)"

# Check auto-upgrade target (should respect your exclusions)
gcloud container clusters get-upgrade-info CLUSTER_NAME \
  --region REGION
```

**Bottom line:** Extended channel is excellent for compliance-driven environments that need longer support lifecycles and are comfortable managing upgrade timing internally. The key shift is from "GKE decides when" to "you decide when" for minor upgrades.