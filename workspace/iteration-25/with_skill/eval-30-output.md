# GKE Fleet Remediation Plan

You've inherited a classic "snowflake fleet" — clusters with divergent versions, mismatched channels, and accumulated technical debt. Here's a systematic approach to get your fleet into a healthy, well-managed state.

## Phase 1: Assessment & Discovery

### Inventory Your Fleet

**Cluster Discovery:**
```bash
# Get all clusters across projects/regions
gcloud container clusters list --format="table(
  name,
  location,
  currentMasterVersion,
  releaseChannel.channel:label='CHANNEL',
  status,
  nodePools[].version.list():label='NODE_VERSIONS'
)" --sort-by=currentMasterVersion

# For programmatic analysis
gcloud container clusters list --format=json > fleet-inventory.json
```

**Per-cluster health check:**
```bash
#!/bin/bash
# fleet-health-check.sh
for cluster in $(gcloud container clusters list --format="value(name,location)"); do
  name=$(echo $cluster | cut -d' ' -f1)
  zone=$(echo $cluster | cut -d' ' -f2)
  
  echo "=== $name ($zone) ==="
  
  # Version info
  gcloud container clusters describe $name --location $zone \
    --format="table(currentMasterVersion, releaseChannel.channel, autopilot.enabled)"
  
  # EoS status
  gcloud container clusters get-upgrade-info $name --location $zone \
    --format="table(endOfStandardSupportTimestamp, endOfExtendedSupportTimestamp)"
  
  echo ""
done
```

### GKE Self-Service Assessment Tools

**1. GKE Deprecation Insights Dashboard**
- Console → GKE → Insights tab
- Shows deprecated API usage, version skew, unpermissive PDBs
- **Critical**: Use this to identify clusters with deprecated APIs that will block auto-upgrades

**2. GKE Recommender API**
```bash
# Deprecated API insights (most critical for upgrades)
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=LOCATION \
  --project=PROJECT_ID \
  --filter="category.category:RELIABILITY"

# Cost optimization insights
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=LOCATION \
  --project=PROJECT_ID \
  --filter="category.category:COST"
```

**3. Config Connector Inventory (if using)**
```bash
# Find GKE resources managed as IaC
kubectl get gkecluster,gkenodepool -A -o wide
```

**4. Release Schedule Planning**
- [GKE Release Schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule)
- Shows version availability, auto-upgrade timing, EoS dates per channel
- Essential for planning your target state

## Phase 2: Risk Assessment & Prioritization

### Cluster Risk Matrix

**Critical (fix first):**
- "No channel" clusters approaching EoS
- Clusters with deprecated API usage (blocks auto-upgrades)
- Production clusters >2 minor versions behind
- Clusters with version skew violations (nodes >2 versions behind CP)

**High:**
- Mixed node pool versions within cluster
- Clusters without maintenance windows
- GPU clusters on incompatible versions
- Clusters with unpermissive PDBs

**Medium:**
- Suboptimal release channel selection
- Missing rollout sequencing for multi-env
- No maintenance exclusion strategy

### Version Compatibility Assessment

```bash
# Check version skew across your fleet
gcloud container clusters list --format="table(
  name,
  currentMasterVersion,
  nodePools[].version.list()
)" | awk '
BEGIN { print "Cluster\tCP_Version\tNode_Versions\tSkew_Risk" }
NR>1 {
  cp_version = $2
  node_versions = $3
  # Simple heuristic - flag if node versions differ from CP by >1 minor
  print $1 "\t" cp_version "\t" node_versions "\t" "CHECK_MANUALLY"
}'
```

## Phase 3: Target Architecture Design

### Recommended Standard Configuration

**Channel Strategy:**
- **Dev environments**: Regular channel (balanced updates, full SLA)
- **Production**: Regular or Stable channel
- **Compliance/regulated**: Extended channel (24-month support, manual minor upgrades)

**Maintenance Controls:**
```yaml
# Standard production cluster config
maintenancePolicy:
  window:
    startTime: "2024-01-01T02:00:00Z"  # 2 AM local time
    duration: "4h"
    recurrence: "FREQ=WEEKLY;BYDAY=SA"  # Saturday nights
  resourceVersion: "..."
```

**For maximum control (regulated environments):**
```bash
gcloud container clusters update CLUSTER_NAME \
  --release-channel extended \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --maintenance-window-start "2024-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### Multi-Cluster Fleet Design

**Option A: Same Channel + Rollout Sequencing (Recommended)**
- All environments on Regular channel
- Use rollout sequencing to ensure dev → staging → prod order
- Patches auto-upgrade in sequence
- Manual minor upgrade control via exclusions

**Option B: Two-Channel Progression**
- Dev: Regular channel
- Prod: Stable channel  
- Natural progression (Regular gets versions before Stable)
- Cannot use rollout sequencing (requires same channel)

## Phase 4: Migration Execution

### 1. Fix Critical Issues First

**Deprecated API Remediation:**
```bash
# Identify problematic clusters
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=LOCATION \
  --project=PROJECT_ID \
  --filter="insightSubtype:API_VERSION_DEPRECATED"

# Per-cluster API usage check
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```

**Channel Migration (No channel → Release channel):**
```bash
# Check if current version is available in target channel first
gcloud container get-server-config --location LOCATION --format="yaml(channels.regular.validVersions)"

# Migrate to Regular (closest to legacy behavior)
gcloud container clusters update CLUSTER_NAME \
  --location LOCATION \
  --release-channel regular
```

### 2. Version Standardization

**Upgrade Path Planning:**
```bash
# Generate upgrade sequence for severely outdated clusters
#!/bin/bash
current_version="1.27.8-gke.1067004"  # example
target_version="1.31.1-gke.1014001"   # example

# Control plane: must be sequential minor versions
echo "Control plane upgrade path:"
echo "1.27.8 → 1.28.x → 1.29.x → 1.30.x → 1.31.1"

# Node pools: can do skip-level within supported skew
echo "Node pool upgrade path:"
echo "1.27.8 → 1.31.1 (skip-level after CP at 1.31.1)"
```

**Batch Upgrade Script:**
```bash
#!/bin/bash
# batch-upgrade.sh - upgrade multiple clusters to same target version

TARGET_VERSION="1.31.1-gke.1014001"
CLUSTERS=(
  "cluster1:us-central1-a"
  "cluster2:us-central1-b"
)

for entry in "${CLUSTERS[@]}"; do
  name=$(echo $entry | cut -d: -f1)
  location=$(echo $entry | cut -d: -f2)
  
  echo "Upgrading $name in $location..."
  
  # Control plane first
  gcloud container clusters upgrade $name \
    --location $location \
    --master \
    --cluster-version $TARGET_VERSION \
    --quiet
  
  # Wait and verify
  echo "Waiting for CP upgrade to complete..."
  sleep 300  # 5 min
  
  # Then node pools
  gcloud container node-pools upgrade default-pool \
    --cluster $name \
    --location $location \
    --cluster-version $TARGET_VERSION \
    --quiet
done
```

### 3. Maintenance Policy Standardization

**Fleet-wide maintenance window deployment:**
```bash
#!/bin/bash
# apply-maintenance-windows.sh

# Standard maintenance window: Saturday 2-6 AM
MAINTENANCE_CONFIG='
--maintenance-window-start "2024-01-01T02:00:00Z"
--maintenance-window-duration 4h
--maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
'

# Apply to all production clusters
for cluster in $(gcloud container clusters list --filter="name~prod" --format="value(name,location)"); do
  name=$(echo $cluster | cut -d' ' -f1)
  location=$(echo $cluster | cut -d' ' -f2)
  
  echo "Applying maintenance window to $name..."
  gcloud container clusters update $name \
    --location $location \
    $MAINTENANCE_CONFIG
done
```

## Phase 5: Ongoing Management

### Monitoring & Alerting

**Cloud Monitoring Queries:**
```sql
-- Clusters approaching EoS
fetch gke_cluster
| filter resource.cluster_name != ""
| group_by [resource.cluster_name, resource.location]

-- Deprecated API usage
fetch gke_cluster
| filter metric.type == "kubernetes.io/container/deprecated_api_requests"
| group_by [resource.cluster_name]
```

**Scheduled Upgrade Notifications (Preview):**
```bash
# Enable 72-hour advance notifications
gcloud container clusters update CLUSTER_NAME \
  --location LOCATION \
  --enable-scheduled-upgrades
```

### Fleet-wide Rollout Sequencing

**Configure for coordinated upgrades:**
```bash
# Example: dev → staging → prod progression
gcloud container fleet clusterupgrade update \
  --project=PROJECT_ID \
  --upstream-fleet=dev-project-id \
  --default-upgrade-soaking=24h
```

### Self-Service Upgrade Planning

**Regular Health Checks:**
```bash
#!/bin/bash
# weekly-fleet-health.sh - run every week
echo "=== Fleet Health Report $(date) ==="

# Version distribution
echo "Version Distribution:"
gcloud container clusters list --format="table(currentMasterVersion)" | sort | uniq -c

# EoS warnings
echo "Approaching EoS:"
gcloud container clusters list --format=json | \
  jq -r '.[] | select(.currentMasterVersion | test("1\\.(29|30)")) | .name + " (" + .currentMasterVersion + ")"'

# Deprecated APIs
echo "Clusters with deprecated API usage:"
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=- \
  --project=PROJECT_ID \
  --filter="insightSubtype:API_VERSION_DEPRECATED" \
  --format="value(targetResources[0].name)"
```

## Key Recommendations

### Immediate Actions (Week 1-2)
1. **Inventory all clusters** using the discovery scripts above
2. **Fix deprecated API usage** on any cluster showing insights
3. **Migrate "No channel" clusters** to Regular or Extended
4. **Apply maintenance windows** to prevent unexpected upgrades during remediation

### Short-term (Month 1)
1. **Standardize on target versions** (latest stable minor)
2. **Deploy maintenance exclusions** for production clusters during remediation
3. **Configure monitoring** for upgrade notifications and EoS warnings
4. **Document cluster ownership** and maintenance responsibilities

### Long-term (Months 2-3)
1. **Implement rollout sequencing** for multi-environment coordination
2. **Establish regular upgrade cadence** aligned with business cycles
3. **Automate fleet health monitoring** with alerting
4. **Train teams** on GKE upgrade best practices

### Anti-patterns to Avoid
- **Don't freeze versions indefinitely** — security debt accumulates
- **Don't skip testing** deprecated API compatibility in staging
- **Don't upgrade all environments simultaneously** — use progressive rollout
- **Don't ignore maintenance windows** — they're your primary timing control

This systematic approach will transform your "snowflake fleet" into a well-managed, standardized, and secure GKE environment. The key is prioritizing critical issues first while establishing sustainable long-term practices.