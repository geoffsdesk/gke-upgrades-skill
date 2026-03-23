# GKE Fleet Remediation Plan

You've inherited a classic "snowflake fleet" — let me help you systematically assess and remediate these clusters using GKE's built-in tools.

## Assessment Phase: Inventory Your Fleet

Start with comprehensive discovery using GKE's assessment tools:

### 1. Fleet-wide cluster inventory

```bash
# Get all clusters across all projects/regions
gcloud container clusters list --format="table(
    name,
    location,
    currentMasterVersion,
    releaseChannel.channel:label=CHANNEL,
    status,
    nodePoolDefaults.nodeConfigDefaults.gcfsConfig.enabled:label=IMAGE_STREAMING,
    autopilot.enabled:label=AUTOPILOT
)"

# Export for analysis
gcloud container clusters list --format="csv(
    name,
    location,
    currentMasterVersion,
    releaseChannel.channel,
    status,
    autopilot.enabled
)" > cluster-inventory.csv
```

### 2. GKE Enterprise fleet visibility (if available)

If you have GKE Enterprise, use the fleet dashboard:
```bash
gcloud container fleet memberships list
```

### 3. Version skew analysis per cluster

Create this assessment script:
```bash
#!/bin/bash
# cluster-assessment.sh

for cluster in $(gcloud container clusters list --format="value(name,location)" | tr '\t' ':'); do
    name=$(echo $cluster | cut -d: -f1)
    location=$(echo $cluster | cut -d: -f2)
    
    echo "=== $name ($location) ==="
    
    # Basic info
    gcloud container clusters describe $name --location=$location \
        --format="value(
            currentMasterVersion,
            releaseChannel.channel,
            autopilot.enabled
        )"
    
    # Node pool versions
    gcloud container node-pools list --cluster=$name --location=$location \
        --format="table(name,version,status)"
    
    # Auto-upgrade status and EoS timeline
    gcloud container clusters get-upgrade-info $name --location=$location \
        --format="yaml(autoUpgradeStatus,endOfStandardSupportTimestamp)"
    
    echo ""
done
```

### 4. Deprecation insights (critical!)

```bash
# Check for deprecated API usage across all clusters
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=- \
    --project=PROJECT_ID \
    --format="table(name,category,description)"
```

This is the #1 upgrade blocker. GKE pauses auto-upgrades when deprecated APIs are detected.

## Categorize Your Fleet

Based on the assessment, group clusters into remediation tiers:

### Tier 1: Critical (immediate action)
- Versions approaching/past End of Support
- Clusters with deprecated API usage
- "No channel" clusters (lack modern upgrade controls)
- Broken auto-upgrade (stuck operations)

### Tier 2: Suboptimal (plan within 30 days)
- Version skew >1 minor between control plane and nodes
- Mixed channels in the same environment (dev/staging/prod)
- Clusters without maintenance windows
- Missing PDBs on critical workloads

### Tier 3: Standardization (plan within 90 days)
- Inconsistent node pool configurations
- Lack of proper resource requests (especially Autopilot)
- Suboptimal release channel selection for workload type

## Remediation Strategy

### Phase 1: Emergency stabilization (Week 1-2)

**Fix deprecated API usage first** — this unblocks auto-upgrades:
```bash
# Get specific deprecated API recommendations
gcloud recommender recommendations list \
    --recommender=google.container.DiagnosisRecommender \
    --location=LOCATION \
    --project=PROJECT_ID
```

**Migrate "No channel" clusters to release channels:**
```bash
# For conservative customers: Regular channel (closest to legacy behavior)
gcloud container clusters update CLUSTER_NAME \
    --location=LOCATION \
    --release-channel=regular

# For customers wanting max EoS flexibility: Extended channel
gcloud container clusters update CLUSTER_NAME \
    --location=LOCATION \
    --release-channel=extended
```

**Set maintenance windows immediately:**
```bash
# Conservative off-peak window (Saturday 2-6 AM)
gcloud container clusters update CLUSTER_NAME \
    --location=LOCATION \
    --maintenance-window-start="2024-01-06T02:00:00Z" \
    --maintenance-window-end="2024-01-06T06:00:00Z" \
    --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SA"
```

### Phase 2: Version alignment (Week 3-6)

**Strategy: Channel-based environment segregation**
- **Dev environments:** Regular channel (gets updates ~1 week after Rapid)
- **Staging:** Regular channel with "no minor" exclusion + manual minor upgrades
- **Prod:** Stable channel OR Regular with "no minor or node upgrades" exclusion

**Target state:** All environments on the same minor version, different channels for timing control.

**Use skip-level upgrades** where possible to reduce total upgrade time:
```bash
# Example: 1.28 → 1.30 (skip 1.29)
gcloud container node-pools upgrade NODE_POOL_NAME \
    --cluster=CLUSTER_NAME \
    --location=LOCATION \
    --cluster-version=1.30.x-gke.xxx
```

### Phase 3: Operational excellence (Week 7-12)

**Implement upgrade controls:**
```bash
# For production: "no minor or node upgrades" with manual promotion
gcloud container clusters update CLUSTER_NAME \
    --location=LOCATION \
    --add-maintenance-exclusion-name="prod-control" \
    --add-maintenance-exclusion-scope=no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

**Standardize node pool configurations:**
- Consistent machine types within environments
- Proper surge settings: `maxSurge=5%` (percentage-based), `maxUnavailable=0`
- PDBs on all critical workloads

## Self-Service Tools GKE Provides

### 1. GKE Insights & Recommendations
- **Deprecation insights:** Automatically detects deprecated API usage
- **Security insights:** Identifies security misconfigurations
- **Cost optimization:** Right-sizing recommendations

Access via Console or:
```bash
gcloud recommender insights list --recommender=google.container.Recommender
```

### 2. Upgrade Assist
- **Pre-upgrade validation:** Checks for upgrade blockers
- **Version compatibility matrix:** Shows available upgrade paths
- **Release notes integration:** Breaking changes between versions

### 3. Auto-upgrade status API
```bash
# Check what GKE plans to upgrade each cluster to
gcloud container clusters get-upgrade-info CLUSTER_NAME --location=LOCATION
```

### 4. Release schedule visibility
- Public [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule)
- Shows when versions become available in each channel
- ~2 week advance notice for auto-upgrade timing

### 5. Monitoring integration
- **Cloud Logging:** Structured upgrade events, PDB violations, EoS warnings
- **Cloud Monitoring:** Cluster health metrics, upgrade progress
- **Pub/Sub notifications:** Programmable upgrade event handling

### 6. Policy as Code (Config Connector)
```yaml
# Example: Enforce release channel via Config Connector
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerCluster
metadata:
  name: standardized-cluster
spec:
  releaseChannel:
    channel: REGULAR
  maintenancePolicy:
    recurringWindow:
      recurrence: "FREQ=WEEKLY;BYDAY=SA"
      window:
        startTime: "2024-01-06T02:00:00Z"
        endTime: "2024-01-06T06:00:00Z"
```

## Fleet Standardization Template

Here's your target state configuration:

### Standard Production Cluster
```bash
# Channel: Regular or Stable
# Maintenance: Saturday 2-6 AM
# Control: "no minor or node upgrades" exclusion
# Manual minor upgrades during planned windows

gcloud container clusters update CLUSTER_NAME \
    --location=LOCATION \
    --release-channel=regular \
    --maintenance-window-start="2024-01-06T02:00:00Z" \
    --maintenance-window-end="2024-01-06T06:00:00Z" \
    --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SA" \
    --add-maintenance-exclusion-name="prod-control" \
    --add-maintenance-exclusion-scope=no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

### Standard Node Pool Settings
```bash
gcloud container node-pools update NODE_POOL_NAME \
    --cluster=CLUSTER_NAME \
    --location=LOCATION \
    --max-surge-upgrade=2 \
    --max-unavailable-upgrade=0 \
    --enable-autoupgrade \
    --enable-autorepair
```

## Monitoring Your Progress

Set up these alerts to track remediation:
```bash
# Clusters approaching EoS
gcloud logging sinks create gke-eos-alerts \
    bigquery.googleapis.com/projects/PROJECT_ID/datasets/gke_logs \
    --log-filter='resource.type="gke_cluster" AND jsonPayload.message:"approaching end of support"'

# Failed upgrades
gcloud logging sinks create gke-upgrade-failures \
    bigquery.googleapis.com/projects/PROJECT_ID/datasets/gke_logs \
    --log-filter='resource.type="gke_cluster" AND jsonPayload.operationType="UPGRADE_NODES" AND jsonPayload.status="FAILED"'
```

## Key Success Metrics

Track these KPIs monthly:
- **% clusters on release channels** (target: 100%)
- **% clusters within 1 minor version of latest** (target: >90%)
- **Mean time between security patch release and fleet deployment** (target: <30 days)
- **% clusters with maintenance windows configured** (target: 100%)
- **% workloads with PDBs** (target: >95% for stateful, >80% for stateless)

The goal is transforming from reactive "firefighting" to proactive, predictable upgrade lifecycle management. GKE's auto-upgrade capabilities should handle 95% of your maintenance — you just control the timing and scope.