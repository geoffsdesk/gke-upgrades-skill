# GKE Fleet Health Assessment & Remediation Plan

You've inherited a classic "snowflake fleet" — clusters with manually frozen versions that deviate from GKE's automated lifecycle. Here's a systematic approach to assess and remediate using GKE's built-in tooling.

## Phase 1: Fleet Discovery & Assessment

### GKE Fleet Inventory Dashboard
Start with GKE's built-in fleet overview to get the big picture:

```bash
# List all clusters across projects/regions
gcloud container clusters list --format="table(
  name,
  location,
  currentMasterVersion,
  releaseChannel.channel,
  status,
  autopilot.enabled
)"

# For multi-project environments
for project in PROJECT1 PROJECT2 PROJECT3; do
  gcloud container clusters list --project=$project
done
```

**GKE Console Fleet View:** Navigate to GKE → Clusters in the Cloud Console. The main dashboard shows:
- Version distribution across your fleet
- Clusters approaching End of Support (EoS)
- Release channel adoption
- Security posture summary

### GKE Deprecation Insights (Critical)
GKE's recommender automatically scans for deprecated API usage — the #1 cause of upgrade failures:

```bash
# Check for deprecated APIs across all clusters
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=LOCATION \
  --project=PROJECT_ID \
  --filter="category.category:RELIABILITY"

# Look for these specific insight subtypes:
# - DEPRECATED_API_USAGE
# - VERSION_END_OF_SUPPORT
# - PDB_UNPERMISSIVE
```

**Console Access:** GKE Console → Select cluster → Insights tab shows deprecation warnings, API usage, and upgrade blockers.

### Version Support Timeline
Use GKE's release schedule to understand your EoS risk:

```bash
# Check auto-upgrade status per cluster
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Shows:
# - autoUpgradeStatus
# - endOfStandardSupportTimestamp  
# - endOfExtendedSupportTimestamp
# - Current auto-upgrade target versions
```

**Key Resource:** [GKE Release Schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) shows EoS dates and version availability per channel.

## Phase 2: Risk Prioritization Matrix

Categorize clusters by risk level to prioritize remediation:

| Risk Level | Criteria | Action Priority |
|------------|----------|-----------------|
| **CRITICAL** | Version at/past EoS, "No channel", deprecated APIs | Immediate (within 30 days) |
| **HIGH** | Version 2+ minors behind, unpermissive PDBs, missing resource requests | Next sprint |
| **MEDIUM** | Version 1 minor behind, suboptimal channel | Next quarter |
| **LOW** | Current version, proper channel, no deprecated APIs | Monitor only |

```bash
# Generate risk report per cluster
echo "Cluster,Version,Channel,EoS_Risk,Deprecated_APIs"
for cluster in $(gcloud container clusters list --format="value(name)"); do
  version=$(gcloud container clusters describe $cluster --format="value(currentMasterVersion)")
  channel=$(gcloud container clusters describe $cluster --format="value(releaseChannel.channel)")
  # Check against current supported versions
  echo "$cluster,$version,$channel,CHECK_MANUALLY,CHECK_INSIGHTS"
done
```

## Phase 3: Self-Service Assessment Tools

### GKE Cluster Health Checker
Run automated health checks using GKE's built-in diagnostics:

```bash
# Check cluster upgrade readiness
gcloud container clusters describe CLUSTER_NAME \
  --format="yaml(addonsConfig,databaseEncryption,networkConfig,nodeConfig)"

# Verify workload health prerequisites  
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
kubectl get pdb -A -o custom-columns=NAME:.metadata.name,NAMESPACE:.metadata.namespace,MIN_AVAILABLE:.spec.minAvailable,ALLOWED_DISRUPTIONS:.status.disruptionsAllowed
```

### Resource Request Analysis (Critical for Autopilot)
Many inherited clusters lack proper resource requests — mandatory for Autopilot migration:

```bash
# Find pods without resource requests
kubectl get pods -A -o json | jq -r '
  .items[] | 
  select(.spec.containers[].resources.requests.cpu == null or .spec.containers[].resources.requests.memory == null) | 
  "\(.metadata.namespace)/\(.metadata.name)"'

# GKE recommender also flags this
gcloud recommender recommendations list \
  --recommender=google.container.DiagnosisRecommender \
  --location=LOCATION
```

### Networking & Security Assessment
```bash
# Check for legacy networking
gcloud container clusters describe CLUSTER_NAME \
  --format="value(networkConfig.network,ipAllocationPolicy.useIpAliases)"

# Private cluster status
gcloud container clusters describe CLUSTER_NAME \
  --format="value(privateClusterConfig.enablePrivateNodes)"

# Workload Identity usage
kubectl get serviceaccounts -A -o json | \
  jq '.items[] | select(.metadata.annotations."iam.gke.io/gcp-service-account") | {ns:.metadata.namespace,name:.metadata.name}'
```

## Phase 4: Standardized Target Architecture

Define your fleet's target state. Recommended standard configuration:

### Release Channel Strategy
- **Dev/Test clusters:** Regular channel (balanced updates, full SLA)
- **Production clusters:** Stable or Extended channel (maximum stability)
- **Never use:** "No channel" (legacy, missing key features)

### Maintenance Control Pattern
```bash
# Standard production cluster configuration
gcloud container clusters update CLUSTER_NAME \
  --release-channel stable \
  --maintenance-window-start "2026-01-04T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

This gives you:
- Patches auto-applied weekly during Saturday 2-6 AM window
- Minor version upgrades blocked until you manually trigger them
- Up to 24 months support with Extended channel (cost only during extended period)

### Multi-Cluster Rollout Sequencing
For mature teams with 5+ clusters:

```bash
# Configure fleet-based rollout sequencing
gcloud container fleet clusterupgrade update \
  --upstream-fleet=dev-project-fleet \
  --default-upgrade-soaking=7d \
  --project=prod-project
```

## Phase 5: Migration Execution Plan

### Legacy "No Channel" Clusters (Highest Priority)
```bash
# Migration path: No channel → Regular/Stable
# Check version availability first
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels)"

# Add temporary exclusion before channel switch
gcloud container clusters update CLUSTER_NAME \
  --add-maintenance-exclusion-scope no_upgrades \
  --add-maintenance-exclusion-start-time NOW \
  --add-maintenance-exclusion-end-time +7d

# Migrate to release channel
gcloud container clusters update CLUSTER_NAME \
  --release-channel regular

# Remove temporary exclusion, add long-term control
gcloud container clusters update CLUSTER_NAME \
  --remove-maintenance-exclusion-name TEMP_EXCLUSION \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

### Version Remediation Sequence
For clusters multiple versions behind:

1. **Control plane first** (required order): N → N+1 → N+2 (sequential minors)
2. **Node pools second**: Can jump 2 minor versions (N → N+2) if CP already at target
3. **Fix deprecated APIs between each minor upgrade**

```bash
# Example: 1.28 → 1.31 path
# Step 1: CP 1.28 → 1.29
gcloud container clusters upgrade CLUSTER_NAME \
  --master \
  --cluster-version 1.29.X-gke.XXX

# Step 2: CP 1.29 → 1.30  
gcloud container clusters upgrade CLUSTER_NAME \
  --master \
  --cluster-version 1.30.X-gke.XXX

# Step 3: CP 1.30 → 1.31
gcloud container clusters upgrade CLUSTER_NAME \
  --master \
  --cluster-version 1.31.X-gke.XXX

# Step 4: Node pools 1.28 → 1.31 (skip-level upgrade)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --cluster-version 1.31.X-gke.XXX
```

## Phase 6: Ongoing Fleet Management

### Monitoring & Alerting Setup
```bash
# Enable scheduled upgrade notifications (72h advance warning)
gcloud container clusters update CLUSTER_NAME \
  --enable-scheduled-upgrades

# Set up Cloud Monitoring alerts for EoS warnings
# Filter: resource.type="gke_cluster" AND jsonPayload.reason="EndOfSupportApproaching"
```

### Fleet Health Dashboard
Create a monitoring dashboard tracking:
- Version distribution across fleet
- Time since last upgrade per cluster  
- Active maintenance exclusions
- Deprecated API usage count
- EoS timeline per cluster

### Standardized Runbooks
Document these standard operations:
- Emergency patch application (30-day "no upgrades" exclusion → manual upgrade)
- Quarterly minor version progression (dev → prod sequencing)
- Incident response for stuck upgrades
- New cluster provisioning with standard configuration

## Phase 7: Governance & Prevention

### Policy Enforcement
```bash
# Organization policy to require release channels
# Resource: //container.googleapis.com/projects/PROJECT/zones/ZONE/clusters/CLUSTER
# Constraint: constraints/container.enableReleaseChannels
```

### Standard Cluster Templates
Create Terraform modules or Config Connector templates with:
- Mandatory release channel enrollment
- Standard maintenance windows
- Proper networking (VPC-native, private nodes)
- Security defaults (Workload Identity, Binary Authorization)
- Resource requests on all containers

### Team Training Checklist
- [ ] GKE auto-upgrade model training (channels + windows + exclusions)
- [ ] Deprecated API detection and remediation
- [ ] Incident response for stuck upgrades
- [ ] Release schedule and EoS planning
- [ ] Multi-cluster upgrade sequencing

## Key Success Metrics

Track these KPIs for fleet health:
- **% clusters on release channels** (target: 100%)
- **% clusters within 1 minor version of latest** (target: >80%)
- **Mean time to patch** (target: <30 days)
- **Deprecated API violations** (target: 0)
- **Failed auto-upgrades** (target: <5% per quarter)

## Timeline Estimate

**Month 1:** Assessment and critical EoS remediation
**Month 2-3:** Legacy "No channel" migration and deprecated API fixes  
**Month 4-6:** Version standardization and maintenance window setup
**Month 7+:** Steady state with automated lifecycle management

**Warning about the snowflake anti-pattern:** Every manually frozen cluster is a "snowflake" that accumulates technical debt. The longer clusters stay frozen, the harder eventual upgrades become — deprecated APIs pile up, version skew grows, and the blast radius of forced EoS upgrades increases. Your goal is to eliminate snowflakes entirely and return to GKE's automated lifecycle with appropriate timing and scope controls.

This plan transforms your chaotic inherited fleet into a well-governed, automatically maintained environment using GKE's native tooling. The key is systematic assessment → risk-based prioritization → standardized remediation → ongoing governance.