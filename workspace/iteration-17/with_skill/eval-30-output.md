# GKE Fleet Health Assessment & Modernization Plan

You've inherited a classic "fleet sprawl" situation. Let's get your clusters into a healthy, standardized state using GKE's built-in assessment tools and a phased modernization approach.

## Phase 1: Fleet Discovery & Assessment (Week 1-2)

### Inventory your fleet with GKE's built-in tools

**1. Fleet-wide cluster inventory:**
```bash
# Get all clusters across projects and regions
gcloud container clusters list --format="table(
  name,
  location,
  currentMasterVersion,
  releaseChannel.channel:label=CHANNEL,
  status,
  nodeConfig.machineType:label=MACHINE_TYPE,
  currentNodeCount
)" --sort-by="releaseChannel.channel,currentMasterVersion"

# Export to CSV for analysis
gcloud container clusters list --format="csv(
  name,
  location,
  currentMasterVersion,
  releaseChannel.channel,
  status,
  currentNodeCount,
  nodeConfig.machineType
)" > fleet-inventory.csv
```

**2. Use GKE's Deprecation Insights Dashboard:**
- In Google Cloud Console → Kubernetes Engine → Insights tab
- Shows deprecated API usage, EoS versions, version skew issues across your fleet
- Programmatic access: `gcloud recommender insights list --insight-type=google.container.DiagnosisInsight --location=LOCATION`

**3. Check upgrade readiness per cluster:**
```bash
# For each cluster, check auto-upgrade status and EoS timeline
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION --format="yaml"
```

**4. Identify version skew and EoS risk:**
```bash
# Get detailed version info for each cluster
for cluster in $(gcloud container clusters list --format="value(name,location)"); do
  name=$(echo $cluster | cut -d$'\t' -f1)
  location=$(echo $cluster | cut -d$'\t' -f2)
  echo "=== $name ($location) ==="
  gcloud container clusters describe $name --region $location \
    --format="table(currentMasterVersion,nodePools[].version,releaseChannel.channel)"
done
```

### Risk assessment categories

Based on your inventory, categorize clusters:

**🔴 CRITICAL (fix first):**
- "No channel" clusters on versions ≤1.29 (systematic EoS enforcement completed)
- Any cluster with node pools 3+ minor versions behind control plane
- Clusters showing deprecated API usage in insights dashboard

**🟡 HIGH RISK:**
- "No channel" clusters on versions 1.30+ (subject to future EoS enforcement)
- Release channel clusters with versions approaching EoS (check [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule))
- Mixed-version node pools within same cluster

**🟢 MEDIUM RISK:**
- Release channel clusters on current/recent versions but inconsistent channels across environments
- Clusters without maintenance windows configured

## Phase 2: Immediate Stabilization (Week 2-4)

### Standardize on release channels first

**For "No channel" clusters (highest priority):**

1. **Migrate to Regular channel** (closest to legacy "No channel" behavior):
```bash
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel regular
```

2. **Or migrate to Extended channel** if you need maximum control over EoS enforcement:
```bash
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel extended
```

**⚠️ Migration warning:** If your current version isn't available in the target channel yet, your cluster will be "ahead of channel" and won't receive auto-upgrades until the channel catches up. Check version availability first:
```bash
gcloud container get-server-config --region REGION --format="yaml(channels)"
```

### Configure maintenance controls

**Apply consistent maintenance windows across your fleet:**
```bash
# Standard maintenance window (Saturday 2-6 AM)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-window-start "2025-02-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Add conservative maintenance exclusions while you stabilize:**
```bash
# "No minor or node upgrades" - allows CP security patches, blocks disruptive changes
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

This gives you control while still receiving critical security patches on the control plane.

## Phase 3: Version Convergence (Week 4-8)

### Establish target state architecture

**Recommended fleet topology:**
```
Development:     Regular channel, auto-upgrades enabled
Staging:         Regular channel, "no minor" exclusion + manual triggers  
Production:      Stable channel, "no minor or node" exclusion + manual triggers
```

**Or for maximum control:**
```
Development:     Regular channel, auto-upgrades enabled
Staging:         Extended channel, "no minor or node" exclusion + manual triggers
Production:      Extended channel, "no minor or node" exclusion + manual triggers
```

### Version convergence strategy

**Step 1: Control plane convergence**
- Upgrade all control planes to the same minor version sequentially (e.g., 1.31→1.32→1.33)
- Use two-step minor upgrades for production (rollback-safe):
```bash
gcloud beta container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version TARGET_VERSION \
  --control-plane-soak-duration 24h
```

**Step 2: Node pool skip-level upgrades**
- Skip-level upgrade node pools within 2-version skew limit (saves time)
- Example: CP at 1.33, upgrade nodes 1.31→1.33 in single jump:
```bash
gcloud container node-pools upgrade POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.33.x-gke.xxxx
```

### GKE Fleet Management for large-scale operations

If you have 10+ clusters, consider **GKE Fleet Management** for centralized operations:

```bash
# Register clusters to a fleet
gcloud container fleet memberships register CLUSTER_NAME \
  --gke-cluster LOCATION/CLUSTER_NAME \
  --enable-workload-identity

# View fleet-wide status
gcloud container fleet memberships list
```

Fleet benefits:
- Centralized fleet dashboard showing all cluster versions, health
- Fleet-wide policy management  
- Rollout sequencing for coordinated upgrades across environments

## Phase 4: Operational Excellence (Week 8+)

### Self-service monitoring and alerting

**1. Set up GKE cluster notifications:**
```bash
# Enable cluster event notifications via Pub/Sub
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --enable-network-policy \
  --notification-config=pubsub=projects/PROJECT_ID/topics/gke-cluster-events
```

**2. Configure scheduled upgrade notifications (72h advance warning):**
```bash
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --send-scheduled-upgrade-notifications
```

**3. Monitor via Cloud Logging queries:**
```sql
-- EoS warnings and upgrade events
resource.type="gke_cluster"
protoPayload.metadata.operationType=~"(UPDATE_CLUSTER|UPGRADE_MASTER)"

-- PDB violation events during upgrades  
resource.type="gke_cluster"
jsonPayload.reason="EvictionBlocked"
```

### Standardized upgrade procedures

**Create standardized runbooks for each environment:**

```bash
# Development (auto-upgrades enabled)
gcloud container clusters update DEV_CLUSTER \
  --region REGION \
  --release-channel regular
  # No exclusions - gets updates automatically

# Staging (manual minor upgrades)  
gcloud container clusters update STAGING_CLUSTER \
  --region REGION \
  --release-channel regular \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Production (maximum control)
gcloud container clusters update PROD_CLUSTER \
  --region REGION \
  --release-channel stable \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Self-Service Assessment Tools Summary

**GKE provides these built-in tools for fleet management:**

| Tool | Purpose | Access Method |
|------|---------|---------------|
| **Deprecation Insights Dashboard** | Find deprecated APIs, EoS versions, skew issues | Console → GKE → Insights tab |
| **Upgrade Info API** | Check auto-upgrade targets, EoS dates | `gcloud container clusters get-upgrade-info` |
| **Release Schedule** | Plan upgrade timing | [GKE release schedule page](https://cloud.google.com/kubernetes-engine/docs/release-schedule) |
| **Fleet Management Dashboard** | Multi-cluster overview | Console → GKE → Fleets (after registration) |
| **Cluster Event Notifications** | Real-time upgrade/maintenance events | Pub/Sub + Cloud Logging |
| **GKE Recommender** | Version skew, deprecated API programmatic access | `gcloud recommender insights list` |

## Success Metrics

Track these KPIs as you modernize:

- **Version drift:** % of clusters within 1 minor version of latest
- **Channel adoption:** % of clusters on release channels (target: 100%)
- **EoS risk:** # of clusters within 30 days of End of Support (target: 0)
- **Maintenance window coverage:** % of clusters with configured windows
- **Deprecated API usage:** # of insights flagging deprecated APIs (target: 0)

**Timeline expectations:**
- **Week 1-2:** Complete assessment, identify critical risks
- **Week 2-4:** Migrate all "No channel" clusters to release channels  
- **Week 4-8:** Converge versions, standardize maintenance policies
- **Week 8+:** Ongoing operational excellence with standardized procedures

This plan transforms your inherited "fleet sprawl" into a well-managed, standardized GKE environment using GKE's native tools and best practices. The key is starting with assessment and risk prioritization, then systematically standardizing on release channels and maintenance policies.