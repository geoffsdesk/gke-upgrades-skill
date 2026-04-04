# Channel Migration: Rapid → Stable

## Key Implications

**⚠️ Critical Warning**: Moving from Rapid (1.32) to Stable when 1.32 may not yet be available in Stable will put your cluster "ahead of channel" and **freeze auto-upgrades** until Stable catches up.

### Version Availability Risk
- **Current state**: Rapid at 1.32
- **Risk**: If 1.32 isn't available in Stable yet, you'll get no auto-upgrades (patches or minor) until Stable reaches 1.32
- **Timeline**: Could be weeks of frozen upgrades, accumulating security debt

### SLA and Stability Changes
| Aspect | Rapid (current) | Stable (target) |
|--------|----------------|-----------------|
| **SLA for upgrade stability** | ❌ No SLA | ✅ Full SLA |
| **Version arrival timing** | First (~2 weeks after upstream) | Last (after Regular validation) |
| **Patch timing** | Fastest | Slowest (+4-6 weeks) |
| **Support period** | 14 months | 14 months |

### Auto-upgrade Behavior Changes
- **Patches**: Will arrive 4-6 weeks later than current
- **Minor versions**: Will arrive 2-4 months later than current
- **Predictability**: Much more predictable timing (good for production)

## Pre-Migration Checklist

```bash
# 1. Check if 1.32 is available in Stable channel
gcloud container get-server-config --zone YOUR_ZONE \
  --format="yaml(channels.STABLE.validVersions)" | grep "1.32"

# 2. Check current cluster version
gcloud container clusters describe CLUSTER_NAME \
  --zone YOUR_ZONE \
  --format="table(currentMasterVersion, nodePools[].version)"

# 3. Review GKE release schedule
# Visit: https://cloud.google.com/kubernetes-engine/docs/release-schedule
```

## Migration Plan

### Option A: Wait-then-migrate (Recommended)
If 1.32 is NOT in Stable channel yet:

```bash
# 1. Add temporary "no upgrades" exclusion to prevent auto-upgrades during planning
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "channel-migration-freeze" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time $(date -u -d "+7 days" +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_upgrades

# 2. Wait for 1.32 to appear in Stable (check weekly)
# 3. Then migrate channel + remove exclusion
```

### Option B: Downgrade-then-migrate (If urgent)
If you need Stable channel immediately and 1.32 isn't available:

```bash
# 1. Check latest version available in Stable
gcloud container get-server-config --zone YOUR_ZONE \
  --format="yaml(channels.STABLE)" | grep validVersions -A 10

# 2. Downgrade control plane to highest Stable version (e.g., 1.31.x)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone YOUR_ZONE \
  --master \
  --cluster-version STABLE_VERSION

# 3. Then migrate channel
```

## Channel Migration Commands

```bash
# 1. Apply temporary exclusion to control timing
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time $(date -u -d "+1 day" +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_upgrades

# 2. Migrate to Stable channel
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --release-channel stable

# 3. Verify channel change
gcloud container clusters describe CLUSTER_NAME \
  --zone YOUR_ZONE \
  --format="value(releaseChannel.channel)"

# 4. Check auto-upgrade target in new channel
gcloud container clusters get-upgrade-info CLUSTER_NAME \
  --region YOUR_REGION

# 5. Remove exclusion when ready for auto-upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --remove-maintenance-exclusion channel-migration
```

## Post-Migration Configuration

### Set Conservative Maintenance Controls
Since this is production, configure appropriate upgrade controls:

```bash
# Configure maintenance window (example: Saturday 2-6 AM)
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --maintenance-window-start "2024-12-14T02:00:00Z" \
  --maintenance-window-end "2024-12-14T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Optional: Add "no minor upgrades" exclusion for maximum control
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "production-minor-control" \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Validation Steps

```bash
# 1. Confirm channel
gcloud container clusters describe CLUSTER_NAME \
  --zone YOUR_ZONE \
  --format="value(releaseChannel.channel)"
# Expected: "STABLE"

# 2. Check auto-upgrade behavior
gcloud container clusters get-upgrade-info CLUSTER_NAME \
  --region YOUR_REGION

# 3. Verify maintenance window
gcloud container clusters describe CLUSTER_NAME \
  --zone YOUR_ZONE \
  --format="value(maintenancePolicy)"
```

## Timeline Expectations

- **Channel migration**: Immediate (API call)
- **First Stable auto-upgrade**: Only after 1.32+ becomes available in Stable
- **Patch cadence**: Expect patches 4-6 weeks later than before
- **Minor versions**: Expect 2-4 months later than Rapid

## Risk Mitigation

1. **Security patches**: If frozen ahead-of-channel, monitor CVEs and consider manual patches for critical issues
2. **Version drift**: Don't let other environments stay on Rapid if they need to match production
3. **Rollback**: Can migrate back to Rapid, but timing will be off-cycle

**Bottom line**: This is the right move for production stability, but plan the timing carefully to avoid getting frozen ahead-of-channel. The SLA improvement and predictable upgrade timing are worth the slower patch cadence for production workloads.