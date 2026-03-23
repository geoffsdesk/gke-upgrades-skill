# GKE Fleet Remediation Plan

You've inherited a common scenario — fragmented GKE clusters with inconsistent versions, channels, and upgrade policies. Here's a systematic approach to assess, standardize, and establish healthy lifecycle management.

## Phase 1: Fleet Assessment & Discovery

### 1. Inventory your fleet

```bash
# List all clusters with key metadata
gcloud container clusters list \
  --format="table(
    name,
    zone,
    currentMasterVersion,
    releaseChannel.channel,
    autopilot.enabled,
    nodePools[].version.list():label=NODE_VERSIONS
  )"

# Get upgrade readiness for each cluster
for cluster in $(gcloud container clusters list --format="value(name,zone)"); do
  name=$(echo $cluster | cut -d' ' -f1)
  zone=$(echo $cluster | cut -d' ' -f2)
  echo "=== $name ($zone) ==="
  gcloud container clusters get-upgrade-info $name --region $zone
done
```

### 2. Use GKE's self-service assessment tools

**GKE Deprecation Insights (most critical):**
```bash
# Check for deprecated API usage across fleet
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=- \
  --project=PROJECT_ID \
  --format="table(
    name.segment(-1):label=CLUSTER,
    insightSubtype,
    description
  )"
```

**Cloud Console Fleet View:**
- Navigate to GKE → Clusters → enable "Fleet" view
- Shows version distribution, channel enrollment, upgrade status
- Highlights clusters approaching End of Support
- Identifies version skew between control plane and nodes

**Security Command Center (if enabled):**
- Automatically flags clusters on unsupported versions
- Provides security posture scoring based on version currency

### 3. Assess maintenance policies

```bash
# Check maintenance windows and exclusions per cluster
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
  --format="yaml(
    maintenancePolicy,
    releaseChannel,
    currentMasterVersion,
    nodePools[].version
  )"
```

## Phase 2: Standardization Strategy

### Target Architecture (Recommended)

**Environment-based channel strategy:**
```
Development:   Regular channel + maintenance exclusions
Staging:       Regular channel + maintenance exclusions  
Production:    Regular/Stable channel + maintenance exclusions
```

**Why this approach:**
- **Don't use different channels per environment** — this makes rollout sequencing impossible and creates version drift
- **Use the same channel** with maintenance exclusions + user-triggered minor upgrades for controlled rollouts
- **Regular channel** is the sweet spot for most production workloads (full SLA, proven stability)
- **Stable channel** for ultra-conservative production environments
- **Extended channel** only for compliance-heavy workloads or customers who want maximum EoS flexibility

### Migration Priority Matrix

| Cluster State | Priority | Action |
|--------------|----------|---------|
| **"No channel" + EoS version** | 🔴 **CRITICAL** | Emergency upgrade + channel migration |
| **"No channel" + supported version** | 🟡 **HIGH** | Channel migration during next maintenance window |
| **Release channel + EoS version** | 🟡 **HIGH** | Remove exclusions, allow auto-upgrade |
| **Release channel + deprecated APIs** | 🟡 **HIGH** | Fix APIs, then allow upgrades |
| **Release channel + current version** | 🟢 **LOW** | Standardize maintenance policies only |

## Phase 3: Remediation Runbook

### Step 1: Emergency fixes (EoS clusters)

```bash
# Identify clusters approaching/past End of Support
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION \
  --format="value(endOfStandardSupportTimestamp,endOfExtendedSupportTimestamp)"

# For EoS clusters: remove all exclusions, allow immediate auto-upgrade
gcloud container clusters update CLUSTER_NAME --zone ZONE \
  --clear-maintenance-exclusions

# Or trigger manual upgrade if auto-upgrade timing is poor
gcloud container clusters upgrade CLUSTER_NAME --zone ZONE \
  --cluster-version TARGET_VERSION
```

### Step 2: Migrate "No channel" clusters

```bash
# Current assessment
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
  --format="value(releaseChannel.channel)"
# If empty → "No channel"

# Migrate to Regular channel (closest to legacy behavior)
gcloud container clusters update CLUSTER_NAME --zone ZONE \
  --release-channel regular

# Add maintenance exclusion for control (recommended)
gcloud container clusters update CLUSTER_NAME --zone ZONE \
  --add-maintenance-exclusion-name "standard-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Migration notes:**
- **Regular/Stable channels** are closest to legacy "No channel" behavior
- **Extended channel** if you want maximum flexibility around EoS enforcement
- **Apply exclusions AFTER migration** — exclusion types don't translate between "No channel" and release channels

### Step 3: Fix deprecated API usage

```bash
# Per-cluster API deprecation check
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# GKE deprecation insights (comprehensive)
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=LOCATION \
  --project=PROJECT_ID
```

**Common deprecated APIs to fix:**
- **PodSecurityPolicy** (removed in 1.25) → migrate to Pod Security Standards
- **Ingress extensions/v1beta1** (removed in 1.22) → networking.k8s.io/v1
- **CronJob batch/v1beta1** (removed in 1.25) → batch/v1

GKE automatically pauses auto-upgrades when deprecated API usage is detected, so this is blocking.

### Step 4: Standardize maintenance policies

```bash
# Standard maintenance window (Saturday 2-6 AM)
gcloud container clusters update CLUSTER_NAME --zone ZONE \
  --maintenance-window-start "2024-12-07T02:00:00Z" \
  --maintenance-window-end "2024-12-07T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Add "no minor or node upgrades" exclusion (maximum control)
gcloud container clusters update CLUSTER_NAME --zone ZONE \
  --add-maintenance-exclusion-name "standard-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Set reasonable disruption intervals
gcloud container clusters update CLUSTER_NAME --zone ZONE \
  --maintenance-minor-version-disruption-interval=30d \
  --maintenance-patch-version-disruption-interval=7d
```

## Phase 4: Establish Operational Processes

### 1. Monitoring & Alerting

**Cloud Monitoring alerts:**
```bash
# Example: Alert on clusters approaching EoS (30 days)
# Create in Cloud Monitoring console or via Terraform
```

**Scheduled upgrade notifications:**
```bash
# Enable 72-hour advance notifications (preview March 2026)
gcloud container clusters update CLUSTER_NAME --zone ZONE \
  --enable-scheduled-upgrade-notifications
```

### 2. Controlled upgrade process

With your standardized fleet, establish this rhythm:

1. **Monthly minor upgrade planning:** Review GKE release schedule, plan upgrades during maintenance windows
2. **User-triggered minor upgrades:** Don't rely on auto-upgrades for minor versions — trigger them yourself for predictable timing:
   ```bash
   gcloud container clusters upgrade CLUSTER_NAME --zone ZONE \
     --cluster-version TARGET_MINOR_VERSION
   ```
3. **Patches auto-upgrade:** Let patches auto-apply during maintenance windows (security critical)
4. **Staging validation:** Upgrade staging first, validate for 48-72h, then prod

### 3. Fleet-wide upgrade orchestration

For sophisticated multi-cluster coordination:

**Option A: Rollout sequencing (advanced)**
```bash
# Configure fleet-wide upgrade ordering with soak times
gcloud container fleet clusterupgrade update --project=PROJECT_ID \
  --default-upgrade-soaking=7d
```

**Option B: Simple channel strategy (recommended for most)**
- Dev/Staging: Regular channel
- Prod: Regular or Stable channel  
- Use "no minor" exclusions + manual minor upgrades to keep environments in sync

## Phase 5: Fleet Health Dashboard

Create a simple monitoring dashboard with these key metrics:

1. **Version currency:** Clusters on current/N-1/N-2 minor versions
2. **Channel distribution:** Regular/Stable/Extended enrollment %
3. **EoS risk:** Clusters within 60/30/0 days of End of Support
4. **Deprecated API usage:** Clusters with blocking deprecation insights
5. **Maintenance exclusion coverage:** % of clusters with appropriate exclusions
6. **Auto-upgrade pause status:** Clusters with paused upgrades (usually API deprecation)

## Self-Service Tools Summary

| Tool | What it shows | When to use |
|------|---------------|-------------|
| **GKE Deprecation Insights** | Deprecated API usage blocking upgrades | Before any upgrade planning |
| **Cloud Console Fleet View** | Version distribution, channel health | Weekly fleet health reviews |
| **`gcloud container clusters get-upgrade-info`** | Per-cluster upgrade targets and EoS dates | Upgrade planning for specific clusters |
| **GKE Release Schedule** | When new versions become available | Monthly upgrade planning |
| **Security Command Center** | Security posture based on version currency | Security compliance reporting |
| **Cloud Monitoring + Alerting** | Proactive notifications on EoS risk | Ongoing operational awareness |
| **Scheduled upgrade notifications** | 72h advance warning of auto-upgrades | Upgrade preparation |

## Quick Win Checklist

Focus on these high-impact, low-risk changes first:

```markdown
Fleet Remediation Quick Wins
- [ ] Migrate all "No channel" clusters to Regular channel
- [ ] Add "no minor or node upgrades" maintenance exclusions to all production clusters
- [ ] Configure maintenance windows aligned with your change management process
- [ ] Fix deprecated API usage (check GKE insights dashboard)
- [ ] Enable EoS monitoring alerts (30-day warning)
- [ ] Document your target channel strategy and maintenance process
- [ ] Set up scheduled upgrade notifications for advance planning
```

## Timeline Estimate

- **Week 1-2:** Complete assessment, identify critical EoS clusters
- **Week 3-4:** Emergency upgrades for EoS clusters, fix deprecated APIs
- **Week 5-6:** Migrate "No channel" clusters to release channels
- **Week 7-8:** Standardize maintenance policies across fleet
- **Week 9-10:** Establish monitoring, alerting, and upgrade processes

The key is **standardization over perfection** — get all clusters onto a consistent, manageable lifecycle first. You can optimize version currency and advanced features later once you have control.