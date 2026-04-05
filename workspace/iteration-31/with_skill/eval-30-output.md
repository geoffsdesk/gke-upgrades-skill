# GKE Fleet Health Assessment & Remediation Plan

You've inherited a classic "snowflake fleet" — clusters with manually frozen versions that deviate from automated lifecycle management. Here's how to systematically assess and remediate using GKE's self-service tools.

## Phase 1: Fleet Discovery & Assessment (Week 1)

### Automated Fleet Inventory

**GKE Fleet Dashboard (recommended starting point):**
```bash
# List all clusters across projects
gcloud container clusters list --format="table(name,zone,currentMasterVersion,releaseChannel.channel,status,nodeConfig.machineType)" --sort-by=zone

# Multi-project discovery
for project in $(gcloud projects list --format="value(projectId)"); do
  echo "=== Project: $project ==="
  gcloud container clusters list --project=$project --format="table(name,zone,currentMasterVersion,releaseChannel.channel)"
done
```

**Critical assessment queries:**
```bash
# Version skew analysis
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
  --format="table(name,currentMasterVersion,nodePools[].name,nodePools[].version)"

# End of Support risk check
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION \
  --format="table(cluster,autoUpgradeStatus,endOfStandardSupportTimestamp,minorTargetVersion)"

# Maintenance configuration audit
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
  --format="yaml(maintenancePolicy)"
```

### GKE Recommender Insights (your best friend)

**Comprehensive fleet health check:**
```bash
# Deprecated API usage (blocks auto-upgrades)
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=LOCATION \
  --project=PROJECT_ID \
  --filter="category.category:RELIABILITY AND state.state:ACTIVE"

# Version and configuration issues
gcloud recommender recommendations list \
  --recommender=google.container.DiagnosisRecommender \
  --location=LOCATION \
  --project=PROJECT_ID \
  --format="table(name,description,primaryImpact.category)"
```

**Key insight types to prioritize:**
- `DEPRECATED_API_VERSION` — immediate auto-upgrade blockers
- `CLUSTER_VERSION_SKEW` — control plane vs node version gaps
- `PDB_UNPERMISSIVE` — upgrade-blocking PodDisruptionBudgets
- Node pool configuration issues

### Fleet Health Scoring

Create a simple health matrix:

| Cluster | Channel | CP Version | Node Version | Days Behind | EoS Risk | Deprecated APIs | Grade |
|---------|---------|------------|--------------|-------------|----------|----------------|-------|
| prod-east | No channel | 1.28.5 | 1.27.8 | 180+ | HIGH | 3 found | F |
| staging-west | Regular | 1.29.2 | 1.29.2 | 45 | LOW | 0 | B |
| dev-central | None | 1.26.1 | 1.26.1 | 365+ | CRITICAL | 8 found | F |

**Grading criteria:**
- **A**: Current channel, <30 days behind, no deprecated APIs
- **B**: On channel, <90 days behind, no blocking issues  
- **C**: On channel, 90-180 days behind, minor issues
- **D**: Legacy config, 180+ days behind, multiple issues
- **F**: No channel, 365+ days behind, deprecated APIs

## Phase 2: Triage & Risk Assessment (Week 2)

### Critical vs. Non-Critical Separation

**Immediate EoS risk (fix within 30 days):**
```bash
# Clusters approaching forced upgrade
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=LOCATION \
  --project=PROJECT_ID \
  --filter="insightSubtype:VERSION_END_OF_SUPPORT"
```

**Production vs. Non-Production:**
- **Production clusters**: Conservative upgrade path, Extended channel consideration
- **Dev/staging**: Aggressive catch-up, Regular channel, accept higher risk

### Workload Impact Assessment

**Stateful workload identification:**
```bash
kubectl get statefulsets -A -o wide
kubectl get persistentvolumes -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy,STORAGECLASS:.spec.storageClassName
```

**Deprecated API usage audit:**
```bash
# Historical usage (requires audit logging enabled)
gcloud logging read '
resource.type="k8s_cluster"
protoPayload.request.apiVersion=~".*/(v1beta1|v1alpha1).*"
' --limit=100 --format="table(timestamp,protoPayload.request.kind,protoPayload.request.apiVersion)"

# Active usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```

## Phase 3: Standardization Strategy

### Target Architecture (the end state)

**Recommended fleet standard:**
- **Dev/Test**: Regular channel, weekly maintenance windows, basic PDBs
- **Staging**: Regular channel, "no minor" exclusions, user-triggered minor upgrades
- **Production**: Extended channel OR Regular with "no minor or node" exclusions
- **All clusters**: Automated patch upgrades, proper PDBs, rollout sequencing

### Channel Migration Priority

**Migration order (lowest to highest risk):**

1. **Dev clusters** → Regular channel (immediate)
2. **Staging clusters** → Regular channel with "no minor" exclusion
3. **Production clusters** → Extended channel (maximum control)
4. **Legacy "No channel"** → Regular or Extended based on tolerance

**Channel migration template:**
```bash
# Step 1: Add temporary freeze during migration
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-start-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-end-time "$(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-scope no_upgrades

# Step 2: Migrate channel
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular  # or extended for prod

# Step 3: Configure ongoing maintenance policy
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-02-03T02:00:00Z" \
  --maintenance-window-end "2024-02-03T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA" \
  --add-maintenance-exclusion-scope no_minor_upgrades \  # optional for prod
  --add-maintenance-exclusion-until-end-of-support

# Step 4: Remove temporary freeze
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "channel-migration"
```

## Phase 4: Automated Catch-Up Process

### Batch Upgrade Approach

**Dev clusters (aggressive catch-up):**
```bash
# Allow auto-upgrades, monitor for 2 weeks
gcloud container clusters update DEV_CLUSTER \
  --release-channel regular \
  --maintenance-window-start "2024-02-01T01:00:00Z" \
  --maintenance-window-duration 6h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=TU,FR"
```

**Production clusters (controlled modernization):**
```bash
# Extended channel + patch-only auto-upgrades
gcloud container clusters update PROD_CLUSTER \
  --release-channel extended \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --maintenance-window-start "2024-02-03T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### Progressive Rollout Sequencing

**Set up fleet-wide upgrade coordination:**
```bash
# Create fleet structure
gcloud container fleet clusterupgrade update \
  --project=PROJECT_ID \
  --upstream-fleet=dev-project-id \
  --default-upgrade-soaking=7d
```

**Rollout order:** Dev → Staging (7d soak) → Prod (14d soak)

## Phase 5: Monitoring & Governance

### Fleet Health Dashboard

**Weekly health check script:**
```bash
#!/bin/bash
# fleet-health-check.sh
echo "=== GKE Fleet Health Report ==="
echo "Date: $(date)"
echo

for cluster in $(gcloud container clusters list --format="value(name,zone)" --filter="status=RUNNING"); do
  cluster_name=$(echo $cluster | cut -d' ' -f1)
  zone=$(echo $cluster | cut -d' ' -f2)
  
  # Get versions and channel
  info=$(gcloud container clusters describe $cluster_name --zone $zone \
    --format="value(currentMasterVersion,releaseChannel.channel)")
  
  # Check for deprecated APIs
  deprecated=$(kubectl --context="gke_${PROJECT_ID}_${zone}_${cluster_name}" \
    get --raw /metrics 2>/dev/null | grep apiserver_request_total | grep deprecated | wc -l)
  
  echo "Cluster: $cluster_name | Version: $info | Deprecated APIs: $deprecated"
done

# Check insights
echo
echo "=== Active Reliability Insights ==="
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=- \
  --filter="category.category:RELIABILITY AND state.state:ACTIVE" \
  --format="table(targetResources[0].name,description)" \
  --limit=10
```

### Automated Compliance Monitoring

**Cloud Functions for fleet monitoring:**
```python
# Triggered weekly, checks fleet compliance
def check_fleet_health(request):
    insights = get_gke_insights()
    deprecated_apis = [i for i in insights if 'DEPRECATED_API' in i.subtype]
    
    if deprecated_apis:
        send_alert(f"URGENT: {len(deprecated_apis)} clusters have deprecated API usage")
    
    return {"status": "checked", "issues": len(deprecated_apis)}
```

### Governance Policies

**Establish cluster standards:**
```yaml
# org-policy.yaml - prevent new "No channel" clusters
apiVersion: orgpolicy.gstackdriver.com/v1alpha1
kind: Policy
spec:
  constraint: constraints/container.requireReleaseChannel
  booleanPolicy:
    enforced: true
```

**SLI/SLO for fleet health:**
- **Objective**: 95% of production clusters within 2 minor versions of latest
- **Measurement**: Weekly automated assessment
- **Alert threshold**: Any prod cluster >90 days behind patches

## Implementation Timeline

**Week 1-2: Assessment**
- [ ] Complete fleet inventory
- [ ] Run GKE recommender analysis  
- [ ] Identify critical EoS clusters
- [ ] Catalog deprecated API usage

**Week 3-4: Emergency Fixes**
- [ ] Migrate EoS-risk clusters to Extended channel
- [ ] Apply maintenance exclusions to prevent forced upgrades
- [ ] Fix deprecated API usage blocking auto-upgrades

**Week 5-8: Standardization**
- [ ] Migrate dev clusters to Regular channel
- [ ] Set up maintenance windows across fleet
- [ ] Configure rollout sequencing
- [ ] Establish monitoring dashboards

**Week 9-12: Modernization**
- [ ] User-triggered minor upgrades for staging
- [ ] Production cluster modernization (Extended channel)
- [ ] Implement governance policies
- [ ] Document new operational procedures

## Self-Service Tools Summary

**GKE provides these assessment tools:**
1. **GKE Recommender** — automated insights for version, API, and config issues
2. **Upgrade Info API** — EoS dates, auto-upgrade targets, rollback status
3. **Release Schedule** — version availability and upgrade timing across channels
4. **Cluster Notifications** — Pub/Sub alerts for EoS warnings and upgrade events
5. **Fleet Dashboard** — multi-cluster view in Cloud Console
6. **Scheduled Upgrade Notifications** — 72h advance warning (opt-in, preview)

**Start with GKE Recommender** — it automatically identifies the highest-impact issues across your fleet without requiring cluster-by-cluster analysis.

The key insight: **Don't try to manually upgrade everything immediately.** Use release channels + maintenance controls to get clusters back on automated lifecycle management, then let GKE catch them up safely over 2-3 months. The goal is sustainable operations, not heroic one-time fixes.