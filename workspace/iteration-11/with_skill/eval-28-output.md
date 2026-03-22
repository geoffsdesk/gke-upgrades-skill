# GKE Upgrade Timing & Visibility Guide

Your VP needs predictable upgrade timing for stakeholder communication. GKE provides several tools for upgrade visibility and control - here's how to get the predictability you need.

## Quick Answer: Key Tools for Predictability

1. **Maintenance windows** - Control WHEN auto-upgrades can happen
2. **Cluster auto-upgrade status API** - Shows target versions and timing
3. **GKE release schedule** - Official timeline for version availability
4. **Scheduled upgrade notifications** - 72-hour advance notice (preview)
5. **Maintenance exclusions** - Block upgrades during critical periods

## Understanding GKE Upgrade Timing

### What affects when upgrades happen:

| Factor | Impact | Your control |
|--------|--------|--------------|
| **Release channel** | Rapid gets upgrades first, Stable last | High - choose channel |
| **Maintenance windows** | Auto-upgrades only during allowed times | High - set your schedule |
| **Progressive rollout** | New releases roll out across regions over 4-5 days | None |
| **Disruption intervals** | GKE enforces gaps between upgrades (7-90 days configurable) | Medium - configure intervals |
| **Maintenance exclusions** | Block upgrades during critical periods | High - apply exclusions |

### Upgrade velocity by channel:
- **Rapid**: New K8s minors within ~2 weeks of upstream
- **Regular**: After Rapid validation (~1 month after upstream)
- **Stable**: After Regular validation (~2 months after upstream)
- **Extended**: Same as Regular, but stays supported longer

## Tools for Upgrade Visibility

### 1. Cluster Auto-Upgrade Status (Primary Tool)

```bash
# Check current upgrade status and targets
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

This shows:
- Current auto-upgrade target version
- End of Support timestamps
- Whether upgrades are blocked by exclusions
- Maintenance windows configuration

**Example output interpretation:**
```yaml
autoUpgradeStatus: 
  enabled: true
  nextUpgradeTime: "2024-03-15T02:00:00Z"  # When next upgrade will happen
endOfStandardSupportTimestamp: "2024-06-01T00:00:00Z"
minorTargetVersion: "1.29"
patchTargetVersion: "1.29.5-gke.1234000"
```

### 2. GKE Release Schedule (Official Timeline)

Visit [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) for:
- Version availability dates by channel
- "Best case" upgrade timing (won't happen before these dates)
- End of Support dates

**Key insight:** New minor versions take ~1 month to reach Regular channel, giving you advance planning time.

### 3. Scheduled Upgrade Notifications (Preview - March 2026)

```bash
# Opt into 72-hour advance notifications
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --enable-scheduled-upgrade-notifications
```

Notifications sent via Cloud Logging 72 hours before control plane auto-upgrades.

### 4. Version Availability Check

```bash
# See what versions are available now
gcloud container get-server-config --region REGION \
  --format="yaml(channels)"
```

## Controlling Upgrade Timing

### 1. Maintenance Windows (Recommended)

Set recurring windows aligned with your change management:

```bash
# Weekend maintenance window
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-end "2024-01-06T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**For ultimate predictability:** Manually trigger upgrades during your maintenance window instead of waiting for auto-upgrade. This guarantees the timing.

### 2. Maintenance Exclusions (Block Critical Periods)

Three types available:

```bash
# Block ALL upgrades during code freeze (30-day max)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "holiday-freeze" \
  --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-02T00:00:00Z" \
  --add-maintenance-exclusion-scope no_upgrades

# Block minor upgrades but allow patches (up to version EoS)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "minor-hold" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_upgrades
```

### 3. Disruption Intervals (Control Upgrade Frequency)

```bash
# Minimum 30 days between minor upgrades
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-minor-version-disruption-interval 30d

# Minimum 14 days between patch upgrades
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-patch-version-disruption-interval 14d
```

## VP Communication Framework

### Monthly Upgrade Planning Report

Create a monthly report with:

1. **Current status** (from `get-upgrade-info`)
2. **Upcoming versions** (from release schedule)
3. **Scheduled maintenance windows**
4. **Active exclusions** and expiry dates
5. **Risk timeline** (End of Support dates)

### Sample Status Report Format:

```
GKE Upgrade Status - March 2024

Production Clusters:
- prod-west: 1.28.5 → 1.29.2 (target), next window: Sat 3/9 2-6AM
- prod-east: 1.28.5 → 1.29.2 (target), next window: Sat 3/9 2-6AM

Staging Clusters:
- staging: 1.29.1 → 1.29.2 (target), next window: Fri 3/8 10PM-2AM

Active Controls:
- Holiday exclusion expires 12/2/24
- Minor upgrades blocked until Q2 (business requirement)

Risk Items:
- Current versions supported until 6/1/24
- Must upgrade by 5/15 to avoid forced upgrade
```

## Advanced: Multi-Cluster Coordination

For large fleets, consider:

### Rollout Sequencing

```bash
# Define upgrade order with soak time
gcloud container clusters update prod-cluster-1 \
  --region REGION \
  --enable-rollout-sequencing \
  --rollout-sequence-rank 1 \
  --rollout-soak-time 3600s  # 1 hour between stages
```

**Important:** All clusters in a sequence must be on the same release channel.

### Environment Staggering

Use different channels for controlled progression:
- **Dev**: Rapid channel (gets updates first)
- **Staging**: Regular channel (1 month behind)
- **Production**: Stable channel (2 months behind)

## Recommendations for Your VP

### Immediate Actions:
1. **Configure maintenance windows** for all production clusters
2. **Set up monitoring** of `get-upgrade-info` output
3. **Apply exclusions** for known critical periods
4. **Choose appropriate release channels** (Regular for most prod workloads)

### Ongoing Process:
1. **Monthly upgrade planning** meetings reviewing status
2. **Quarterly channel strategy** review
3. **Annual maintenance calendar** planning with business stakeholders

### Communication Strategy:
- **4 weeks ahead**: Channel-based visibility from release schedule
- **2 weeks ahead**: Confirmed via maintenance windows + exclusions
- **72 hours ahead**: Final confirmation via scheduled notifications (when available)

The key insight: **GKE auto-upgrades are the default and recommended model**. Your control comes from configuring WHEN and IF upgrades happen through maintenance windows and exclusions, not from disabling auto-upgrades entirely.

Would you like me to help you set up maintenance windows for your specific clusters or create a monitoring script for the upgrade status API?