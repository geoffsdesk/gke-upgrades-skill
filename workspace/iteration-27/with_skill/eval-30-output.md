# GKE Fleet Health Assessment & Remediation Plan

You've inherited a classic "snowflake fleet" — clusters with frozen versions that have diverged from standard lifecycle management. Here's how to systematically assess and remediate your fleet using GKE's self-service tools.

## Phase 1: Fleet Discovery & Assessment

### Discovery Tools

**1. Fleet-wide cluster inventory:**
```bash
# List all clusters across projects/regions
gcloud container clusters list --format="table(
  name,
  location,
  currentMasterVersion,
  releaseChannel.channel:label=CHANNEL,
  status
)" --flatten="nodePools[]" --project PROJECT_ID

# For multi-project discovery
for project in $(gcloud projects list --format="value(projectId)"); do
  echo "=== Project: $project ==="
  gcloud container clusters list --project=$project --format="table(name,location,currentMasterVersion,releaseChannel.channel)"
done
```

**2. GKE Recommender for fleet-wide insights:**
```bash
# Get all deprecation and compatibility insights across projects
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=- \
  --project=PROJECT_ID \
  --filter="category.category:RELIABILITY"

# Specific insight types to check:
# - Deprecated API usage
# - Version compatibility issues
# - End of Support warnings
# - Unpermissive PDBs
```

**3. Version analysis script:**
```bash
#!/bin/bash
# Create a fleet health report
echo "Cluster,Project,Zone,CP_Version,Channel,Node_Versions,EoS_Risk,Action_Needed" > fleet-health.csv

for cluster in $(gcloud container clusters list --format="value(name,location)" --flatten="locations[]"); do
  cluster_name=$(echo $cluster | cut -d' ' -f1)
  location=$(echo $cluster | cut -d' ' -f2)
  
  # Get cluster details
  cluster_info=$(gcloud container clusters describe $cluster_name --location=$location --format="value(
    currentMasterVersion,
    releaseChannel.channel,
    endOfStandardSupportTimestamp
  )")
  
  # Get node versions
  node_versions=$(gcloud container node-pools list --cluster=$cluster_name --location=$location --format="value(version)" | sort -u | tr '\n' ';')
  
  echo "$cluster_name,$PROJECT_ID,$location,$cluster_info,$node_versions" >> fleet-health.csv
done
```

### Assessment Dashboard

**4. GKE Console fleet view:**
- Navigate to GKE → Clusters in Google Cloud Console
- Enable the "Insights" tab for deprecation warnings
- Use the filter bar to find clusters by channel, version, or status
- Look for clusters with warning/error badges

**5. Programmatic assessment:**
```bash
# Check upgrade-info for all clusters
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION --format="yaml(
  autoUpgradeStatus,
  endOfStandardSupportTimestamp,
  endOfExtendedSupportTimestamp,
  minorTargetVersion,
  patchTargetVersion
)"
```

## Phase 2: Risk Classification

Classify your clusters into risk tiers based on this assessment:

### 🔴 **Critical Risk (Fix Immediately)**
- Versions at or near End of Support
- Deprecated API usage detected
- "No channel" clusters with auto-upgrade disabled
- Node pools >2 minor versions behind control plane

### 🟡 **Medium Risk (Fix Within 30 Days)**
- "No channel" clusters with auto-upgrade enabled
- Clusters 2+ minor versions behind current stable
- Mixed node pool versions within same cluster
- No maintenance windows configured

### 🟢 **Low Risk (Standardize During Next Maintenance)**
- Release channel clusters with proper exclusions
- Recent versions but inconsistent channels across environments
- Missing PDBs or monitoring

## Phase 3: Remediation Strategy

### Migration Path: "No Channel" → Release Channels

**For production clusters (prioritize stability):**
```bash
# Option 1: Migrate to Extended channel (maximum control)
gcloud container clusters update CLUSTER_NAME \
  --location LOCATION \
  --release-channel extended

# Add persistent exclusion for maximum control
gcloud container clusters update CLUSTER_NAME \
  --location LOCATION \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**For dev/staging clusters:**
```bash
# Migrate to Regular channel (balanced approach)
gcloud container clusters update CLUSTER_NAME \
  --location LOCATION \
  --release-channel regular
```

**Migration checklist per cluster:**
- [ ] Check current version availability in target channel
- [ ] Apply temporary "no upgrades" exclusion during migration
- [ ] Test auto-upgrade behavior in dev first
- [ ] Configure maintenance windows aligned with operations schedule

### Version Remediation Priority

**1. Emergency upgrades (EoS clusters):**
```bash
# For clusters approaching/at EoS, upgrade immediately
gcloud container clusters upgrade CLUSTER_NAME \
  --location LOCATION \
  --cluster-version TARGET_VERSION
```

**2. Batch upgrade strategy:**
Group clusters by environment and upgrade in sequence:
- Dev/staging first (validate new versions)
- Canary production (small subset)
- Full production rollout

**3. Node pool consolidation:**
```bash
# For clusters with mixed node pool versions, standardize
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --location LOCATION \
  --cluster-version CONTROL_PLANE_VERSION
```

## Phase 4: Fleet Standardization

### Standard Configuration Template

Apply this configuration to all migrated clusters:

```bash
# Standard production cluster config
gcloud container clusters update CLUSTER_NAME \
  --location LOCATION \
  --release-channel extended \
  --maintenance-window-start "2024-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --enable-scheduled-upgrades
```

**Standard maintenance strategy:**
- **Extended channel** for production (24-month support, manual minor upgrades)
- **Regular channel** for dev/staging (automatic minor upgrades for early testing)
- **Saturday 2-6 AM maintenance windows** (off-peak)
- **"No minor or node upgrades" exclusions** for production (CP patches only)
- **Scheduled upgrade notifications enabled** (72h advance warning)

### Fleet Governance Tools

**1. Rollout sequencing for coordinated upgrades:**
```bash
# Configure fleet hierarchy: dev → staging → prod
gcloud container fleet clusterupgrade update \
  --project=PROJECT_ID \
  --upstream-fleet=dev-fleet-project \
  --default-upgrade-soaking=7d
```

**2. Monitoring and alerting:**
```bash
# Subscribe to cluster notifications
gcloud pubsub topics create gke-cluster-notifications
gcloud container clusters update CLUSTER_NAME \
  --location LOCATION \
  --enable-cluster-notifications \
  --notification-config pubsub-topic=projects/PROJECT_ID/topics/gke-cluster-notifications
```

**3. Policy enforcement with Config Connector:**
```yaml
# Enforce release channel enrollment
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerCluster
metadata:
  name: example-cluster
spec:
  releaseChannel:
    channel: "EXTENDED"
  maintenancePolicy:
    window:
      dailyMaintenanceWindow:
        startTime: "02:00"
```

## Phase 5: Operational Excellence

### Ongoing Fleet Management

**1. Regular health checks (monthly):**
```bash
# Check for new insights and deprecations
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=- \
  --project=PROJECT_ID

# Monitor EoS timeline
for cluster in $(gcloud container clusters list --format="value(name,location)"); do
  gcloud container clusters get-upgrade-info $(echo $cluster | tr ' ' ' --location ')
done
```

**2. Version drift monitoring:**
```bash
# Alert on version skew across environments
# Dev should not lag more than 1 minor version behind prod
```

**3. Automated remediation with Cloud Build:**
```yaml
# Trigger upgrades based on schedule or drift detection
steps:
- name: 'gcr.io/cloud-builders/gcloud'
  script: |
    # Check if dev cluster needs upgrade
    # Trigger staging upgrade after dev validation
    # Notify team of prod upgrade availability
```

## Self-Service Tools Summary

| Tool | Purpose | Command/Access |
|------|---------|----------------|
| **GKE Recommender** | Deprecated APIs, version insights | `gcloud recommender insights list` |
| **Upgrade Info API** | EoS dates, auto-upgrade status | `gcloud container clusters get-upgrade-info` |
| **Release Schedule** | Version availability timeline | [GKE Release Schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) |
| **Console Insights** | Visual fleet health dashboard | GKE → Clusters → Insights tab |
| **Cluster Notifications** | Proactive upgrade alerts | Pub/Sub integration |
| **Fleet Management** | Multi-cluster coordination | `gcloud container fleet` commands |

## Implementation Timeline

**Week 1-2: Assessment**
- [ ] Run fleet discovery across all projects
- [ ] Generate health report with risk classification
- [ ] Identify critical EoS clusters for immediate upgrade

**Week 3-4: Emergency Remediation**
- [ ] Upgrade all EoS clusters
- [ ] Fix deprecated API usage
- [ ] Migrate highest-risk "No channel" clusters

**Week 5-8: Standardization**
- [ ] Migrate remaining clusters to release channels
- [ ] Configure maintenance windows and exclusions
- [ ] Set up rollout sequencing for coordinated upgrades

**Week 9-12: Governance**
- [ ] Implement monitoring and alerting
- [ ] Document standard procedures
- [ ] Train team on new operational model

**Ongoing: Maintenance**
- [ ] Monthly fleet health reviews
- [ ] Quarterly channel/strategy reviews
- [ ] Automated drift detection and remediation

This systematic approach transforms your chaotic fleet into a well-managed, predictable upgrade lifecycle. The key is starting with assessment tools, prioritizing by risk, and standardizing on release channels with appropriate controls rather than trying to manually manage each cluster individually.