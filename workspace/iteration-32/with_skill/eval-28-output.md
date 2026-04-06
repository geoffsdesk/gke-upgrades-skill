# GKE Upgrade Predictability & Visibility Guide

Your VP needs certainty for stakeholder communication. Here's how to achieve predictable upgrade timing and get advance visibility into upcoming upgrades.

## Upgrade Timing Control Mechanisms

### 1. Maintenance Windows (Primary Control)
**Most reliable for timing predictability.** Auto-upgrades only happen during your specified windows.

```bash
# Set predictable weekly window (e.g., Saturdays 2-6 AM)
gcloud container clusters update CLUSTER_NAME \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Key insight:** Manual upgrades bypass maintenance windows. If you trigger upgrades yourself during the window, you get **exact timing control** rather than waiting for GKE's auto-upgrade within the window.

### 2. Release Channel Selection (Cadence Control)
Controls **how soon** upgrades become available:

| Channel | Upgrade Cadence | Best For |
|---------|----------------|----------|
| **Stable** | Slowest (~2 weeks behind Regular) | Maximum predictability |
| **Regular** | Balanced (default) | Most production workloads |
| **Extended** | Manual minor upgrades only | Ultimate control (cost during extended period) |

**For maximum predictability:** Use Stable channel + maintenance windows. Upgrades happen during your window after passing additional validation.

### 3. Maintenance Exclusions (Scope Control)
Block specific upgrade types when you need frozen periods:

```bash
# Block all upgrades during critical business periods (max 30 days)
gcloud container clusters update CLUSTER_NAME \
  --add-maintenance-exclusion-name "q4-freeze" \
  --add-maintenance-exclusion-start "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end "2024-12-15T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# Block minor versions but allow security patches (until EoS)
gcloud container clusters update CLUSTER_NAME \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Upgrade Visibility Tools

### 1. Scheduled Upgrade Notifications (72h Advance Notice)
**Most important for stakeholder communication.** GKE sends notifications 72 hours before control plane auto-upgrades.

```bash
# Enable scheduled notifications (Preview, available March 2026)
gcloud container clusters update CLUSTER_NAME \
  --enable-scheduled-upgrades

# Check Cloud Logging for notifications
gcloud logging read 'resource.type="gke_cluster" 
  protoPayload.resourceName=~"CLUSTER_NAME"
  protoPayload.methodName="google.container.v1.ClusterManager.ScheduledUpgrade"'
```

**Note:** Node pool scheduled notifications coming in a later release.

### 2. GKE Release Schedule (Long-range Planning)
The [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) shows **best-case dates** for:
- When versions become available in each channel
- Estimated auto-upgrade target dates
- End of Support dates

**Critical:** These are "no earlier than" dates. Actual upgrades may be delayed by maintenance windows, progressive rollout, or technical issues.

### 3. Auto-upgrade Status API
Check your cluster's current auto-upgrade target and timeline:

```bash
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

Example output includes:
- `autoUpgradeStatus`: Whether auto-upgrades are enabled
- `minorTargetVersion` / `patchTargetVersion`: What version GKE will upgrade to
- `endOfStandardSupportTimestamp`: EoS deadline
- `rollbackSafeUpgrade`: Whether rollback is possible

### 4. Cluster Notifications via Pub/Sub
Set up proactive alerting for all upgrade events:

```bash
# Create Pub/Sub topic for cluster notifications
gcloud pubsub topics create gke-cluster-notifications

# Subscribe to cluster notifications
gcloud container clusters update CLUSTER_NAME \
  --notification-config=pubsub=projects/PROJECT_ID/topics/gke-cluster-notifications
```

Notification types you'll receive:
- **Upgrade available event** — new version is available
- **Upgrade event (start)** — upgrade has begun
- **Minor version at or near end of support** — EoS warning
- **Disruption events** — PDB violations, stuck drains during upgrades

## Recommended Configuration for Maximum Predictability

For your VP's stakeholder communication needs, this configuration provides the most predictable upgrade experience:

```bash
# 1. Stable channel for slowest, most validated upgrades
gcloud container clusters update CLUSTER_NAME \
  --release-channel stable

# 2. Predictable maintenance window
gcloud container clusters update CLUSTER_NAME \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# 3. Enable 72h advance notifications
gcloud container clusters update CLUSTER_NAME \
  --enable-scheduled-upgrades

# 4. Optional: Block minor versions, allow patches only
gcloud container clusters update CLUSTER_NAME \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# 5. Set up Pub/Sub notifications
gcloud container clusters update CLUSTER_NAME \
  --notification-config=pubsub=projects/PROJECT_ID/topics/gke-cluster-notifications
```

## Multi-Cluster Rollout Sequencing (Advanced)

If you have dev/staging/prod clusters, rollout sequencing ensures predictable ordering with soak time between environments:

```bash
# Configure fleet-based rollout sequencing
gcloud container fleet clusterupgrade update \
  --project=PROJECT_ID \
  --upstream-fleet=dev-fleet-project \
  --default-upgrade-soaking=7d
```

**Important:** All clusters must be on the **same release channel** for rollout sequencing to work.

## Communicating Timelines to Stakeholders

### Short-term (Next 2 weeks)
- **Check scheduled notifications:** 72h advance notice for control plane upgrades
- **Check auto-upgrade status:** Current target version and estimated timing
- **Maintenance windows:** Upgrades confined to your specified windows

### Medium-term (1-3 months)
- **GKE release schedule:** Best-case estimates for new versions reaching your channel
- **Channel progression:** Stable gets versions ~2 weeks after Regular
- **EoS deadlines:** Force-upgrade dates when versions reach end of support

### Long-term (3-12 months)
- **Kubernetes release cycle:** New minor versions ~3-4 times per year
- **Extended support:** Up to 24 months for versions 1.27+ (additional cost during extended period)
- **Channel strategy:** Plan channel migrations aligned with business cycles

## Sample Communication Template

For your VP's stakeholder updates:

```
GKE Upgrade Timeline - [Cluster Name]

Immediate (Next 72 hours):
• Scheduled upgrades: [None / Control plane upgrade to 1.31.8 on Saturday 2-6 AM]
• Status: [No action required / Monitoring planned upgrade]

Short-term (Next 30 days):  
• Maintenance windows: Every Saturday 2-6 AM EST
• Expected upgrades: [Security patches only / Minor version 1.32 estimated mid-February]
• Business impact: [None - patches only / Brief API unavailability during Saturday window]

Medium-term (3 months):
• Current version support ends: [March 15, 2024]
• Next major decision point: [Migrate to Extended channel vs allow auto-upgrade to 1.33]
• Maintenance exclusions planned: [Q4 freeze Nov 15 - Dec 15]
```

## Key Takeaways for Predictable Upgrades

1. **Maintenance windows + Stable channel** = most predictable timing
2. **Scheduled notifications** = 72h advance warning (control plane only today)
3. **GKE release schedule** = longer-range planning (best-case dates)
4. **Maintenance exclusions** = block upgrades during critical periods
5. **Manual upgrades within windows** = exact timing control vs waiting for auto-upgrade

The combination of these tools gives you the visibility and control needed for reliable stakeholder communication about GKE upgrade timing.