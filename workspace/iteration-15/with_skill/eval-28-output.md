# GKE Upgrade Timing Predictability & Control

Your VP needs reliable upgrade schedules for stakeholder communication. Here's how to achieve predictable timing and visibility with GKE's available tools.

## Current Upgrade Status Check

First, check what upgrades are planned for your clusters:

```bash
# Check auto-upgrade targets for each cluster
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# See what versions are available/targeted in your channel
gcloud container get-server-config --region REGION --format="yaml(channels)"

# List all clusters with their current versions and channels
gcloud container clusters list --format="table(name,location,releaseChannel.channel,currentMasterVersion,nodePools[].version.list():label=NODE_VERSIONS)"
```

The `get-upgrade-info` command shows:
- `autoUpgradeStatus`: Whether auto-upgrades are enabled
- `minorTargetVersion`/`patchTargetVersion`: What version GKE will upgrade to
- `endOfStandardSupportTimestamp`: When the current version reaches EoS (forced upgrade)

## Upgrade Timing Predictability Tools

### 1. GKE Release Schedule (Planning Horizon: 1+ month)

The [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) shows:
- **Earliest possible dates** for new versions in each channel
- Historical progression patterns between channels
- End of Support dates for all versions

**Key insight:** These are "no earlier than" dates. Upgrades won't happen before these dates but may happen days or weeks later due to progressive rollout.

### 2. Scheduled Upgrade Notifications (Preview - March 2026)

GKE will offer **72-hour advance notifications** for control plane auto-upgrades via Cloud Logging:

```bash
# Set up log-based alerting for upgrade notifications
gcloud logging sinks create gke-upgrade-notifications \
  pubsub.googleapis.com/projects/PROJECT_ID/topics/TOPIC_NAME \
  --log-filter='resource.type="gke_cluster" protoPayload.methodName="google.container.v1.ClusterManager.UpgradeCluster"'
```

**Timeline:** Control plane notifications available March 2026, node pool notifications follow later.

### 3. Maintenance Windows (Timing Control)

Configure recurring maintenance windows to constrain when auto-upgrades can happen:

```bash
# Set weekend maintenance window (Saturday 2-6 AM UTC)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-end "2024-01-06T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Important:** Maintenance windows control WHEN upgrades can happen, but not WHETHER they happen. If a new version becomes available, GKE will upgrade during the next maintenance window.

### 4. Maintenance Exclusions (Upgrade Blocking)

Use exclusions to temporarily block upgrades during critical periods:

```bash
# Block ALL upgrades during code freeze (max 30 days)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "code-freeze-jan" \
  --add-maintenance-exclusion-start-time "2024-01-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-02-15T00:00:00Z" \
  --add-maintenance-exclusion-scope no_upgrades

# Block minor upgrades but allow security patches (up to EoS)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "minor-freeze" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Exclusion types:**
- **"no_upgrades"**: Blocks everything (30-day max) - use for critical periods
- **"no_minor_or_node_upgrades"**: Allows security patches, blocks disruptive changes
- **"no_minor_upgrades"**: Allows patches and node upgrades, blocks minor versions

## Maximum Predictability Strategy

For the highest predictability (recommended for your VP's needs):

### Option A: Controlled Auto-Upgrades
```bash
# 1. Use Regular or Stable channel (not Rapid)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel stable

# 2. Set "no minor or node upgrades" exclusion
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# 3. Configure maintenance window for patches
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-end "2024-01-06T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Result:** 
- Security patches happen automatically during weekend windows
- Minor upgrades only happen when YOU initiate them
- No surprise disruptions to workloads

### Option B: Manual Minor Upgrades with Scheduled Timing
```bash
# Plan quarterly minor upgrade schedule
# Q1: January 15 (planned maintenance window)
# Q2: April 15
# Q3: July 15  
# Q4: October 15

# Execute at planned time:
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --cluster-version TARGET_VERSION
```

## Multi-Cluster Fleet Coordination

If you have multiple clusters across environments, use **rollout sequencing** to control the order:

```bash
# Set up dev → staging → prod sequence
gcloud container fleet clusterupgrade update \
  --project PROJECT_ID \
  --upstream-fleet projects/PROJECT_ID/locations/global/fleets/dev-fleet \
  --default-upgrade-soaking 7d
```

**Alternative (simpler):** Use different channels per environment:
- Dev: Regular channel (gets updates first)
- Staging: Regular channel + 1-week maintenance exclusion delay
- Prod: Stable channel (gets updates last)

## Stakeholder Communication Template

Here's a template for your VP to communicate upgrade schedules:

```
GKE Cluster Upgrade Schedule - Q1 2024

Current Status:
- All clusters on Stable release channel
- Security patches: Automated weekly (Saturdays 2-6 AM UTC)
- Minor upgrades: Controlled quarterly releases

Planned Minor Upgrades:
- Q1 (Jan 15): Kubernetes 1.29 → 1.30
- Q2 (Apr 15): Kubernetes 1.30 → 1.31
- Q3 (Jul 15): Kubernetes 1.31 → 1.32

Emergency Patches:
- Applied automatically within 72 hours during maintenance windows
- Critical security patches may override schedule with 24h notice

Rollout Sequence:
1. Dev clusters: Target date
2. Staging clusters: Target date + 3 days
3. Production clusters: Target date + 7 days

Monitoring:
- 72-hour advance notifications enabled
- Upgrade status dashboard: [LINK]
- Emergency contact: Platform team
```

## Monitoring & Alerting Setup

Set up proactive monitoring for upgrade events:

```bash
# Cloud Logging query for upgrade events
resource.type="gke_cluster"
protoPayload.methodName=~"google.container.v1.ClusterManager.(UpgradeCluster|UpdateCluster)"
severity>=INFO

# Set up Pub/Sub notifications
gcloud logging sinks create gke-upgrades \
  pubsub.googleapis.com/projects/PROJECT_ID/topics/gke-upgrades \
  --log-filter='resource.type="gke_cluster" protoPayload.methodName=~"UpgradeCluster"'
```

## Key Constraints to Communicate

**What you CAN control:**
- WHEN upgrades happen (maintenance windows)
- WHETHER minor upgrades happen (exclusions)
- SEQUENCE across environments (rollout sequencing)

**What you CANNOT control:**
- Exact timing of new version availability (progressive rollout)
- Emergency security patches (may override schedule)
- End-of-Support enforcement (forced upgrades)

**Recommendation:** Use the controlled auto-upgrade strategy (Option A) for maximum predictability while maintaining security. This gives you defined maintenance windows for patches and full control over when minor upgrades happen.