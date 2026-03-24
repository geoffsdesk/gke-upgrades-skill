# GKE Upgrade Timing & Visibility Guide

Your VP needs predictable upgrade schedules. Here's how to achieve maximum visibility and control over GKE upgrade timing.

## Current Upgrade Status Check

First, assess your clusters' current auto-upgrade trajectory:

```bash
# Check auto-upgrade targets and timing for all clusters
for cluster in $(gcloud container clusters list --format="value(name)"); do
  echo "=== $cluster ==="
  gcloud container clusters get-upgrade-info $cluster --region=REGION \
    --format="table(
      name,
      autoUpgradeStatus.autoUpgradeTarget.minorVersion,
      autoUpgradeStatus.autoUpgradeTarget.patchVersion,
      autoUpgradeStatus.endOfStandardSupportTimestamp,
      autoUpgradeStatus.endOfExtendedSupportTimestamp
    )"
done

# Check release channels and maintenance windows
gcloud container clusters list \
  --format="table(
    name,
    releaseChannel.channel,
    maintenancePolicy.window.recurringWindow.window.startTime,
    maintenancePolicy.exclusions[].name
  )"
```

## Upgrade Prediction Tools

### 1. GKE Release Schedule (Primary Planning Tool)

**URL:** https://cloud.google.com/kubernetes-engine/docs/release-schedule

This shows **best-case estimates** for when versions arrive in each channel:
- When new versions become **available** in your channel
- Earliest possible **auto-upgrade dates** (~2 weeks advance notice)
- **End of Support** dates for planning mandatory upgrades

**Key insight:** Upgrades won't happen BEFORE these dates, but may happen later due to progressive rollout, maintenance windows, or technical issues.

### 2. Scheduled Upgrade Notifications (72-Hour Advance Notice)

Enable proactive notifications for control plane upgrades:

```bash
# Enable 72-hour advance notifications (Preview - available March 2026)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --send-scheduled-upgrade-notifications

# Query scheduled upgrades via Cloud Logging
gcloud logging read 'resource.type="gke_cluster" 
  jsonPayload.eventType="SCHEDULED_UPGRADE_NOTIFICATION"' \
  --limit=10 --format=json
```

**What you get:** Notification 72 hours before GKE initiates an auto-upgrade, including:
- Cluster name and location
- Current version → target version
- Planned upgrade start time
- Type of upgrade (control plane/nodes, minor/patch)

**Note:** Node pool notifications will follow in a later release.

### 3. Progressive Rollout Tracking

GKE rolls out new releases across regions over 4-5 business days. Check if your region has received the upgrade yet:

```bash
# Check version availability in your region
gcloud container get-server-config --region=REGION \
  --format="yaml(channels[].availableVersions)"

# Compare with global release schedule to see rollout progress
```

## Maximum Predictability Configuration

For VP-level predictability, implement this configuration pattern:

### Option A: Maintenance Windows + Manual Triggering (Recommended)

**Best for:** Teams that want upgrades to happen at EXACTLY the right time.

```bash
# Set maintenance window (upgrades only happen during this time)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-window-start "2024-02-03T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Add "no minor or node upgrades" exclusion (only security patches auto-apply)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Manually trigger upgrades during approved windows
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --cluster-version TARGET_VERSION
```

**Result:** Security patches auto-apply during Saturday 2-6 AM windows. Minor version upgrades only happen when you manually trigger them during approved times.

### Option B: Disruption Intervals (Regulated Environments)

**Best for:** Organizations needing minimum gaps between upgrades.

```bash
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-minor-version-disruption-interval=45d \
  --maintenance-patch-version-disruption-interval=7d \
  --maintenance-window-start "2024-02-03T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Result:** Minor upgrades happen at most every 45 days, patches every 7 days, only during Saturday maintenance windows.

## Multi-Environment Upgrade Sequencing

For predictable dev → staging → prod rollouts:

### Simple Approach (Recommended)
Use different release channels with "no minor" exclusions:

```bash
# Dev clusters: Regular channel (gets versions first)
gcloud container clusters update dev-cluster \
  --release-channel regular

# Staging: Stable channel (gets versions ~4 weeks after Regular)  
gcloud container clusters update staging-cluster \
  --release-channel stable

# Prod: Stable + exclusion (only manual minor upgrades)
gcloud container clusters update prod-cluster \
  --release-channel stable \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Timeline:** Dev gets new versions first → Staging gets them ~4 weeks later → You manually upgrade Prod after validating Staging.

### Advanced Approach: Rollout Sequencing
For 10+ clusters needing automated orchestration:

```bash
# Configure fleet-based rollout sequencing
gcloud container fleet clusterupgrade update \
  --project=PROJECT_ID \
  --upstream-fleet=dev-fleet-project \
  --default-upgrade-soaking=7d
```

**Result:** GKE automatically upgrades dev fleet first, waits 7 days, then upgrades staging/prod fleets in sequence.

## Visibility Dashboard Setup

Create ongoing visibility for your VP:

### 1. Cloud Monitoring Dashboard

```bash
# Create custom dashboard with upgrade metrics
gcloud monitoring dashboards create --config-from-file=- <<EOF
{
  "displayName": "GKE Upgrade Status",
  "mosaicLayout": {
    "tiles": [
      {
        "width": 6,
        "height": 4,
        "widget": {
          "title": "Cluster Versions",
          "xyChart": {
            "dataSets": [{
              "timeSeriesQuery": {
                "timeSeriesFilter": {
                  "filter": "resource.type=\"gke_cluster\"",
                  "aggregation": {
                    "alignmentPeriod": "3600s"
                  }
                }
              }
            }]
          }
        }
      }
    ]
  }
}
EOF
```

### 2. Automated Status Reports

```bash
#!/bin/bash
# Weekly upgrade status report script
echo "GKE Upgrade Status Report - $(date)"
echo "=================================="

for cluster in $(gcloud container clusters list --format="value(name)"); do
  echo "Cluster: $cluster"
  
  # Current version and upgrade target
  gcloud container clusters get-upgrade-info $cluster --region=REGION \
    --format="table(autoUpgradeStatus.autoUpgradeTarget.minorVersion:label='Target Version')"
  
  # Next maintenance window
  gcloud container clusters describe $cluster --region=REGION \
    --format="value(maintenancePolicy.window.recurringWindow.window.startTime)"
  
  echo "---"
done
```

## Stakeholder Communication Template

**For your VP's external communication:**

```
GKE Upgrade Schedule - [Month Year]

PREDICTABLE TIMELINE:
✓ Maintenance windows: Every Saturday 2-6 AM PT
✓ 72-hour advance notice via automated alerts  
✓ Security patches: Auto-applied during maintenance windows
✓ Feature upgrades: Manually triggered after validation

UPCOMING UPGRADES:
• Dev clusters: [Date] - Version X.Y.Z (automatic)
• Staging clusters: [Date + 4 weeks] - Version X.Y.Z (automatic)  
• Prod clusters: [Date + 6 weeks] - Version X.Y.Z (manual after staging validation)

CONTROLS IN PLACE:
• Zero business-hour disruptions (weekend-only windows)
• Ability to pause upgrades during critical business periods
• 45-day minimum between major upgrades
• 7-day minimum between security updates
```

## Emergency Upgrade Deferrals

When critical business events require freezing upgrades:

```bash
# Apply 30-day "no upgrades" exclusion (blocks everything including security patches)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "black-friday-freeze" \
  --add-maintenance-exclusion-start-time "2024-11-20T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-20T00:00:00Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**Warning:** This defers security patches. Use sparingly and plan catch-up upgrades immediately after the freeze period.

## Key Messaging for Your VP

**Bottom line for executive communication:**

1. **"We have 72-hour advance notice"** - GKE tells us exactly when upgrades will happen
2. **"Upgrades only happen during approved windows"** - Saturday 2-6 AM, never during business hours  
3. **"We control the pace"** - Security patches weekly, feature upgrades every 45 days minimum
4. **"We can pause for critical events"** - Black Friday, product launches, etc.
5. **"Full audit trail"** - Every upgrade logged and tracked via Cloud Logging

This gives you predictability for stakeholder management while maintaining security posture. The 72-hour notifications are the key tool for executive-level visibility.