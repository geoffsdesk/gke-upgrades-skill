# GKE Upgrade Timing Prediction & Control

Your VP needs predictable upgrade timelines. GKE provides several tools for visibility and control, but the level of predictability depends on your current configuration. Here's how to achieve maximum predictability:

## Current Visibility Tools

### 1. Scheduled Upgrade Notifications (Preview - March 2026)
**72-hour advance warning** for control plane auto-upgrades:
```bash
# Enable scheduled notifications
gcloud container clusters update CLUSTER_NAME \
  --enable-scheduled-upgrades \
  --region REGION
```
Notifications appear in Cloud Logging with query:
```
resource.type="gke_cluster"
jsonPayload.eventSubType="SCHEDULED_UPGRADE_NOTIFICATION"
```

### 2. GKE Release Schedule (Best-case estimates)
- **URL:** https://cloud.google.com/kubernetes-engine/docs/release-schedule
- Shows estimated dates for version availability and auto-upgrade per channel
- **Important:** These are "no earlier than" dates — upgrades won't happen before these dates but may happen later

### 3. Upgrade Info API (Current auto-upgrade target)
```bash
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```
Returns:
- `autoUpgradeStatus`: Whether auto-upgrade is enabled
- `minorTargetVersion`: Next minor version target
- `patchTargetVersion`: Next patch target
- `endOfStandardSupportTimestamp`: When current version reaches EoS

### 4. Cluster Notifications via Pub/Sub
Set up proactive alerts:
```bash
# Create topic for cluster events
gcloud pubsub topics create gke-cluster-upgrades

# Create notification config
gcloud container clusters update CLUSTER_NAME \
  --notification-config=pubsub=ENABLED,pubsub-topic=projects/PROJECT_ID/topics/gke-cluster-upgrades \
  --region REGION
```

## Achieving Maximum Predictability

### Option 1: User-Controlled Upgrades (Most Predictable)
**Best for:** Teams wanting exact timing control

```bash
# Block auto-upgrades with "no minor or node upgrades" exclusion
gcloud container clusters update CLUSTER_NAME \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --region REGION

# Set maintenance window for when you DO upgrade
gcloud container clusters update CLUSTER_NAME \
  --maintenance-window-start "2026-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA" \
  --region REGION
```

**Process:** Watch the release schedule, enable 72h notifications, then manually trigger upgrades during your maintenance window:
```bash
# When ready to upgrade (during your window)
gcloud container clusters upgrade CLUSTER_NAME \
  --cluster-version TARGET_VERSION \
  --region REGION
```

### Option 2: Controlled Auto-Upgrades (Balanced Predictability)
**Best for:** Teams wanting automation with timing control

```bash
# Configure tight maintenance window + disruption intervals
gcloud container clusters update CLUSTER_NAME \
  --maintenance-window-start "2026-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA" \
  --maintenance-minor-version-disruption-interval=2592000s \
  --maintenance-patch-version-disruption-interval=604800s \
  --region REGION
```

This gives you:
- **Patches:** Maximum once per week, only during Saturday 2-6 AM
- **Minor versions:** Maximum once per month, only during Saturday 2-6 AM
- **72h notification:** Advance warning via Cloud Logging

## Multi-Cluster Rollout Sequencing

For multiple clusters, use **rollout sequencing** to control order:

```bash
# Configure dev → staging → prod sequence
gcloud container fleet clusterupgrade update \
  --upstream-fleet=projects/PROJECT_ID/locations/global/fleets/dev-fleet \
  --default-upgrade-soaking=168h \
  --project=PROJECT_ID
```

**Timeline becomes:** Dev upgrades → 7-day soak → Staging upgrades → 7-day soak → Prod upgrades

## Timeline Factors That Affect Predictability

### Factors you CAN control:
- **Channel selection:** Stable = slowest cadence, Regular = balanced, Rapid = fastest
- **Maintenance windows:** When upgrades happen
- **Disruption intervals:** How often upgrades happen
- **Rollout sequencing:** Order across environments

### Factors you CANNOT control:
- **Progressive rollout:** GKE rolls versions across regions over 4-5 days
- **Regional availability:** Your region may get versions later than others
- **Internal freezes:** Google pauses upgrades during critical periods (BFCM, etc.)
- **Technical pauses:** Issues with specific versions can delay rollouts

## Stakeholder Communication Template

Based on your configuration, here's what you can tell stakeholders:

### For User-Controlled Upgrades:
> "Our GKE clusters upgrade during our scheduled maintenance windows (every Saturday 2-6 AM). We receive 72-hour advance notice of available upgrades and choose when to apply them within our window. Next scheduled maintenance windows: [dates]. We control exactly when upgrades happen."

### For Controlled Auto-Upgrades:
> "Our GKE clusters auto-upgrade during Saturday 2-6 AM maintenance windows, with patches limited to once per week and minor versions once per month. We receive 72-hour advance notice. Upgrades will not happen outside these windows. Next possible upgrade windows: [dates]."

### For Multi-Cluster:
> "Our clusters upgrade in sequence: dev first, then staging after 7 days, then production after another 7 days. Each environment only upgrades during its Saturday 2-6 AM window."

## Recommended Configuration for VP Requirements

Given the need for predictable timelines, I recommend **Controlled Auto-Upgrades** with tight maintenance windows:

```bash
# Apply to all clusters
for CLUSTER in cluster-dev cluster-staging cluster-prod; do
  gcloud container clusters update $CLUSTER \
    --maintenance-window-start "2026-01-01T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA" \
    --maintenance-minor-version-disruption-interval=2592000s \
    --maintenance-patch-version-disruption-interval=604800s \
    --enable-scheduled-upgrades \
    --region REGION
done
```

**Set up monitoring:**
```bash
# Create alert policy for upgrade notifications
gcloud alpha monitoring policies create --policy-from-file=upgrade-alert-policy.yaml
```

This gives your VP:
- ✅ **Exact time windows:** Only Saturday 2-6 AM
- ✅ **Frequency limits:** Patches max weekly, minor max monthly  
- ✅ **72h advance notice:** Time to communicate with stakeholders
- ✅ **No surprises:** Upgrades cannot happen outside defined windows
- ✅ **Automated safety:** Still gets security patches without manual intervention

The trade-off is slightly less upgrade frequency control compared to fully manual upgrades, but much better predictability than unrestricted auto-upgrades.