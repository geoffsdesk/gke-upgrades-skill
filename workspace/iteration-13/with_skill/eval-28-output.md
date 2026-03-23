# GKE Upgrade Timing & Predictability Guide

Your VP needs visibility into when upgrades will happen and control over timing. Here's how to achieve both with GKE's tooling.

## Current Upgrade Status Check

First, get visibility into what's planned:

```bash
# Check each cluster's auto-upgrade status and targets
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# What this shows:
# - autoUpgradeStatus (enabled/disabled/paused)
# - Current and target versions (minor and patch)
# - End of Support timestamps
# - Whether upgrades are blocked by exclusions
```

This API tells you exactly what version each cluster will upgrade to and when support ends.

## Predicting Upgrade Timing

### Release Schedule Visibility
- **GKE Release Schedule**: [cloud.google.com/kubernetes-engine/docs/release-schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) shows "earliest possible" dates for new versions reaching each channel
- **Key insight**: Upgrades won't happen BEFORE these dates, but may happen days/weeks later due to progressive rollout
- **Progressive rollout**: New releases roll out across all regions over 4-5 business days

### Scheduled Upgrade Notifications (Preview - March 2026)
```bash
# Enable 72-hour advance notifications via Cloud Logging
gcloud container clusters update CLUSTER_NAME \
  --enable-scheduled-upgrade-notifications
```
These notifications give you 72 hours advance notice before control plane auto-upgrades begin.

### Factors Affecting Timing
1. **Progressive regional rollout** (4-5 days)
2. **Your maintenance windows** (upgrades only happen during windows)
3. **Maintenance exclusions** (can block upgrades entirely)
4. **Disruption intervals** (minimum time between upgrades on same cluster)
5. **Internal freezes** (e.g., BFCM, holiday periods)
6. **Technical pauses** (if GKE detects issues with a release)

## Taking Control of Timing

### Option 1: Maintenance Windows (Predictable Windows)
Set recurring windows when auto-upgrades are allowed:

```bash
gcloud container clusters update CLUSTER_NAME \
    --maintenance-window-start "2024-12-14T02:00:00Z" \
    --maintenance-window-duration "PT4H" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**For your VP**: "Upgrades will only happen during Saturday 2-6 AM UTC windows. This gives us predictable timing without blocking security patches."

### Option 2: User-Triggered Upgrades (Ultimate Control)
Instead of waiting for auto-upgrades, trigger them yourself during planned maintenance:

```bash
# Upgrade control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --master \
  --cluster-version TARGET_VERSION

# Upgrade node pools
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --cluster-version TARGET_VERSION
```

**For your VP**: "We manually trigger upgrades during our planned maintenance windows. No surprises."

### Option 3: Maintenance Exclusions (Block When Needed)
Block upgrades during critical periods:

```bash
# Block ALL upgrades during code freeze (max 30 days)
gcloud container clusters update CLUSTER_NAME \
  --add-maintenance-exclusion-name "holiday-freeze" \
  --add-maintenance-exclusion-start-time "2024-12-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-01-02T00:00:00Z" \
  --add-maintenance-exclusion-scope no_upgrades

# Block minor upgrades but allow security patches (until version EoS)
gcloud container clusters update CLUSTER_NAME \
  --add-maintenance-exclusion-name "no-minor-upgrades" \
  --add-maintenance-exclusion-start-time "2024-12-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Recommended Strategy for Executive Communication

### For Maximum Predictability:
1. **Use Regular or Stable release channels** (not Rapid - no SLA for stability)
2. **Set maintenance windows** aligned with your change management windows
3. **Enable scheduled upgrade notifications** (72h advance notice)
4. **Use "no minor or node upgrades" exclusions** to prevent disruptive changes while allowing security patches
5. **Manually trigger upgrades** during planned maintenance instead of waiting for auto-upgrades

### Multi-Environment Sequencing
If you have dev/staging/prod environments:

```bash
# Option A: Different channels for natural sequencing
# Dev: Regular channel
# Staging: Regular channel (same as dev, for testing)
# Prod: Stable channel (gets versions ~1-2 weeks after Regular)

# Option B: Same channel + rollout sequencing (advanced)
gcloud container fleet clusterupgrade update \
    --default-upgrade-soaking=7d \
    --project=PROJECT_ID
```

**For your VP**: "Dev gets new versions first, we test for 1 week, then prod gets the same version. No version drift between environments."

## Executive Summary Template

Here's what to tell your VP:

> **GKE Upgrade Predictability Plan**
> 
> **Current Status**: [Use get-upgrade-info to fill in cluster versions and targets]
> 
> **Timing Control Strategy**:
> - Maintenance windows: Saturdays 2-6 AM UTC
> - 72-hour advance notifications enabled
> - Code freeze exclusions: Dec 15 - Jan 2
> 
> **Environment Sequencing**:
> - Dev (Regular channel): Gets new versions first
> - Prod (Stable channel): Gets same versions ~1 week later
> - Manual trigger during planned maintenance windows
> 
> **Next Planned Upgrades**:
> - Control plane: Next Saturday maintenance window (if new version available)
> - Nodes: Following Saturday (after control plane validation)
> 
> **Communication**: 72-hour advance notifications + weekly status in change management meetings

## Monitoring & Alerting

Set up alerts for upgrade events:

```bash
# Cloud Logging filter for upgrade notifications
resource.type="gke_cluster"
protoPayload.methodName="google.container.v1.ClusterManager.UpdateCluster"
protoPayload.request.update.desiredMasterVersion!=""
```

This gives you real-time visibility when upgrades begin, not just when they're scheduled.

## Key Takeaway

**GKE's value is automated lifecycle management** - don't fight it, control it. Use maintenance windows + exclusions + manual triggers to get predictability while keeping the automated security patching benefits. Your VP gets predictable timing without the operational overhead of managing Kubernetes versions manually.