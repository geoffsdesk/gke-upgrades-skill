# GKE Upgrade Timing & Visibility Guide

Your VP needs predictable upgrade timelines for stakeholder communication. Here's how to get visibility and control over when GKE upgrades happen.

## Current Upgrade Status Check

First, check what upgrades are coming for each cluster:

```bash
# Check auto-upgrade targets and timing for each cluster
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Example output shows:
# - autoUpgradeStatus: "UPGRADE_AVAILABLE" or "UP_TO_DATE"  
# - minorTargetVersion: "1.31.3-gke.1146000"
# - patchTargetVersion: "1.31.4-gke.1200000" 
# - endOfStandardSupportTimestamp: "2025-12-15T00:00:00Z"
```

Run this for all clusters to build your upgrade forecast.

## GKE's Upgrade Timing Tools

### 1. Scheduled Upgrade Notifications (72-hour advance notice)

**NEW in March 2026:** GKE offers opt-in notifications 72 hours before control plane auto-upgrades.

```bash
# Enable 72h advance notifications
gcloud container clusters update CLUSTER_NAME \
    --send-scheduled-upgrade-notifications \
    --region REGION
```

These appear in Cloud Logging with filter:
```
resource.type="gke_cluster"
jsonPayload.eventType="SCHEDULED_UPGRADE_NOTIFICATION"
```

Set up alerting on these logs to get advance warning for stakeholder communication.

### 2. GKE Release Schedule (longer-range planning)

The [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) shows:
- When new versions become available in each channel
- Estimated auto-upgrade dates (best-case timeline)
- End of support dates

**Key insight:** These are "no earlier than" dates. Upgrades won't happen before these dates but may happen later due to:
- Progressive rollout across regions (4-5 business days)
- Maintenance windows
- Internal freezes (holiday periods, etc.)
- Technical pauses

### 3. Release Channel Progression Timeline

Understanding channel timing helps predict when upgrades reach your clusters:

| Channel | When new versions arrive | Typical progression |
|---------|-------------------------|-------------------|
| **Rapid** | ~2 weeks after K8s upstream | Patches: ~1 week between stages |
| **Regular** | After Rapid validation | Patches: ~2 weeks after Rapid |
| **Stable** | After Regular validation | Patches: ~3 weeks after Rapid |
| **Extended** | Same as Regular initially | Minor upgrades are MANUAL only |

**For predictable timing:** Use Stable channel + maintenance windows. This gives you the slowest automatic upgrade cadence with predictable time slots.

## Controlling Upgrade Timing

### Option A: Maintenance Windows (when upgrades happen)

Set recurring windows during acceptable business hours:

```bash
# Saturday 2-6 AM maintenance window
gcloud container clusters update CLUSTER_NAME \
    --maintenance-window-start "2024-01-06T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA" \
    --region REGION
```

**Guarantee:** Auto-upgrades will only start during these windows. Manual upgrades bypass windows entirely.

### Option B: Maintenance Exclusions (what upgrades are blocked)

For maximum control, use exclusions to block specific upgrade types:

```bash
# Block ALL upgrades during critical periods (30-day max)
gcloud container clusters update CLUSTER_NAME \
    --add-maintenance-exclusion-name "q4-code-freeze" \
    --add-maintenance-exclusion-start "2024-11-01T00:00:00Z" \
    --add-maintenance-exclusion-end "2024-12-31T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades \
    --region REGION

# Block minor/node upgrades, allow security patches (no time limit)
gcloud container clusters update CLUSTER_NAME \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support \
    --region REGION
```

### Option C: Extended Channel (maximum control)

For the most predictable upgrade experience:

```bash
# Migrate to Extended channel
gcloud container clusters update CLUSTER_NAME \
    --release-channel extended \
    --region REGION
```

**Extended channel benefits:**
- Up to 24 months support (vs. 14 months)
- Minor upgrades are MANUAL only (except at end of extended support)
- Only patches are auto-applied
- You control exactly when minor version changes happen

## Recommended Configuration for VP-Level Predictability

For maximum predictability and stakeholder communication:

```bash
# Ultimate predictability setup
gcloud container clusters update CLUSTER_NAME \
    --release-channel extended \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support \
    --maintenance-window-start "2024-01-06T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA" \
    --send-scheduled-upgrade-notifications \
    --region REGION
```

This gives you:
- ✅ **72-hour advance warning** via Cloud Logging
- ✅ **Only security patches auto-applied** (no disruptive changes)
- ✅ **Patches limited to Saturday 2-6 AM** windows
- ✅ **Full control over minor upgrades** (you decide when)
- ✅ **24-month support** per version
- ✅ **Persistent exclusions** that auto-renew

## Stakeholder Communication Templates

### For the VP: Quarterly Upgrade Planning

"Our GKE clusters are configured for maximum predictability:
- **Automatic security patches** apply during Saturday 2-6 AM windows with 72h advance notice
- **Major upgrades** (new Kubernetes versions) happen only when we initiate them
- **Extended support** gives us up to 24 months per version
- **Next planned upgrade:** [Date] during [maintenance window]"

### For Engineering Teams: Technical Timeline

```
Cluster Upgrade Schedule - Q1 2024

Production Clusters (Extended channel):
├── cluster-prod-us-central1 → Current: 1.28.x → Next minor: TBD (manual)
├── cluster-prod-europe-west1 → Current: 1.28.x → Next minor: TBD (manual)
└── Maintenance windows: Saturdays 2-6 AM with 72h notifications

Staging Clusters (Regular channel):
├── cluster-staging → Current: 1.29.x → Next minor: ~Feb 15 (auto)
└── Maintenance windows: Fridays 2-4 AM

Security patches: Auto-applied weekly during maintenance windows
Major version upgrades: Planned quarterly, manually triggered
```

## Monitoring & Alerting Setup

Set up alerts on the scheduled upgrade notifications:

```bash
# Cloud Monitoring alert policy for scheduled upgrades
gcloud alpha monitoring policies create --policy-from-file=- <<EOF
displayName: "GKE Scheduled Upgrade Alert"
conditions:
- displayName: "Upgrade notification received"
  conditionThreshold:
    filter: 'resource.type="gke_cluster" jsonPayload.eventType="SCHEDULED_UPGRADE_NOTIFICATION"'
    comparison: COMPARISON_GREATER_THAN
    thresholdValue: 0
notificationChannels:
- projects/PROJECT_ID/notificationChannels/CHANNEL_ID
EOF
```

## What This Gives Your VP

1. **72-hour advance notice** for any automatic upgrades
2. **Predictable timing** (only during approved maintenance windows)
3. **Control over major changes** (minor versions are manual-only on Extended)
4. **Security compliance** (patches still auto-apply during windows)
5. **Long-term stability** (24-month support per version)

The Extended channel + maintenance exclusions approach is specifically designed for organizations that need maximum predictability and stakeholder communication control. This is the configuration I'd recommend presenting to your VP as the solution for predictable upgrade timelines.