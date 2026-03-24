# GKE Fleet Health Assessment & Recovery Plan

You're in a common situation - inherited GKE debt is widespread. The good news is GKE provides excellent self-service tools to assess your fleet and create a recovery plan. Here's a systematic approach:

## Phase 1: Fleet Discovery & Assessment (Week 1-2)

### Inventory your clusters

```bash
# Get all clusters across projects
gcloud projects list --format="value(projectId)" | while read project; do
  echo "=== Project: $project ==="
  gcloud container clusters list --project=$project --format="table(
    name,
    location,
    currentMasterVersion,
    releaseChannel.channel:label=CHANNEL,
    status,
    nodePools[].version.list():label=NODE_VERSIONS
  )"
done > cluster-inventory.txt
```

### Use GKE's built-in assessment tools

**1. GKE Deprecation Insights Dashboard**
- Go to GKE console → any cluster → "Insights" tab
- Shows deprecated API usage, version skew, EoS timelines
- Export via: `gcloud recommender insights list --insight-type=google.container.DiagnosisInsight --location=LOCATION --project=PROJECT_ID`

**2. GKE Release Schedule Page**
- Visit [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule)
- Shows version timelines, EoS dates, channel availability
- Critical for understanding your upgrade runway

**3. Upgrade Info API (per cluster)**
```bash
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION --format="yaml"
# Shows: autoUpgradeStatus, EoS timestamps, target versions
```

## Phase 2: Risk Assessment & Prioritization

### Categorize clusters by risk level

**CRITICAL (upgrade immediately):**
- Versions at or past End of Support
- "No channel" clusters approaching EoS
- Deprecated API usage blocking auto-upgrades
- Security vulnerabilities in current version

**HIGH (upgrade within 30 days):**
- Versions 2+ minor versions behind current
- Clusters with version skew (nodes >2 versions behind control plane)
- Production workloads on "No channel"

**MEDIUM (upgrade within 60 days):**
- Versions 1 minor behind current
- Dev/staging on suboptimal channels

**LOW (upgrade during next maintenance window):**
- Recent versions on appropriate release channels
- Proper maintenance windows configured

### Create a risk matrix

```bash
# Generate cluster risk assessment
for cluster in $(gcloud container clusters list --format="value(name,zone)"); do
  name=$(echo $cluster | cut -d' ' -f1)
  zone=$(echo $cluster | cut -d' ' -f2)
  
  echo "Cluster: $name"
  gcloud container clusters get-upgrade-info $name --zone $zone \
    --format="value(endOfStandardSupportTimestamp,autoUpgradeStatus)"
done
```

## Phase 3: Migration Strategy

### Channel migration priority order

1. **Legacy "No channel" → Regular/Stable** (highest priority)
2. **Rapid → Regular** for production clusters
3. **Consolidate on consistent channel strategy** across environments

**Recommended channel strategy:**
- **Dev**: Regular channel (gets features ~1 week after Rapid validation)
- **Staging**: Regular channel (same as prod for parity)
- **Prod**: Regular or Stable channel (Stable for maximum stability)

### Migration commands

```bash
# Migrate legacy "No channel" to Regular (closest to legacy behavior)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular

# Add "no minor or node upgrades" exclusion for maximum control (up to EoS)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "migration-control" \
  --add-maintenance-exclusion-until-end-of-support \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**Migration warning:** When moving from "No channel" to release channels, if your current version isn't available in the target channel yet, your cluster will be "ahead of channel" and won't receive auto-upgrades until the channel catches up.

## Phase 4: Standardize Maintenance Controls

### Establish consistent maintenance windows

```bash
# Standard maintenance windows (adjust for your timezone)
# Production: Saturday 2-6 AM
gcloud container clusters update PROD_CLUSTER \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-end "2024-01-06T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Dev/Staging: Wednesday 2-4 AM  
gcloud container clusters update DEV_CLUSTER \
  --zone ZONE \
  --maintenance-window-start "2024-01-03T02:00:00Z" \
  --maintenance-window-end "2024-01-03T04:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=WE"
```

### Set up upgrade controls for cautious customers

```bash
# "No minor or node upgrades" - allows CP security patches, maximum control
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "minor-upgrade-control" \
  --add-maintenance-exclusion-until-end-of-support \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

This lets you control when minor upgrades happen while still getting security patches.

## Phase 5: Monitoring & Alerting Setup

### Enable GKE upgrade notifications

```bash
# Subscribe to cluster notifications via Pub/Sub
gcloud logging sinks create gke-upgrade-alerts \
  pubsub.googleapis.com/projects/PROJECT_ID/topics/gke-upgrades \
  --log-filter='resource.type="gke_cluster" protoPayload.metadata.operationType=~"(UPDATE_CLUSTER|UPGRADE_MASTER)"'
```

### Set up version drift monitoring

```bash
# Create a simple monitoring script
cat > check-version-drift.sh << 'EOF'
#!/bin/bash
for cluster in $(gcloud container clusters list --format="value(name,zone)"); do
  name=$(echo $cluster | cut -d' ' -f1)
  zone=$(echo $cluster | cut -d' ' -f2)
  
  gcloud container clusters describe $name --zone $zone \
    --format="csv[no-heading](name,currentMasterVersion,nodePools[].version.flatten())" \
    >> version-report.csv
done
EOF
```

## Phase 6: Recovery Execution Plan

### Week 1-2: Emergency fixes
- Upgrade EoS clusters immediately
- Fix deprecated API usage
- Migrate critical "No channel" clusters

### Week 3-4: Channel standardization  
- Move all clusters to appropriate release channels
- Configure maintenance windows
- Set up monitoring

### Week 5-8: Version convergence
- Bring all clusters to supported versions
- Establish consistent minor versions across environments
- Document new maintenance procedures

### Ongoing: Maintenance discipline
- Review cluster health monthly via GKE insights dashboard
- Plan minor upgrades quarterly using "no minor" exclusions + manual upgrades
- Monitor the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) for upcoming EoS dates

## Key GKE Self-Service Tools Summary

1. **GKE Insights Dashboard** - Shows deprecation warnings, API usage, EoS timeline
2. **Upgrade Info API** - Per-cluster auto-upgrade status and target versions
3. **GKE Release Schedule** - Version timelines and availability across channels  
4. **Cloud Logging** - Upgrade events and notifications
5. **Recommender Insights** - Programmatic access to deprecation data

## Important: What NOT to do

- **Don't stay on "No channel"** - migrate to release channels for better tools
- **Don't disable auto-upgrades** - use maintenance exclusions for control instead  
- **Don't upgrade everything at once** - stage by environment and risk level
- **Don't ignore version skew** - nodes >2 versions behind control plane will be force-upgraded

The key insight is that GKE's value is in **automated lifecycle management**. Your goal isn't to control everything manually, but to set up the right guardrails (channels + maintenance windows + exclusions) so GKE can manage upgrades predictably and safely.

Would you like me to focus on any specific part of this plan, or help you assess a particular cluster that's in especially bad shape?