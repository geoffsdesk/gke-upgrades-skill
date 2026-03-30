# GKE Upgrade Predictability & Visibility Guide

Your VP needs reliable upgrade timing for stakeholder communication. Here's how to achieve predictable upgrades and get visibility into GKE's upgrade schedule.

## Primary Control Mechanisms

### 1. Release Channel Selection (Primary Cadence Control)

The release channel is your **primary lever for upgrade velocity**:

| Channel | Upgrade Cadence | Use Case | Predictability |
|---------|----------------|----------|----------------|
| **Stable** | Slowest (most validation) | Mission-critical production | Highest - versions are well-tested |
| **Regular** | Balanced (default) | Most production workloads | Good - standard validation period |
| **Extended** | Manual minor upgrades | Compliance/regulated environments | Highest - you control minor timing |
| **Rapid** | Fastest (minimal validation) | Dev/test environments | Lower - early access, potential issues |

**Recommendation for predictability:** Use **Stable** for production clusters requiring maximum predictability.

### 2. Maintenance Windows (Timing Control)

Configure recurring windows to control **when** upgrades happen:

```bash
# Set Saturday 2-6 AM maintenance window
gcloud container clusters update CLUSTER_NAME \
    --maintenance-window-start "2025-01-04T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Key insight:** Auto-upgrades respect maintenance windows. Manual upgrades bypass them entirely.

### 3. Maintenance Exclusions (Scope Control)

Block upgrades during critical periods:

```bash
# Block ALL upgrades during code freeze (max 30 days)
gcloud container clusters update CLUSTER_NAME \
    --add-maintenance-exclusion-name "holiday-freeze" \
    --add-maintenance-exclusion-start "2025-12-15T00:00:00Z" \
    --add-maintenance-exclusion-end "2026-01-02T00:00:00Z" \
    --add-maintenance-exclusion-scope no_upgrades

# Block minor upgrades but allow security patches (up to EoS)
gcloud container clusters update CLUSTER_NAME \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

## Upgrade Visibility Tools

### 1. Scheduled Upgrade Notifications (Preview - March 2026)

**72-hour advance notice** via Cloud Logging:

```bash
# Enable scheduled notifications
gcloud container clusters update CLUSTER_NAME \
    --enable-scheduled-upgrades

# Query scheduled upgrade notifications
gcloud logging read 'resource.type="gke_cluster" 
    jsonPayload.eventType="SCHEDULED_UPGRADE_NOTIFICATION"' \
    --project=PROJECT_ID --limit=10
```

**What you get:** Control plane upgrade notifications 72 hours before auto-upgrade. Node pool notifications coming in later releases.

### 2. GKE Release Schedule (Longer-Range Planning)

The [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) shows **best-case estimates** for:
- When new versions become available per channel
- Earliest possible auto-upgrade dates (~2 weeks advance notice)
- End of Support timelines

**Important:** These are estimates - actual upgrades may happen later but not earlier.

### 3. Current Auto-Upgrade Status

Check what upgrade is planned next:

```bash
# See current auto-upgrade target and timing
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Check current versions
gcloud container clusters describe CLUSTER_NAME \
    --format="table(name,currentMasterVersion,nodePools[].version)"
```

### 4. Cluster Notifications via Pub/Sub

Set up proactive alerting:

```bash
# Create Pub/Sub topic for cluster events
gcloud pubsub topics create gke-cluster-upgrades

# Subscribe clusters to notification topic
gcloud container clusters update CLUSTER_NAME \
    --notification-config=pubsub=projects/PROJECT_ID/topics/gke-cluster-upgrades
```

**Notification types you'll receive:**
- Upgrade available events
- Upgrade start/completion events  
- Minor version approaching EoS warnings
- Disruption events during upgrades

## Recommended Configuration for Maximum Predictability

For stakeholder-friendly upgrade timing, combine these settings:

```bash
# 1. Use Stable channel (slowest, most predictable)
gcloud container clusters update CLUSTER_NAME \
    --release-channel stable

# 2. Set predictable maintenance window (Saturday nights)
gcloud container clusters update CLUSTER_NAME \
    --maintenance-window-start "2025-01-04T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# 3. Enable 72h notifications (when available)
gcloud container clusters update CLUSTER_NAME \
    --enable-scheduled-upgrades

# 4. Optional: Block minor upgrades for maximum control
gcloud container clusters update CLUSTER_NAME \
    --add-maintenance-exclusion-scope no_minor_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

**Result:** Security patches arrive during Saturday 2-6 AM windows with 72-hour advance notice. Minor upgrades only happen when you manually trigger them.

## Multi-Cluster Rollout Sequencing (Advanced)

For fleets with dev/staging/prod progression:

```bash
# Configure rollout order: dev → staging → prod
gcloud container fleet clusterupgrade update \
    --upstream-fleet=DEV_PROJECT_ID \
    --default-upgrade-soaking=168h  # 7-day soak between stages
```

**Constraint:** All clusters must be on the **same release channel** for rollout sequencing to work.

## Alternative: Manual Upgrade Control

If you need **absolute control** over upgrade timing:

1. **Extended Channel** - Minor upgrades are manual-only
2. **"No minor or node" exclusions** - Security patches only
3. **Trigger upgrades manually** during planned windows

```bash
# When ready to upgrade (you control timing completely)
gcloud container clusters upgrade CLUSTER_NAME \
    --cluster-version TARGET_VERSION \
    --master  # Control plane first

# Then node pools
gcloud container node-pools upgrade NODE_POOL_NAME \
    --cluster CLUSTER_NAME \
    --cluster-version TARGET_VERSION
```

## Stakeholder Communication Template

**For your VP's stakeholder updates:**

```
GKE Cluster Upgrade Schedule - [Month Year]

TIMING CONTROLS IN PLACE:
✓ Stable release channel (most predictable upgrade cadence)  
✓ Saturday 2-6 AM maintenance windows
✓ 72-hour advance notifications enabled
✓ Holiday/critical period exclusions configured

NEXT SCHEDULED UPGRADES:
- Control Plane: [Date] during maintenance window
- Node Pools: [Date] during maintenance window  
- Estimated Duration: [X] hours per cluster

NOTIFICATION TIMELINE:
- T-72h: Automatic notification via Cloud Logging
- T-24h: Platform team verification & go/no-go
- T-0h: Upgrade execution during maintenance window

ESCAPE HATCH:
30-day "no upgrades" exclusion available for critical business periods
```

## Key Takeaways

1. **Release channel selection is your primary predictability control**
2. **Maintenance windows control timing; exclusions control scope**
3. **72-hour notifications provide tactical visibility (Preview March 2026)**
4. **GKE release schedule provides strategic visibility (~2 weeks)**
5. **For absolute control: Extended channel + exclusions + manual triggers**

The combination of Stable channel + maintenance windows + scheduled notifications gives you the most predictable auto-upgrade experience while maintaining security patch currency.