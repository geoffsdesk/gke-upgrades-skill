# GKE Release Channel Migration: Rapid → Stable

## Migration Overview

**Current State:** Production Standard cluster on Rapid channel (1.32)
**Target State:** Same cluster on Stable channel

This is a **safe migration** with minimal risk, but there are important timing and operational implications to understand.

## Key Implications

### 1. Version Availability Timeline
- **Rapid channel:** New versions arrive ~2 weeks after upstream Kubernetes release
- **Stable channel:** New versions arrive after validation in Rapid → Regular → Stable (typically 6-8 weeks later)
- **Your cluster will receive upgrades more slowly** — this is the intended behavior

### 2. Auto-upgrade Behavior Changes
- Current 1.32 version: Will remain until Stable channel catches up
- **No immediate upgrade** — your cluster won't downgrade or change versions during migration
- Future upgrades will follow Stable channel timeline (slower, more validated)

### 3. Production Benefits of This Move ✅
- **Improved stability:** Versions have been validated through Rapid and Regular channels first
- **Fewer surprise issues:** Bug fixes happen upstream before reaching Stable
- **Maintained SLA:** Full GKE SLA coverage (unlike Rapid which has no upgrade stability SLA)
- **Better for production:** Aligns with best practices for mission-critical workloads

### 4. Potential Concerns
- **Slower security patches:** Critical patches take longer to reach Stable
- **Feature lag:** New Kubernetes features arrive 6-8 weeks later
- **Version drift:** If you have dev/staging on different channels, versions may diverge

## Migration Runbook

### Pre-migration Checks
```bash
# Verify current state
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="table(name, currentMasterVersion, releaseChannel.channel, nodePools[].version)"

# Check available versions in Stable channel
gcloud container get-server-config --region REGION \
  --format="yaml(channels.STABLE.validVersions[])"
```

### Migration Command
```bash
# Migrate to Stable channel
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel stable
```

**Duration:** ~2-3 minutes, zero downtime

### Post-migration Verification
```bash
# Confirm channel change
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="value(releaseChannel.channel)"

# Check auto-upgrade target (should show when next upgrade will occur)
gcloud container clusters get-upgrade-info CLUSTER_NAME \
  --region REGION
```

## Recommended Controls for Production

Since this is production, consider adding upgrade controls:

### Option 1: Maintenance Windows (Recommended)
```bash
# Set weekend maintenance window (Saturday 2 AM UTC, 4-hour window)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-window-start "2025-01-11T02:00:00Z" \
  --maintenance-window-end "2025-01-11T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### Option 2: Maximum Control (If Needed)
```bash
# Block minor version auto-upgrades, allow security patches
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "prod-minor-control" \
  --add-maintenance-exclusion-scope "no_minor_or_node_upgrades" \
  --add-maintenance-exclusion-until-end-of-support
```

**Use this only if:** You need manual control over when minor versions upgrade. Most production teams find maintenance windows + Stable channel sufficient.

## Multi-environment Strategy

If you have dev/staging environments, consider this progression:
- **Dev:** Rapid channel (early testing)
- **Staging:** Regular channel (validation)  
- **Production:** Stable channel (maximum stability)

Keep environments within 1 minor version of each other to avoid drift.

## Timeline Expectations

After migration:
- **Immediate:** No version changes, cluster operates normally
- **Next 2-4 weeks:** Cluster stays on current version while Stable catches up
- **Ongoing:** Upgrades arrive 6-8 weeks after Rapid, following Stable validation timeline

## Post-Migration Checklist

```markdown
- [ ] Channel migration completed: `gcloud container clusters describe` shows `channel: STABLE`
- [ ] Maintenance window configured for off-peak hours
- [ ] Monitoring/alerting updated for new upgrade timeline expectations
- [ ] Team informed about slower upgrade cadence
- [ ] Dev/staging channel strategy reviewed for version alignment
- [ ] Security patch timeline documented (slower arrival in Stable)
```

## Summary

This migration **supports your CTO's stability goals** and follows GKE best practices for production. The trade-off is slower feature/patch delivery for better stability. The migration itself is safe and immediate — your operational changes will be in managing the new, more conservative upgrade timeline.

Would you like me to elaborate on any specific aspect, such as the maintenance window configuration or multi-environment channel strategy?