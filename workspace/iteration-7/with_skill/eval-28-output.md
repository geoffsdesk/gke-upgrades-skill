# GKE Upgrade Timing & Visibility Guide

Your VP needs predictable upgrade schedules for stakeholder communication. Here's how to get visibility and control over when GKE upgrades will happen.

## Current Upgrade Status Check

First, check what upgrades are planned for your clusters:

```bash
# Check auto-upgrade target and timeline for each cluster
for cluster in $(gcloud container clusters list --format="value(name)"); do
  echo "=== $cluster ==="
  gcloud container clusters describe $cluster --zone=ZONE \
    --format="table(name,currentMasterVersion,releaseChannel.channel)" \
    --flatten="nodePools[]" \
    --format="table(name,currentMasterVersion,releaseChannel.channel,nodePools.version,nodePools.management.autoUpgrade)"
done

# Check maintenance windows and exclusions
gcloud container clusters describe CLUSTER_NAME --zone=ZONE \
  --format="yaml(maintenancePolicy)"
```

## GKE's Upgrade Predictability Tools

### 1. Release Schedule (Best-case timeline)
- **Official schedule**: https://cloud.google.com/kubernetes-engine/docs/release-schedule
- Shows when new versions become **available** in each channel
- **Key caveat**: These are "no sooner than" dates — upgrades won't happen before these dates but may happen later due to:
  - Progressive rollout across regions (4-5 business days)
  - Maintenance windows/exclusions
  - Internal freezes (e.g., Black Friday/Cyber Monday)
  - Technical pauses

### 2. Auto-upgrade Status (Current target)
```bash
# See what version your cluster will upgrade to next
gcloud container clusters describe CLUSTER_NAME --zone=ZONE \
  --format="value(autopilot.enabled,releaseChannel.channel,currentMasterVersion)"
```

### 3. Scheduled Upgrade Notifications (72-hour warning)
```bash
# Enable 72-hour advance notifications via Cloud Logging
gcloud container clusters update CLUSTER_NAME --zone=ZONE \
  --notification-config=pubsub=projects/PROJECT_ID/topics/TOPIC_NAME
```

## Timeline Prediction by Channel

| Channel | Upgrade cadence | Predictability | VP communication strategy |
|---------|----------------|----------------|--------------------------|
| **Rapid** | Weekly patches, minors ~2 weeks after upstream | Low — frequent, bleeding edge | "Expect weekly maintenance windows" |
| **Regular** | Bi-weekly patches, minors ~6-8 weeks after upstream | Medium | "Major upgrades quarterly, patches monthly" |
| **Stable** | Monthly patches, minors ~3-4 months after upstream | High | "Major upgrades semi-annually, patches monthly" |
| **Extended** | Same as Regular for patches, manual minor upgrades | Highest | "Only patches auto-applied, full control over major changes" |

## Controlling Upgrade Timing

### Option 1: Maintenance Windows (Recurring control)
```bash
# Set predictable maintenance windows (e.g., Saturday 2-6 AM)
gcloud container clusters update CLUSTER_NAME --zone=ZONE \
  --maintenance-window-start "2024-12-07T02:00:00Z" \
  --maintenance-window-end "2024-12-07T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**VP communication**: "All GKE maintenance occurs during our Saturday 2-6 AM window."

### Option 2: Maintenance Exclusions (Temporary blocks)
```bash
# Block all upgrades for 30 days (code freeze, critical period)
gcloud container clusters update CLUSTER_NAME --zone=ZONE \
  --add-maintenance-exclusion-name "Q4-freeze" \
  --add-maintenance-exclusion-start-time "2024-12-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# Block minor upgrades while allowing security patches (until version EoS)
gcloud container clusters update CLUSTER_NAME --zone=ZONE \
  --add-maintenance-exclusion-name "minor-freeze" \
  --add-maintenance-exclusion-start-time "2024-12-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-06-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**VP communication**: "We've blocked all platform upgrades through Q4 earnings season."

### Option 3: Channel Strategy (Long-term predictability)

**For maximum predictability:**
```bash
# Move production clusters to Stable channel
gcloud container clusters update PROD-CLUSTER --zone=ZONE \
  --release-channel stable

# Use Extended channel for compliance-sensitive workloads
gcloud container clusters update COMPLIANCE-CLUSTER --zone=ZONE \
  --release-channel extended
```

**Multi-environment progression:**
- Dev → Rapid channel
- Staging → Regular channel  
- Production → Stable channel
- Compliance → Extended channel

**VP communication**: "Production follows the Stable channel — major Kubernetes upgrades happen semi-annually with 3-4 months advance notice."

## Executive Dashboard Setup

Create a monitoring dashboard showing upgrade status across your fleet:

```bash
# Script to generate cluster upgrade status report
#!/bin/bash
echo "Cluster,Current Version,Channel,Next Upgrade Window,Status"
for cluster in $(gcloud container clusters list --format="value(name,zone)"); do
  cluster_name=$(echo $cluster | cut -d' ' -f1)
  zone=$(echo $cluster | cut -d' ' -f2)
  
  version=$(gcloud container clusters describe $cluster_name --zone=$zone --format="value(currentMasterVersion)")
  channel=$(gcloud container clusters describe $cluster_name --zone=$zone --format="value(releaseChannel.channel)")
  
  echo "$cluster_name,$version,$channel,Next Saturday 2-6AM,Active"
done
```

## Stakeholder Communication Templates

### For immediate needs:
> "Our GKE clusters are configured for predictable maintenance windows every Saturday 2-6 AM. The next potential upgrade window is [DATE]. We receive 72-hour advance notification of any scheduled maintenance."

### For quarterly planning:
> "We're on the Stable release channel, which means major Kubernetes upgrades happen approximately every 6 months with security patches monthly. Based on the current release schedule, our next major platform upgrade is expected in Q[X] [YEAR]."

### For risk-averse periods:
> "We've implemented maintenance exclusions blocking all platform upgrades from [START DATE] through [END DATE] to ensure stability during [CRITICAL PERIOD]. Only emergency security patches will be applied if needed."

## Advanced: Multi-cluster Coordination

For large fleets, use rollout sequencing:

```bash
# Define upgrade order with soak time
gcloud container fleet scopes create upgrade-sequence

# Add clusters in order: dev → staging → prod
gcloud container fleet memberships register dev-cluster \
  --location=LOCATION \
  --gke-cluster=ZONE/DEV_CLUSTER

# Configure rollout with 48h soak between environments
# (This requires Fleet API setup — contact support for configuration)
```

## Key Points for Your VP

1. **72-hour minimum notice**: GKE provides advance notifications of scheduled upgrades
2. **Maintenance windows**: Guarantee upgrades only happen during approved times
3. **Maintenance exclusions**: Can block upgrades for up to 30 days during critical periods
4. **Channel strategy**: Stable channel provides the most predictable timeline
5. **Progressive rollout**: New versions take 4-5 business days to reach all regions
6. **Emergency override**: Critical security patches may bypass normal scheduling

**Recommended approach**: Configure maintenance windows + Stable channel for production, with staging environments on Regular channel to provide 6-8 weeks advance validation of upcoming changes.