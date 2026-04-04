# GKE Upgrade Predictability & Visibility

Your VP needs **predictable upgrade timing** for stakeholder communication. GKE provides several tools for visibility and control, but the level of predictability depends on your current configuration.

## Current Upgrade Visibility Tools

### 1. Scheduled Upgrade Notifications (Preview, March 2026)
**72-hour advance notice for control plane upgrades:**
```bash
# Enable scheduled notifications
gcloud container clusters update CLUSTER_NAME \
  --enable-scheduled-upgrades \
  --region REGION
```
- Notifications appear in Cloud Logging 72 hours before auto-upgrade
- Control plane only (node pool notifications coming in later release)
- Best tool for short-term predictability

### 2. GKE Release Schedule (Long-term Planning)
Check the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule):
- Shows **earliest possible dates** when versions become available/auto-upgrade targets
- Channel-specific timelines (Rapid → Regular → Stable progression)
- End of Support dates for planning forced upgrades
- **Important:** These are "no sooner than" dates — actual upgrades may happen later

### 3. Upgrade Info API (Current Status)
```bash
# Check what your cluster will upgrade to next
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```
Shows:
- Current auto-upgrade target version
- End of Support timestamps
- Rollback-safe upgrade status
- Whether cluster is "ahead of channel"

## Controlling Upgrade Timing

### Option 1: Maximum Predictability (Recommended)
**Use maintenance windows + manual upgrades for ultimate control:**

```bash
# Set maintenance window for "approved" time slots
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-window-start "2025-01-04T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Block minor version auto-upgrades (allows security patches)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Workflow for stakeholder communication:**
1. Monitor release schedule for new minor versions
2. When new minor reaches your channel's auto-upgrade target, you get 72h notification
3. **YOU decide when to upgrade** during approved maintenance windows
4. Communicate exact timing to stakeholders in advance

### Option 2: Controlled Auto-Upgrades
**Let GKE upgrade automatically within your constraints:**

```bash
# Tight maintenance window (Saturday 2-6 AM only)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-window-start "2025-01-04T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Optional: Slow down upgrade frequency
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-minor-version-disruption-interval=7776000s  # 90 days max
```

**Trade-off:** Less control, but upgrades happen automatically within your approved windows.

## Multi-Cluster Fleet Predictability

If you have multiple clusters, **rollout sequencing** provides ordered upgrades:

```bash
# Configure fleet-based rollout sequencing
gcloud container fleet clusterupgrade update \
  --project=PROJECT_ID \
  --upstream-fleet=DEV_FLEET_PROJECT \
  --default-upgrade-soaking=7d
```

**Stakeholder communication advantage:** "Dev clusters upgrade first, then after 7-day soak period, production follows."

## Release Channel Strategy for Predictability

Your channel choice affects upgrade timing:

| Channel | Predictability | Timeline | Best for |
|---------|---------------|----------|----------|
| **Stable** | Highest | Latest, slowest cadence | Risk-averse environments |
| **Regular** | Moderate | Balanced validation + speed | Most production workloads |  
| **Extended** | Maximum control | Manual minor upgrades only | Compliance/regulated environments |

**For maximum stakeholder predictability:** Use **Extended channel** + maintenance exclusions + manual upgrades:
- You control exactly when minor upgrades happen
- Only security patches auto-apply (during maintenance windows)
- Up to 24 months of support per version

## Monitoring and Alerting Setup

Set up proactive monitoring for upgrade events:

```bash
# Cloud Logging query for upgrade notifications
resource.type="gke_cluster" 
protoPayload.metadata.operationType=~"(UPDATE_CLUSTER|UPGRADE_MASTER)"

# Pub/Sub subscription for real-time alerts
gcloud pubsub subscriptions create gke-upgrade-alerts \
  --topic=gke-cluster-notifications
```

## Recommended Configuration for Your VP

**For maximum predictability and stakeholder communication:**

```bash
# 1. Enable 72-hour notifications
gcloud container clusters update CLUSTER_NAME \
  --enable-scheduled-upgrades \
  --region REGION

# 2. Set predictable maintenance windows
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-window-start "2025-01-04T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# 3. Block auto minor upgrades, allow manual control
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# 4. Optional: Move to Extended channel for maximum control
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel extended
```

**Communication workflow:**
1. **Monthly:** Review GKE release schedule for upcoming versions
2. **72 hours before:** Receive scheduled upgrade notification
3. **Your timeline:** Manually trigger upgrades during approved windows
4. **Stakeholders:** Know exactly when upgrades will happen

This gives your VP the predictability needed for stakeholder communication while maintaining security through automatic patch updates.