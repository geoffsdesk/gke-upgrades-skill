# GKE Fleet Modernization Plan

You've inherited a classic "snowflake fleet" — this is actually very common. The good news is that GKE provides excellent self-service tools to assess your current state and plan a systematic cleanup. Here's how to approach it:

## Phase 1: Discovery & Assessment (Week 1-2)

### Inventory your fleet with GKE's built-in tools

```bash
# Get overview of all clusters across projects
gcloud asset search-all-resources \
  --asset-types='container.googleapis.com/Cluster' \
  --format='table(name, location, additionalAttributes.releaseChannel, additionalAttributes.currentMasterVersion)'

# For each project, get detailed cluster info
gcloud container clusters list --format='table(
  name,
  location,
  currentMasterVersion,
  releaseChannel.channel:label="CHANNEL",
  status,
  nodePools.len():label="NODE_POOLS"
)'
```

### Use GKE's Deprecation Insights Dashboard

Navigate to **GKE Console → [Cluster name] → Details → Insights tab**. This shows:
- Deprecated API usage (the #1 upgrade blocker)
- Version compatibility issues
- Security recommendations
- Resource optimization opportunities

Or query programmatically:
```bash
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=LOCATION \
  --project=PROJECT_ID \
  --format='table(name, insightSubtype, severity, lastRefreshTime)'
```

### Check End of Support (EoS) exposure

```bash
# Get EoS dates for all clusters
for cluster in $(gcloud container clusters list --format="value(name,zone)"); do
  cluster_name=$(echo $cluster | cut -d' ' -f1)
  zone=$(echo $cluster | cut -d' ' -f2)
  echo "=== $cluster_name ($zone) ==="
  gcloud container clusters get-upgrade-info $cluster_name --region $zone \
    --format='value(endOfStandardSupportTimestamp, endOfExtendedSupportTimestamp)'
done
```

### Categorize clusters by risk level

Create a spreadsheet with this data for each cluster:
- **Cluster name** / **Project** / **Zone**
- **Current version** / **Channel** (or "No channel")
- **Days to EoS** (End of Support)
- **Deprecated API usage** (from insights dashboard)
- **Environment** (dev/staging/prod — you'll need to determine this)
- **Workload type** (stateless/stateful/GPU/batch)
- **Business criticality** (high/medium/low)

## Phase 2: Risk-Based Prioritization (Week 2)

### Triage clusters into upgrade buckets

**🚨 Critical (upgrade within 2 weeks):**
- Clusters <30 days from EoS
- Clusters with deprecated API usage blocking auto-upgrades
- Security-sensitive production workloads on very old versions

**⚠️ High Priority (upgrade within 6 weeks):**
- "No channel" clusters (missing modern upgrade controls)
- Clusters >6 months behind current stable
- Production clusters with manual freeze configurations

**📅 Medium Priority (upgrade within 3 months):**
- Development/staging environments
- Clusters on supported versions but 2+ minors behind

**✅ Low Priority (ongoing maintenance):**
- Clusters on release channels with appropriate maintenance policies
- Recent versions with proper auto-upgrade controls

## Phase 3: Standardization Strategy

### Establish fleet-wide standards

**Target architecture for your fleet:**
```yaml
# Production clusters
Release Channel: Stable (or Regular if you need faster patches)
Maintenance Window: Saturday 2-6 AM local time
Maintenance Exclusion: "no minor or node upgrades" with persistent tracking
  # Allows security patches, blocks disruptive changes
Manual Control: User-triggered minor upgrades during planned windows

# Staging clusters  
Release Channel: Regular
Maintenance Window: Thursday 2-6 AM local time
Auto-upgrades: Full auto (no exclusions)
Purpose: Early validation before prod upgrades

# Development clusters
Release Channel: Regular (same as staging to catch issues early)
Maintenance Window: Wednesday 10 PM - 2 AM
Auto-upgrades: Full auto (no exclusions)
```

### Migration commands for legacy clusters

**Move "No channel" to release channels:**
```bash
# Before migration: check if current version is available in target channel
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels.stable.validVersions)"

# Add temporary freeze before channel migration
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-start-time "2025-01-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-01-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# Migrate to stable channel
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel stable

# Set up proper maintenance controls
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2025-01-11T02:00:00Z" \
  --maintenance-window-end "2025-01-11T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA" \
  --add-maintenance-exclusion-name "production-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Remove temporary freeze
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion "channel-migration"
```

## Phase 4: Systematic Cleanup (Weeks 3-12)

### Week-by-week execution plan

**Weeks 3-4: Critical clusters**
- Fix deprecated API usage first (check insights dashboard)
- Emergency upgrades for EoS-approaching clusters
- Focus on one cluster per day maximum

**Weeks 5-8: High priority modernization**
- Migrate "No channel" clusters to release channels
- Implement standardized maintenance policies
- Test upgrade procedures on staging equivalents

**Weeks 9-12: Fleet standardization**
- Bring all clusters to supported versions
- Implement monitoring and alerting for upgrade health
- Document runbooks and handoffs

### Self-service monitoring setup

**Set up fleet-wide upgrade notifications:**
```bash
# Enable scheduled upgrade notifications (72h advance warning)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --send-scheduled-upgrade-notifications

# Create Cloud Logging sink for upgrade events
gcloud logging sinks create gke-upgrade-events \
  projects/PROJECT_ID/topics/gke-upgrades \
  --log-filter='resource.type="gke_cluster" 
               protoPayload.metadata.operationType=~"(UPDATE_CLUSTER|UPGRADE_MASTER)"'
```

**GKE Fleet Insights Dashboard (if using multiple projects):**
Enable the [GKE Fleet dashboard](https://cloud.google.com/kubernetes-engine/docs/how-to/fleet-observability) for cross-project cluster visibility:
```bash
gcloud services enable gkehub.googleapis.com
gcloud container fleet create
```

## Phase 5: Establish Ongoing Governance

### Fleet management best practices

**Prevent future snowflakes:**
1. **Mandate release channels** — no new "No channel" clusters
2. **Standardize maintenance policies** — use templates/Terraform
3. **Monitor deprecation insights** — set up alerting for new deprecated API usage
4. **Regular fleet health reviews** — monthly check of version distribution

**Self-service tooling for your team:**
```bash
# Fleet health check script
#!/bin/bash
echo "=== GKE Fleet Health Report ==="
gcloud container clusters list --format='table(
  name:label="CLUSTER",
  location:label="ZONE", 
  currentMasterVersion:label="VERSION",
  releaseChannel.channel:label="CHANNEL",
  status:label="STATUS"
)' --sort-by=currentMasterVersion

echo -e "\n=== Clusters approaching EoS ==="
# Add EoS checking logic here using get-upgrade-info
```

### Recommended fleet architecture

For most inherited fleets, this progression works well:

1. **Immediate term:** Get everything onto supported versions and release channels
2. **3-6 months:** Standardize maintenance policies and upgrade procedures  
3. **6-12 months:** Implement proper dev→staging→prod progression with rollout sequencing
4. **Ongoing:** Automated compliance monitoring and drift prevention

## Key GKE self-service resources for ongoing management

- **GKE Release Schedule:** [cloud.google.com/kubernetes-engine/docs/release-schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) — plan upgrade timing
- **Deprecation Insights Dashboard:** Built into GKE console — proactive API deprecation warnings  
- **Upgrade Info API:** `gcloud container clusters get-upgrade-info` — programmatic upgrade planning
- **Fleet Insights:** Cross-project cluster visibility and compliance monitoring
- **Release Notes:** [cloud.google.com/kubernetes-engine/docs/release-notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) — breaking changes between versions

The most important insight: **don't try to fix everything at once**. Focus on eliminating immediate EoS risk first, then systematically modernize. GKE's tooling will guide you through the process once you establish the assessment baseline.