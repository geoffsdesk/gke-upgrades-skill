# GKE Upgrade Timing and Visibility Guide

Your VP needs **predictable upgrade timing** for stakeholder communication. Here's how to achieve that with GKE's timing control and visibility tools.

## Primary Control Mechanisms

### 1. Release Channel Selection (Primary Cadence Control)

**Channel timing characteristics:**
- **Stable**: Slowest upgrade cadence (~4-6 weeks after Rapid for new versions)
- **Regular**: Balanced timing (~2-3 weeks after Rapid)  
- **Rapid**: Fastest cadence (new versions within ~2 weeks of upstream K8s release)
- **Extended**: Same timing as Regular, but versions stay supported for up to 24 months

**Recommendation for predictability:** Use **Stable channel** for maximum lead time between version availability and auto-upgrade.

### 2. Maintenance Windows (When Upgrades Happen)

Set recurring windows aligned with your change management process:

```bash
gcloud container clusters update CLUSTER_NAME \
    --maintenance-window-start "2024-02-03T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

This ensures upgrades only happen during Saturday 2-6 AM windows, making timing predictable.

### 3. Maintenance Exclusions (Block Specific Upgrade Types)

For maximum control during sensitive periods:

```bash
# Block all upgrades during code freeze (max 30 days)
gcloud container clusters update CLUSTER_NAME \
    --add-maintenance-exclusion-name "Q4-freeze" \
    --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-12-15T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades

# Block minor versions only (allows security patches)
gcloud container clusters update CLUSTER_NAME \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

## Upgrade Visibility Tools

### 1. Scheduled Upgrade Notifications (72-hour advance warning)

**NEW**: GKE now provides scheduled upgrade notifications 72 hours before auto-upgrades:

```bash
# Enable notifications
gcloud container clusters update CLUSTER_NAME \
    --send-scheduled-upgrade-notifications
```

Notifications appear in Cloud Logging with filter:
```
resource.type="gke_cluster"
jsonPayload.type="SCHEDULED_UPGRADE_NOTIFICATION"
```

### 2. GKE Release Schedule (Long-range planning)

The [GKE Release Schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) shows:
- When new versions become available in each channel
- **Estimated auto-upgrade dates** (~2 weeks advance notice)
- End of Support timelines

**Key for your VP:** This provides ~2-4 weeks of advance visibility beyond the 72-hour notification.

### 3. Auto-upgrade Status API

Check what version your cluster will upgrade to next:

```bash
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

Example output shows:
- `autoUpgradeStatus`: Whether auto-upgrades are enabled
- `minorTargetVersion`: Next minor version for auto-upgrade
- `patchTargetVersion`: Next patch version
- `endOfStandardSupportTimestamp`: When current version reaches EoS

## Recommended VP-Ready Upgrade Predictability Strategy

### Configuration for Maximum Predictability

```bash
# 1. Use Stable channel for slowest cadence
gcloud container clusters update CLUSTER_NAME \
    --release-channel stable

# 2. Set predictable maintenance windows
gcloud container clusters update CLUSTER_NAME \
    --maintenance-window-start "2024-01-06T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# 3. Enable advance notifications
gcloud container clusters update CLUSTER_NAME \
    --send-scheduled-upgrade-notifications

# 4. Block minor upgrades, allow patches (optional for max control)
gcloud container clusters update CLUSTER_NAME \
    --add-maintenance-exclusion-scope no_minor_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

### Timeline Visibility Dashboard

Create a monitoring dashboard showing:

```bash
# Check all clusters' upgrade status
for cluster in $(gcloud container clusters list --format="value(name)"); do
    echo "=== $cluster ==="
    gcloud container clusters get-upgrade-info $cluster --region=REGION \
        --format="table(
            autoUpgradeStatus,
            minorTargetVersion,
            patchTargetVersion,
            endOfStandardSupportTimestamp
        )"
done
```

## Ultimate Predictability: User-Initiated Upgrades

For **maximum control**, use maintenance exclusions to block auto-upgrades and trigger upgrades manually during planned windows:

```bash
# Block auto-upgrades
gcloud container clusters update CLUSTER_NAME \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support

# Manually upgrade during planned maintenance window
gcloud container clusters upgrade CLUSTER_NAME \
    --cluster-version TARGET_VERSION
```

**Trade-off:** This gives you 100% control over WHEN upgrades happen, but requires internal processes to monitor for new versions and security patches.

## Multi-cluster Progressive Rollout (For Large Fleets)

If you have multiple clusters, use **rollout sequencing** to control the order:

```bash
# Configure dev → staging → prod progression with soak time
gcloud container fleet clusterupgrade update \
    --upstream-fleet=projects/PROJECT/locations/global/fleets/dev-fleet \
    --default-upgrade-soaking=7d
```

This ensures dev upgrades first, 7-day soak period, then staging, then prod.

## Executive Summary for Your VP

**Current Timing Predictability:**
- **2-4 weeks advance notice**: GKE Release Schedule shows estimated dates
- **72 hours advance notice**: Scheduled upgrade notifications (enable now)
- **Day/time control**: Maintenance windows ensure upgrades only happen during approved slots
- **Scope control**: Maintenance exclusions can block upgrades during sensitive periods

**Recommended Immediate Actions:**
1. Enable scheduled upgrade notifications on all clusters
2. Configure maintenance windows aligned with change windows  
3. Subscribe to the GKE Release Schedule for long-range planning
4. Consider Stable channel for maximum lead time

**Result:** Upgrades become predictable events in your change calendar, not surprises.

Would you like me to help implement any of these controls or create a specific monitoring dashboard for upgrade visibility?