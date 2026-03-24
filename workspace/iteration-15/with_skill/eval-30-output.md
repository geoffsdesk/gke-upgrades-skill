# GKE Fleet Modernization Plan

You're right to prioritize this—inherited GKE fleets are often in rough shape. Here's a systematic approach to assess, plan, and execute fleet modernization using GKE's self-service tools.

## Assessment Phase: Inventory Your Fleet

### 1. Fleet Discovery and Current State

```bash
# Get all clusters across projects
gcloud projects list --format="value(projectId)" | while read project; do
  echo "=== Project: $project ==="
  gcloud container clusters list --project=$project --format="table(
    name,
    location,
    currentMasterVersion,
    releaseChannel.channel,
    nodePools[].version.list():label=NODE_VERSIONS,
    status
  )"
done > fleet-inventory.txt
```

### 2. Use GKE Fleet Management Dashboard

Navigate to **GKE > Fleets** in Cloud Console. This gives you:
- Cross-project cluster visibility
- Version distribution heatmaps
- Upgrade readiness scores
- Security posture overview

Register clusters in a fleet for centralized visibility:
```bash
gcloud container fleet memberships register CLUSTER_NAME \
  --gke-cluster=LOCATION/CLUSTER_NAME \
  --project=PROJECT_ID
```

### 3. Deprecation and Compliance Insights

Check **GKE > Recommendations** in Cloud Console for:
- End of Support warnings
- Deprecated API usage
- Version skew violations
- Security recommendations

Programmatically:
```bash
# Get deprecation insights across all clusters
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=LOCATION \
  --project=PROJECT_ID \
  --format="table(
    name.segment(-1):label=INSIGHT_ID,
    insightSubtype,
    targetResources[0].segment(-1):label=CLUSTER,
    severity,
    lastRefreshTime
  )"
```

### 4. Auto-Upgrade Status Check

For each cluster, understand what GKE will do automatically:
```bash
gcloud container clusters get-upgrade-info CLUSTER_NAME \
  --region REGION \
  --format="yaml(
    autoUpgradeStatus,
    endOfStandardSupportTimestamp,
    endOfExtendedSupportTimestamp,
    minorTargetVersion,
    patchTargetVersion
  )"
```

## Categorization: Triage Your Clusters

Group clusters by risk and complexity:

### **Critical/Production Clusters**
- Customer-facing workloads
- Stateful databases
- Revenue-impacting services
- **Strategy:** Move to Stable channel + maintenance exclusions for maximum control

### **Development/Test Clusters** 
- Non-production workloads
- CI/CD environments
- **Strategy:** Move to Regular channel, let them auto-upgrade to validate versions

### **Legacy/Zombie Clusters**
- No clear ownership
- Unused or abandoned
- **Strategy:** Evaluate for deletion first

### **Special Cases**
- GPU/AI workloads with long-running training
- Compliance-sensitive environments
- **Strategy:** Extended channel or tight maintenance exclusions

## Modernization Strategy by Cluster Type

### For "No Channel" Clusters (Priority #1)

"No channel" is legacy and lacks modern upgrade controls. Migrate these first:

```bash
# Migrate to Regular channel (closest to legacy behavior)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular

# For conservative customers needing maximum EoS flexibility
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

**Why migrate?** Only release channels support:
- "No minor or node upgrades" exclusions (the most powerful control)
- Persistent exclusions that track End of Support
- Extended support options (24 months)
- Rollout sequencing for multi-cluster coordination

### For Mixed-Version Node Pools

Clusters with nodes 2+ versions behind the control plane need immediate attention:

```bash
# Check version skew
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
  --format="table(
    currentMasterVersion:label=CONTROL_PLANE,
    nodePools[].name:label=POOL,
    nodePools[].version:label=NODE_VERSION
  )"

# Upgrade nodes using skip-level upgrades (faster)
# Example: 1.28 → 1.30 (skip 1.29)
gcloud container node-pools upgrade POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30.x-gke.xxxx
```

### Channel Selection Strategy

| Environment | Recommended Channel | Rationale |
|-------------|-------------------|-----------|
| **Development** | Regular | Good balance of stability and early access |
| **Staging** | Regular | Same as prod for version parity testing |
| **Production** | Stable or Regular | Stable for max stability, Regular for faster patches |
| **Compliance** | Extended | 24-month support, minimal forced upgrades |
| **AI/ML Training** | Stable + exclusions | Predictable, with manual control during training campaigns |

**Best Practice:** Keep dev and prod on the same channel or one channel apart, maintaining the same minor version.

## Self-Service Planning Tools

### 1. GKE Release Schedule
- **URL:** https://cloud.google.com/kubernetes-engine/docs/release-schedule
- **Use for:** Version availability predictions, End of Support dates, auto-upgrade timing
- **Key insight:** Shows best-case dates when versions will be available/auto-upgraded in each channel

### 2. Upgrade Assist Dashboard
- **Location:** GKE Console > Clusters > [Cluster Name] > Upgrade
- **Features:** Pre-upgrade compatibility checks, deprecated API detection, recommended upgrade paths
- **Use before:** Any manual upgrade to catch breaking changes

### 3. Fleet Insights and Recommendations
- **Location:** GKE Console > Fleets or Recommendations
- **Automated insights:** Version drift, security vulnerabilities, optimization opportunities
- **Actionable:** Direct links to fix issues

### 4. Cloud Asset Inventory Integration
Query your GKE assets programmatically:
```bash
# Get all clusters with version info across organization
gcloud asset search-all-resources \
  --scope=organizations/ORG_ID \
  --asset-types=container.googleapis.com/Cluster \
  --format="table(
    name.segment(-1):label=CLUSTER,
    location.segment(-1):label=LOCATION,
    additionalAttributes.currentMasterVersion:label=VERSION,
    additionalAttributes.releaseChannel.channel:label=CHANNEL
  )"
```

## Implementation Roadmap

### Phase 1: Stabilize (Weeks 1-2)
- [ ] Migrate all "No channel" clusters to Regular channel
- [ ] Fix critical version skew (nodes 3+ versions behind control plane)
- [ ] Set up maintenance windows for production clusters
- [ ] Apply "no upgrades" exclusions to freeze state during assessment

### Phase 2: Standardize (Weeks 3-4)
- [ ] Establish channel strategy per environment tier
- [ ] Configure maintenance exclusions for production workloads
- [ ] Set up monitoring for upgrade events (Cloud Logging + Pub/Sub)
- [ ] Document cluster ownership and upgrade contacts

### Phase 3: Automate (Weeks 5-8)
- [ ] Enable auto-upgrades with proper controls (maintenance windows + exclusions)
- [ ] Set up rollout sequencing for multi-cluster environments
- [ ] Configure scheduled upgrade notifications (72h advance notice)
- [ ] Create runbooks for manual intervention scenarios

### Phase 4: Optimize (Ongoing)
- [ ] Regular fleet health reviews using GKE insights
- [ ] Deprecation debt management (quarterly API usage audits)
- [ ] Performance baseline monitoring post-upgrades
- [ ] Cost optimization through version standardization

## Fleet Health Monitoring Setup

### Essential Alerts
```bash
# Set up Pub/Sub for GKE upgrade events
gcloud pubsub topics create gke-upgrade-events

# Configure Cloud Logging sink
gcloud logging sinks create gke-upgrade-sink \
  pubsub.googleapis.com/projects/PROJECT_ID/topics/gke-upgrade-events \
  --log-filter='resource.type="gke_cluster" AND 
               (protoPayload.metadata.operationType="UPDATE_CLUSTER" OR 
                protoPayload.metadata.operationType="UPGRADE_MASTER" OR
                protoPayload.metadata.operationType="UPGRADE_NODES")'
```

### Fleet Health Dashboard Queries
```bash
# Weekly fleet health report
gcloud container clusters list --format="csv[no-heading](
  name,
  location,
  currentMasterVersion,
  releaseChannel.channel,
  nodePools[0].version,
  status
)" > weekly-fleet-report.csv
```

## Red Flags to Address Immediately

1. **Clusters on End of Support versions** → Force-upgraded by GKE soon
2. **Node pools 3+ minor versions behind** → Risk of upgrade failures
3. **No maintenance windows configured** → Upgrades happen at unpredictable times
4. **Stateful workloads without PDBs** → Risk of data loss during upgrades
5. **Admission webhooks without failsafes** → Can block all pod creation post-upgrade
6. **GPU clusters with no upgrade strategy** → Expensive upgrade failures

## Success Metrics

Track these KPIs monthly:
- **Version currency:** % of clusters within 1 minor version of latest
- **Channel compliance:** % of clusters on appropriate channels for their tier
- **Upgrade success rate:** % of upgrades completing without manual intervention  
- **Deprecation debt:** Count of clusters using deprecated APIs
- **Mean time to upgrade:** Average time from version availability to deployment

This systematic approach will transform your chaotic fleet into a well-managed, automatically upgrading infrastructure that stays current with minimal operational overhead.