# GKE Fleet Health Assessment & Remediation Plan

You're dealing with a classic "inherited fleet" scenario. Here's a systematic approach to get your clusters into a healthy, well-managed state using GKE's built-in assessment tools.

## Phase 1: Discovery & Assessment (Week 1-2)

### Fleet inventory with GKE's built-in tools

```bash
# Get all clusters across all regions/zones
gcloud container clusters list --format="table(
  name,
  location,
  currentMasterVersion,
  releaseChannel.channel:label='CHANNEL',
  status,
  nodePools.len():label='NODE_POOLS',
  autopilot.enabled:label='AUTOPILOT'
)"

# For each cluster, get detailed version info
for cluster in $(gcloud container clusters list --format="value(name,location)"); do
  IFS=$'\t' read -r name location <<< "$cluster"
  echo "=== $name ($location) ==="
  gcloud container clusters get-upgrade-info "$name" --location="$location" \
    --format="yaml(autoUpgradeStatus,endOfStandardSupportTimestamp,endOfExtendedSupportTimestamp,minorTargetVersion,patchTargetVersion)"
done
```

### Use GKE Recommender for health insights

This is your most powerful assessment tool:

```bash
# Get all GKE-specific insights across your project
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=- \
  --project=PROJECT_ID \
  --format="table(
    name.segment(-1):label='CLUSTER',
    insightSubtype:label='ISSUE',
    description:wrap=80,
    lastRefreshTime.date():label='LAST_CHECKED'
  )"

# Common insight subtypes you'll see:
# - CLUSTER_VERSION_OUT_OF_SUPPORT (critical)
# - DEPRECATED_API_USAGE (blocks upgrades)
# - PDB_UNPERMISSIVE (blocks node drain)
# - NODE_VERSION_SKEW (nodes too far behind CP)
```

### Cluster-by-cluster health check script

Create this assessment script:

```bash
#!/bin/bash
# cluster-health-check.sh

CLUSTER=$1
LOCATION=$2

echo "=== Health Check: $CLUSTER ($LOCATION) ==="

# Basic info
echo "1. Versions & Channel:"
gcloud container clusters describe "$CLUSTER" --location="$LOCATION" \
  --format="value(currentMasterVersion,releaseChannel.channel,autopilot.enabled)"

# Node pool versions
echo "2. Node Pool Versions:"
gcloud container node-pools list --cluster="$CLUSTER" --location="$LOCATION" \
  --format="table(name,version,status)"

# Upgrade blockers
echo "3. Deprecated API Usage:"
kubectl get --raw /metrics --context="gke_$(gcloud config get-value project)_${LOCATION}_${CLUSTER}" 2>/dev/null | \
  grep apiserver_request_total | grep deprecated || echo "No deprecated APIs (good)"

# PDB issues
echo "4. Restrictive PDBs:"
kubectl get pdb -A --context="gke_$(gcloud config get-value project)_${LOCATION}_${CLUSTER}" \
  -o custom-columns="NAMESPACE:.metadata.namespace,NAME:.metadata.name,ALLOWED:.status.disruptionsAllowed" | \
  grep " 0$" || echo "No blocking PDBs (good)"

echo ""
```

## Phase 2: Risk Assessment & Prioritization (Week 2-3)

### Categorize clusters by risk level

**CRITICAL (fix immediately):**
- Clusters on versions approaching End of Support (within 60 days)
- "No channel" clusters 3+ minor versions behind
- Clusters with deprecated API usage blocking auto-upgrades

**HIGH (fix within 1 month):**
- "No channel" clusters 1-2 minor versions behind
- Node pools with >2 minor version skew from control plane
- Clusters with no maintenance windows configured

**MEDIUM (fix within 3 months):**
- Release channel clusters with restrictive PDBs
- Clusters without proper monitoring/alerting
- Missing resource requests on Autopilot

### Use GKE's upgrade assist scenarios

GKE provides [upgrade assist scenarios](https://cloud.google.com/kubernetes-engine/docs/how-to/upgrade-assist#common-upgrades-scenarios) for common inherited fleet situations:

```bash
# Check if clusters qualify for skip-level upgrades
gcloud container clusters get-upgrade-info CLUSTER_NAME --location=LOCATION \
  --format="value(controlPlaneUpgradeInfo.skipLevelUpgradeAvailable)"
```

## Phase 3: Standardization Strategy

### Recommended target architecture

**For production clusters:**
```bash
# Extended channel (24-month support, manual minor control)
gcloud container clusters update CLUSTER_NAME \
  --location LOCATION \
  --release-channel extended \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**For dev/staging clusters:**
```bash
# Regular channel with auto-upgrades
gcloud container clusters update CLUSTER_NAME \
  --location LOCATION \
  --release-channel regular \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### Migration priority order

1. **"No channel" clusters → Extended channel** (for prod) or Regular (for dev)
2. **Fix deprecated API usage** (use GKE insights + kubectl-convert tool)
3. **Standardize maintenance windows** across all clusters
4. **Configure monitoring** (cluster notifications via Pub/Sub)
5. **Implement rollout sequencing** for multi-cluster coordination

## Phase 4: Self-Service Monitoring & Alerting

### Set up cluster notifications

```bash
# Create Pub/Sub topic for cluster events
gcloud pubsub topics create gke-cluster-notifications

# Enable notifications for all clusters
for cluster in $(gcloud container clusters list --format="value(name,location)"); do
  IFS=$'\t' read -r name location <<< "$cluster"
  gcloud container clusters update "$name" \
    --location="$location" \
    --notification-config=pubsub=projects/PROJECT_ID/topics/gke-cluster-notifications
done
```

### Create a fleet health dashboard

Use this Cloud Monitoring query to track fleet health:

```sql
-- Clusters by channel and version
fetch gke_cluster
| metric 'kubernetes.io/container/uptime'
| group_by [resource.cluster_name, resource.location], 1m, [max: .mean()]
| join (
  fetch gke_cluster
  | metric 'kubernetes.io/container/cpu/limit_utilization'
  | group_by [resource.cluster_name, resource.location, metadata.release_channel]
)
```

### Automated health checks

Create a weekly fleet health report:

```bash
#!/bin/bash
# weekly-fleet-report.sh

echo "GKE Fleet Health Report - $(date)"
echo "================================="

# Clusters approaching EoS
echo "1. CLUSTERS APPROACHING END OF SUPPORT:"
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=- \
  --filter="insightSubtype:CLUSTER_VERSION_OUT_OF_SUPPORT" \
  --format="table(name.segment(-3),name.segment(-1),description)" || echo "None (good)"

# Deprecated API usage
echo "2. CLUSTERS WITH DEPRECATED API USAGE:"
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=- \
  --filter="insightSubtype:DEPRECATED_API_USAGE" \
  --format="table(name.segment(-3),name.segment(-1),description)" || echo "None (good)"

# Channel distribution
echo "3. RELEASE CHANNEL DISTRIBUTION:"
gcloud container clusters list --format="value(releaseChannel.channel)" | \
  sort | uniq -c | sort -nr

echo "4. UPGRADE RECOMMENDATIONS:"
echo "- Migrate remaining 'No channel' clusters to Extended/Regular"
echo "- Fix deprecated API usage before next minor version"
echo "- Configure maintenance windows for unmanaged clusters"
```

## Phase 5: Execution Playbook

### Week 1-2: Critical fixes
- Migrate EoS clusters to supported versions
- Fix deprecated API usage (use `kubectl-convert` tool)
- Set up cluster notifications

### Week 3-4: Channel migrations
- Move "No channel" production → Extended channel
- Move "No channel" dev/staging → Regular channel  
- Configure maintenance windows

### Week 5-8: Standardization
- Implement rollout sequencing for multi-cluster environments
- Standardize node pool upgrade strategies
- Set up automated health monitoring

### Ongoing: Operational excellence
- Weekly fleet health reports
- Quarterly access reviews
- Continuous monitoring of GKE insights

## Key Success Metrics

Track these with Cloud Monitoring:
- **Clusters on supported versions**: >95%
- **Clusters with maintenance windows**: 100%
- **Deprecated API usage**: 0 instances
- **Time to upgrade**: <48 hours for patches, <7 days for minors
- **Failed upgrade rate**: <5%

## Tools & Resources Summary

**GKE-native assessment tools:**
- `gcloud recommender insights list` — your primary health assessment tool
- `gcloud container clusters get-upgrade-info` — upgrade readiness per cluster  
- GKE console Insights tab — visual dashboard of recommendations
- [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) — version timeline planning

**Kubernetes tools:**
- `kubectl-convert` — migrate deprecated API manifests
- `kubectl get --raw /metrics` — deprecated API usage detection
- GKE cluster notifications via Pub/Sub — real-time alerting

**Planning resources:**
- [Upgrade assist scenarios](https://cloud.google.com/kubernetes-engine/docs/how-to/upgrade-assist#common-upgrades-scenarios)
- [GKE release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) 
- [Deprecations page](https://cloud.google.com/kubernetes-engine/docs/deprecations)

The key is to use GKE's built-in assessment tools first — they'll surface 80% of your issues automatically. Focus on getting clusters onto release channels with proper maintenance controls rather than trying to manually manage versions. This inherited fleet cleanup typically takes 6-8 weeks but sets you up for sustainable operations going forward.