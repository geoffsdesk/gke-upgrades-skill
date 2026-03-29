# GKE Upgrade Timing & Visibility Guide

Your VP needs predictable upgrade schedules for stakeholder communication. Here's how to achieve maximum visibility and control over GKE upgrade timing.

## Executive Summary

**What you can predict:**
- **72-hour advance warning** for control plane auto-upgrades (opt-in notifications)
- **Best-case dates** from the GKE release schedule (won't happen before these dates)
- **Your cluster's current auto-upgrade target** via API

**What you can control:**
- **WHEN** upgrades happen (maintenance windows)
- **HOW OFTEN** upgrades happen (disruption intervals)
- **WHAT** gets upgraded (maintenance exclusions)
- **ORDER** across environments (rollout sequencing)

## Immediate Actions for Your VP

### 1. Enable 72-Hour Upgrade Notifications

Get advance warning for every auto-upgrade:

```bash
# Enable scheduled upgrade notifications (control plane only, preview March 2026)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --send-scheduled-upgrade-notifications
```

This sends notifications to Cloud Logging 72 hours before each auto-upgrade, giving your VP time to communicate with stakeholders or apply temporary exclusions if needed.

### 2. Check Current Auto-Upgrade Status

See exactly what each cluster will upgrade to next:

```bash
# Get auto-upgrade targets for all clusters
for cluster in $(gcloud container clusters list --format="value(name,zone)" | tr '\t' ' '); do
  name=$(echo $cluster | cut -d' ' -f1)
  zone=$(echo $cluster | cut -d' ' -f2)
  echo "=== $name ==="
  gcloud container clusters get-upgrade-info $name --region $zone \
    --format="table(minorTargetVersion,patchTargetVersion,autoUpgradeStatus)"
done
```

### 3. Set Predictable Maintenance Windows

Control exactly when upgrades can happen:

```bash
# Saturday 2-6 AM maintenance window (4-hour window)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-window-start "2026-01-04T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**For ultimate predictability:** Don't wait for auto-upgrades. Initiate upgrades manually during your chosen maintenance window. This guarantees the upgrade happens at the exact time you communicate to stakeholders.

## Long-Range Planning Tools

### GKE Release Schedule

The [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) shows:
- When new versions become available in each channel
- Estimated auto-upgrade dates (best-case scenarios)
- End of support dates

**Timeline expectations:**
- **Patch versions:** ~2 weeks to progress from Rapid → Regular → Stable
- **Minor versions:** ~1 month from Rapid availability to Regular availability
- **Auto-upgrades:** Happen within 1-2 weeks after a version becomes the channel's target

### Release Channel Strategy for Predictability

Choose channels based on your VP's communication needs:

| Channel | Predictability | Timeline | Best for |
|---------|---------------|----------|----------|
| **Stable** | Highest | Longest validation period | Executive visibility, change control |
| **Regular** | Good | Balanced validation | Most production workloads |
| **Extended** | Maximum control | Manual minor upgrades only | Regulated environments, maximum planning time |

**Recommendation for executive visibility:** Use **Stable** channel for production. It provides the most predictable timeline and longest advance notice.

## Advanced Control Mechanisms

### Disruption Intervals (Control Upgrade Frequency)

Prevent back-to-back upgrades:

```bash
# Minimum 30 days between minor upgrades, 7 days between patches
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-minor-version-disruption-interval=2592000s \
  --maintenance-patch-version-disruption-interval=604800s
```

### Maintenance Exclusions (Control Upgrade Scope)

For regulated environments or during critical business periods:

```bash
# Block all upgrades during Black Friday (30-day max)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "BFCM-freeze" \
  --add-maintenance-exclusion-start "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end "2024-12-02T00:00:00Z" \
  --add-maintenance-exclusion-scope no_upgrades

# Allow only security patches, block disruptive changes
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

### Multi-Cluster Rollout Sequencing

Control the order of upgrades across environments:

```bash
# Configure dev → staging → prod sequence with 7-day soak between stages
gcloud container fleet clusterupgrade update \
  --project PROJECT_ID \
  --upstream-fleet UPSTREAM_PROJECT_ID \
  --default-upgrade-soaking 7d
```

## Monitoring & Alerting Setup

### Cloud Logging Queries for Upgrade Events

```bash
# All upgrade-related events
resource.type="gke_cluster"
protoPayload.metadata.operationType=~"(UPDATE_CLUSTER|UPGRADE_MASTER)"

# Scheduled upgrade notifications (72h advance)
resource.type="gke_cluster"
jsonPayload.reason="ScheduledUpgrade"
```

### Pub/Sub Notifications for Proactive Alerting

Set up cluster event subscriptions to get real-time notifications:

```bash
# Create topic for cluster events
gcloud pubsub topics create gke-cluster-events

# Subscribe clusters to publish events
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --enable-cluster-event-audit-logs
```

## Executive Communication Template

Here's a template your VP can use for stakeholder communication:

---

**GKE Maintenance Schedule Update**

**Upcoming Maintenance Windows:**
- **When:** Every Saturday, 2:00-6:00 AM PST
- **Impact:** Potential brief service interruption during node upgrades
- **Advance Notice:** 72-hour notifications for all scheduled upgrades

**Current Status:**
- Production clusters on Stable channel (most predictable timeline)
- Next minor version upgrade estimated: [DATE from release schedule]
- All critical business periods protected with maintenance exclusions

**Controls in Place:**
- Maintenance windows restrict upgrades to off-peak hours
- 30-day minimum interval between major upgrades
- Emergency exclusions available for critical business events

---

## Recommended Configuration for Maximum Predictability

Combine these settings for your VP's requirements:

```bash
# Production cluster configuration for maximum predictability
gcloud container clusters update PROD_CLUSTER \
  --region REGION \
  --release-channel stable \
  --maintenance-window-start "2026-01-04T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA" \
  --maintenance-minor-version-disruption-interval=2592000s \
  --maintenance-patch-version-disruption-interval=604800s \
  --send-scheduled-upgrade-notifications \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**This configuration provides:**
- ✅ 72-hour advance notifications
- ✅ Saturday 2-6 AM maintenance windows only  
- ✅ Minimum 30 days between minor upgrades
- ✅ Minimum 7 days between patches
- ✅ Manual control over all disruptive upgrades
- ✅ Automatic security patches on control plane

## Key Message for Your VP

**"We now have 72-hour advance notice of all upgrades, with maintenance restricted to Saturday early morning windows. Major upgrades are under manual control, and security patches happen automatically during our defined maintenance windows. This gives us predictable timing for stakeholder communication while maintaining our security posture."**

The combination of Stable channel + scheduled notifications + maintenance windows + disruption intervals gives you the most predictable upgrade timeline possible while still benefiting from GKE's automated lifecycle management.