# GKE Fleet Health Assessment & Remediation Plan

You've inherited a classic "snowflake" fleet situation. Here's a systematic approach to assess, prioritize, and remediate your GKE clusters using GKE's built-in tools.

## Phase 1: Fleet Assessment & Discovery

### Immediate inventory with GKE's built-in tools

**1. Cluster inventory across all projects:**
```bash
# Get all clusters across your organization
gcloud container clusters list --format="table(
    name,
    location,
    currentMasterVersion,
    releaseChannel.channel:label=CHANNEL,
    autopilot.enabled:label=AUTOPILOT,
    status
)" --filter="status=RUNNING"

# Export to CSV for analysis
gcloud container clusters list --format="csv(
    name,
    location,
    currentMasterVersion,
    releaseChannel.channel,
    autopilot.enabled,
    nodePools[].version.list()
)" > cluster-inventory.csv
```

**2. Use GKE deprecation insights dashboard:**
- Navigate to GKE console → select each cluster → "Insights" tab
- Look for red/orange deprecation warnings
- Export insights programmatically:
```bash
for cluster in $(gcloud container clusters list --format="value(name)"); do
  gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=LOCATION \
    --project=PROJECT_ID \
    --filter="category.category:RELIABILITY" \
    --format="table(name,description,severity)"
done
```

**3. End of Support (EoS) risk assessment:**
```bash
# Check EoS dates for all clusters
for cluster in $(gcloud container clusters list --format="value(name)"); do
  echo "=== $cluster ==="
  gcloud container clusters get-upgrade-info $cluster \
    --region REGION \
    --format="table(
      endOfStandardSupportTimestamp,
      endOfExtendedSupportTimestamp,
      autoUpgradeStatus
    )"
done
```

**4. Version skew analysis:**
```bash
# Identify clusters with node version skew issues
gcloud container clusters list --format="table(
  name,
  currentMasterVersion,
  nodePools[].version.list():label='NODE_VERSIONS'
)" | grep -E "(1\.[0-9]+.*1\.[0-9]+.*1\.[0-9]+|None)"
```

## Phase 2: Risk Prioritization Matrix

Based on your assessment, prioritize clusters by risk:

### **CRITICAL (fix immediately):**
- Versions at or past End of Support
- "No channel" clusters with deprecated API usage
- Clusters with >2 minor version skew between CP and nodes
- Critical production workloads on unsupported versions

### **HIGH (fix within 30 days):**
- "No channel" clusters (migrate to release channels)
- Clusters 1-2 minor versions behind current
- Mixed node pool versions within same cluster
- Clusters with no maintenance windows configured

### **MEDIUM (fix within 90 days):**
- Clusters on Rapid channel in production
- Missing PDBs on stateful workloads
- Inconsistent release channels across environments

### **LOW (ongoing maintenance):**
- Clusters on appropriate channels but need standardization
- Documentation and runbook gaps

## Phase 3: Fleet-wide Standardization Strategy

### Target architecture (recommended for most orgs):

**Standard cluster configuration:**
- **Channel:** Regular for both dev and prod (enables rollout sequencing)
- **Maintenance windows:** Off-peak hours (e.g., Saturday 2-6 AM)
- **Exclusions:** "No minor or node upgrades" for production (allows CP patches, manual minor control)
- **Rollout sequencing:** Dev → Prod with 7-day soak time

**Alternative for conservative environments:**
- **Channel:** Extended for production (24-month support, no auto-minor upgrades)
- **Exclusions:** Persistent "no minor or node upgrades" with end-of-support tracking
- **Disruption intervals:** 90-day patch interval for maximum control

### Mass migration approach

**1. Create standardized maintenance policies:**
```bash
# Template for production clusters
gcloud container clusters update CLUSTER_NAME \
  --release-channel regular \
  --maintenance-window-start "2025-01-04T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**2. Batch migration script for "No channel" clusters:**
```bash
#!/bin/bash
# Migrate legacy clusters to Regular channel

CLUSTERS=($(gcloud container clusters list --format="value(name)" --filter="releaseChannel.channel=''"))

for cluster in "${CLUSTERS[@]}"; do
  echo "Migrating $cluster to Regular channel..."
  
  # Add temporary freeze during migration
  gcloud container clusters update $cluster \
    --add-maintenance-exclusion-name "channel-migration" \
    --add-maintenance-exclusion-start-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --add-maintenance-exclusion-end-time "$(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ)" \
    --add-maintenance-exclusion-scope no_upgrades
  
  # Migrate to channel
  gcloud container clusters update $cluster \
    --release-channel regular
  
  # Configure maintenance window
  gcloud container clusters update $cluster \
    --maintenance-window-start "2025-01-04T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
  
  # Remove temporary freeze, add permanent minor control
  gcloud container clusters update $cluster \
    --remove-maintenance-exclusion "channel-migration" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
done
```

## Phase 4: GKE Self-Service Assessment Tools

**1. GKE Recommender (your best friend):**
```bash
# Get all reliability insights (includes deprecations, version issues)
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=LOCATION \
  --project=PROJECT_ID \
  --filter="category.category:RELIABILITY" \
  --format="table(name,description,severity,insightSubtype)"

# Performance insights (resource right-sizing, PDB issues)
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=LOCATION \
  --project=PROJECT_ID \
  --filter="category.category:PERFORMANCE"
```

**2. Upgrade info API for systematic planning:**
```bash
# Create upgrade readiness report
for cluster in $(gcloud container clusters list --format="value(name)"); do
  echo "=== $cluster upgrade status ==="
  gcloud container clusters get-upgrade-info $cluster --region REGION \
    --format="yaml(
      autoUpgradeStatus,
      minorTargetVersion,
      patchTargetVersion,
      endOfStandardSupportTimestamp
    )"
done
```

**3. Fleet-level monitoring setup:**
```bash
# Enable scheduled upgrade notifications (72h advance warning)
for cluster in $(gcloud container clusters list --format="value(name)"); do
  gcloud container clusters update $cluster \
    --enable-scheduled-upgrades
done
```

**4. Deprecated API usage detection:**
```bash
# Script to check all clusters for deprecated API usage
#!/bin/bash
for cluster in $(gcloud container clusters list --format="value(name,zone)"); do
  cluster_name=$(echo $cluster | cut -d' ' -f1)
  zone=$(echo $cluster | cut -d' ' -f2)
  
  echo "=== Checking $cluster_name for deprecated APIs ==="
  gcloud container clusters get-credentials $cluster_name --zone $zone
  
  # Check via metrics
  kubectl get --raw /metrics 2>/dev/null | grep apiserver_request_total | grep deprecated || echo "No deprecated API usage detected"
done
```

## Phase 5: Rollout Sequencing Setup (Advanced)

For organizations with 10+ clusters, set up automated rollout sequencing:

**1. Create fleet structure:**
```bash
# Dev fleet
gcloud container fleet create dev-fleet --project DEV_PROJECT

# Prod fleet (upstream from dev)
gcloud container fleet create prod-fleet --project PROD_PROJECT \
  --upstream-fleet projects/DEV_PROJECT/locations/global/fleets/dev-fleet \
  --default-upgrade-soaking 7d
```

**2. Enroll clusters:**
```bash
# Enroll dev clusters
gcloud container fleet membership register dev-cluster-1 \
  --gke-cluster LOCATION/CLUSTER_NAME \
  --project DEV_PROJECT

# Enroll prod clusters
gcloud container fleet membership register prod-cluster-1 \
  --gke-cluster LOCATION/CLUSTER_NAME \
  --project PROD_PROJECT
```

## Phase 6: Ongoing Fleet Health Monitoring

**1. Weekly health check script:**
```bash
#!/bin/bash
# weekly-gke-health-check.sh

echo "=== GKE Fleet Health Report $(date) ==="

# Version distribution
echo "--- Version Distribution ---"
gcloud container clusters list --format="table(currentMasterVersion)" | sort | uniq -c

# Clusters approaching EoS
echo "--- Clusters Near End of Support ---"
# (insert EoS check logic)

# Deprecated API usage alerts
echo "--- Deprecated API Usage ---"
# (insert deprecated API check)

# Channel distribution
echo "--- Release Channel Distribution ---"
gcloud container clusters list --format="table(releaseChannel.channel)" | sort | uniq -c
```

**2. Set up Cloud Monitoring dashboards:**
- Create custom dashboard tracking fleet version distribution
- Set up alerts for clusters approaching EoS
- Monitor upgrade success/failure rates across the fleet

## Key Self-Service Resources

1. **GKE Release Schedule:** https://cloud.google.com/kubernetes-engine/docs/release-schedule
2. **Deprecation Information:** https://cloud.google.com/kubernetes-engine/docs/deprecations
3. **Upgrade Assist Common Scenarios:** https://cloud.google.com/kubernetes-engine/docs/how-to/upgrade-assist#common-upgrades-scenarios
4. **Fleet Management:** https://cloud.google.com/kubernetes-engine/docs/fleets-overview

## Success Metrics

Track these KPIs to measure fleet health improvement:

- **Version spread:** Target ≤2 minor versions across entire fleet
- **Channel standardization:** >90% of clusters on appropriate channels
- **EoS risk:** Zero clusters within 30 days of End of Support
- **Deprecated API usage:** Zero clusters with deprecated API insights
- **Maintenance coverage:** 100% of clusters have maintenance windows configured

**Expect 3-6 months for full remediation** of a heavily "snowflaked" fleet. Start with the critical risk clusters and work systematically through the priority matrix. The GKE recommender and upgrade info API will be your primary tools for ongoing assessment and planning.