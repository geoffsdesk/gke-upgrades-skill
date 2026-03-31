# GKE Upgrade Timing Control & Visibility

Your VP needs predictable upgrade timing for stakeholder communication. GKE provides several mechanisms to control WHEN upgrades happen and visibility tools to predict upcoming upgrades.

## Primary Control Mechanisms

### 1. Maintenance Windows (Time Control)
**What it does:** Restricts auto-upgrades to specific time windows
**Best for:** Controlling WHEN upgrades happen without blocking them entirely

```bash
# Set recurring weekend maintenance window
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --maintenance-window-start "2024-01-06T02:00:00Z" \
    --maintenance-window-duration 6h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Key insight:** Auto-upgrades respect maintenance windows, but manual upgrades bypass them entirely.

### 2. Release Channel Selection (Cadence Control)
**What it does:** Controls how quickly new versions reach your cluster

| Channel | Upgrade Cadence | Best For |
|---------|----------------|----------|
| **Stable** | Slowest (most validation) | Mission-critical, predictable timing |
| **Regular** | Balanced (default) | Most production workloads |
| **Rapid** | Fastest (new features early) | Dev/test environments |
| **Extended** | Manual minor upgrades only | Maximum control (24mo support) |

**For maximum predictability:** Use **Stable** channel + maintenance windows. You get the slowest upgrade cadence with time-bounded execution.

### 3. Maintenance Exclusions (Scope Control)
**What it does:** Blocks specific types of upgrades during defined periods

```bash
# Block ALL upgrades for 30 days (code freeze, BFCM)
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "q4-freeze" \
    --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-12-15T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades

# Block minor versions only (allow security patches)
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "minor-freeze" \
    --add-maintenance-exclusion-start-time START_TIME \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

## Visibility & Prediction Tools

### 1. Scheduled Upgrade Notifications (Preview - March 2026)
**72-hour advance notice** via Cloud Logging before control plane auto-upgrades.

```bash
# Enable scheduled notifications
gcloud container clusters update CLUSTER_NAME \
    --enable-scheduled-upgrades
```

### 2. GKE Release Schedule (Long-range Planning)
The [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) shows estimated dates for:
- When versions become available in each channel
- Earliest auto-upgrade dates (~2 weeks advance visibility)
- End of Support dates

**Use this for quarterly planning** — you can see roughly when new minor versions will hit your channel.

### 3. Upgrade Info API (Current Status)
Check your cluster's current auto-upgrade target and timeline:

```bash
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

Example output shows:
- `autoUpgradeStatus`: Whether auto-upgrades are active
- `minorTargetVersion` / `patchTargetVersion`: What version you'll upgrade to
- `endOfStandardSupportTimestamp`: When current version reaches EoS

### 4. Cluster Notifications via Pub/Sub
Set up proactive alerting for upgrade events:

```bash
# Subscribe to cluster notifications
gcloud pubsub topics create gke-upgrades
gcloud container clusters update CLUSTER_NAME \
    --notification-config=pubsub-topic=projects/PROJECT_ID/topics/gke-upgrades
```

**Notification types you'll receive:**
- Upgrade available event
- Upgrade event (start)
- Minor version at/near end of support

## Multi-Cluster Coordination

### Rollout Sequencing (Advanced)
For multiple clusters, control upgrade order with soak time between environments:

```bash
# Configure dev → prod sequence with 7-day soak
gcloud container fleet clusterupgrade update \
    --project=PROJECT_ID \
    --upstream-fleet=dev-fleet-project \
    --default-upgrade-soaking=7d
```

**Critical constraint:** All clusters must be on the same release channel for rollout sequencing to work.

## Recommended Configuration for Maximum Predictability

```bash
# 1. Use Stable channel for slowest cadence
gcloud container clusters update CLUSTER_NAME \
    --release-channel stable

# 2. Set weekend maintenance window
gcloud container clusters update CLUSTER_NAME \
    --maintenance-window-start "2024-01-06T02:00:00Z" \
    --maintenance-window-duration 6h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# 3. Enable 72h notifications (when available)
gcloud container clusters update CLUSTER_NAME \
    --enable-scheduled-upgrades

# 4. Set up monitoring
gcloud pubsub topics create gke-upgrades
gcloud container clusters update CLUSTER_NAME \
    --notification-config=pubsub-topic=projects/PROJECT_ID/topics/gke-upgrades
```

## For Your VP: Executive Summary

**Short-term visibility (1-2 weeks):**
- Scheduled upgrade notifications provide 72-hour advance notice
- Maintenance windows ensure upgrades only happen during approved time slots

**Medium-term planning (1-3 months):**
- GKE release schedule shows when new versions will reach your channel
- Upgrade info API shows your current auto-upgrade target

**Long-term control (quarterly):**
- Release channel selection controls overall upgrade velocity
- Maintenance exclusions can block upgrades during critical business periods
- Extended channel provides up to 24 months of support with manual control

**Bottom line:** You can achieve very predictable upgrade timing by combining Stable channel + weekend maintenance windows + 72h notifications. For ultimate control during critical periods, add temporary maintenance exclusions.

## Important Caveats

1. **Progressive rollout:** New versions roll out across regions over 4-5 days. Your specific region may be early or late in the rollout.

2. **Best-case dates:** The release schedule shows earliest possible dates — upgrades won't happen before then but may happen later due to various factors.

3. **EoS enforcement:** When a version reaches End of Support, clusters are force-upgraded regardless of maintenance controls (except temporary "no upgrades" exclusions).

**Recommendation:** Start with Stable channel + maintenance windows. This gives you predictable weekend upgrade timing with the slowest upgrade cadence available while maintaining full automation and security patching.