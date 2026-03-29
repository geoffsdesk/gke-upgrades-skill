# GKE Fleet Recovery Plan

You've inherited a classic "snowflake fleet" scenario. Here's a systematic approach to get your clusters into a healthy, well-managed state using GKE's self-service tools.

## Phase 1: Fleet Discovery & Assessment

### 1. Inventory your clusters

```bash
# Get all clusters across projects/regions
gcloud container clusters list --format="table(
  name,
  location,
  currentMasterVersion,
  releaseChannel.channel,
  status,
  nodePools[0].version:label=NODE_VERSION
)" --sort-by="currentMasterVersion"

# Export to CSV for analysis
gcloud container clusters list --format="csv(
  name,
  location,
  currentMasterVersion,
  releaseChannel.channel,
  status,
  nodePools[].version
)" > cluster-inventory.csv
```

### 2. Use GKE's deprecation insights dashboard

**In Google Cloud Console:**
- Navigate to GKE → Insights & Recommendations
- Filter by insight type: "Deprecations and Issues"
- Export the list of deprecated API usage, EoS versions, and version skew issues

**Or programmatically:**
```bash
# Get deprecation insights for all clusters
for PROJECT in $(gcloud projects list --format="value(projectId)"); do
  echo "=== Project: $PROJECT ==="
  gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=global \
    --project=$PROJECT \
    --format="table(name.basename(),insightSubtype,targetResources[0].basename())"
done
```

### 3. Check EoS status and upgrade targets

```bash
# For each cluster, get upgrade info
for CLUSTER in $(gcloud container clusters list --format="value(name,location)"); do
  CLUSTER_NAME=$(echo $CLUSTER | cut -d$'\t' -f1)
  LOCATION=$(echo $CLUSTER | cut -d$'\t' -f2)
  
  echo "=== $CLUSTER_NAME ($LOCATION) ==="
  gcloud container clusters get-upgrade-info $CLUSTER_NAME \
    --region=$LOCATION \
    --format="yaml(
      autoUpgradeStatus,
      endOfStandardSupportTimestamp,
      endOfExtendedSupportTimestamp,
      minorTargetVersion,
      patchTargetVersion
    )"
done
```

### 4. Assess workload readiness

```bash
# Check for deprecated API usage across clusters
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Find bare pods (won't survive upgrades)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Check for missing resource requests (breaks Autopilot)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.spec.containers[].resources.requests == null) | "\(.metadata.namespace)/\(.metadata.name)"'
```

## Phase 2: Prioritization & Triage

### Risk-based prioritization matrix

**Critical (fix immediately):**
- Clusters at End of Support (force-upgrade imminent)
- Deprecated API usage blocking auto-upgrades
- Production clusters on "No channel" (limited upgrade controls)

**High (fix within 30 days):**
- Clusters 2+ minor versions behind current
- GPU/TPU clusters on unsupported driver versions
- Clusters with >3 minor version node skew

**Medium (fix within 90 days):**
- Dev/test clusters on "No channel"
- Mixed channel strategies preventing rollout sequencing
- Clusters missing PDBs for stateful workloads

### Fleet standardization targets

Based on your environment, establish targets:

```
Standard Configuration:
- Channel: Regular (prod), Rapid (dev/staging)
- Maintenance windows: Aligned with business off-peak hours
- Upgrade controls: "No minor or node upgrades" exclusion for prod (allows CP patches, manual minor control)
- Node pools: Consistent machine types, surge settings
- Workloads: PDBs configured, no bare pods, resource requests set
```

## Phase 3: Migration Strategy

### 1. Legacy "No channel" → Release channel migration

**For production clusters (safest path to Regular/Stable):**
```bash
# Step 1: Add temporary "no upgrades" exclusion before switching
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-start-time $(date -u -d "now" +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d "+30 days" +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades

# Step 2: Switch to release channel
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular

# Step 3: Remove temporary exclusion, add permanent minor control
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-name "minor-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Version compatibility warning:** Check if your current version is available in the target channel using the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule). If not, your cluster will be "ahead of channel" and won't receive auto-upgrades until the channel catches up.

### 2. Channel standardization across environments

**Recommended pattern:**
- **Dev/Staging:** Rapid channel (early access to features/fixes)
- **Production:** Regular channel (balanced stability + timeliness)
- **Mission-critical:** Stable or Extended channel (maximum validation)

**Important:** All environments should be within 1 channel apart and on the same minor version to enable proper testing flow and rollout sequencing.

### 3. Maintenance control standardization

```bash
# Production clusters - maximum control, security patches only
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --maintenance-window-start "2026-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Dev/staging clusters - patches + node auto-upgrades, manual minor control
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --maintenance-window-start "2026-01-01T03:00:00Z" \
  --maintenance-window-duration 3h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Phase 4: Workload Remediation

### 1. Fix deprecated API usage

```bash
# Use GKE's API deprecation checker
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Common fixes for deprecated APIs:
# - extensions/v1beta1 Ingress → networking.k8s.io/v1
# - policy/v1beta1 PodSecurityPolicy → use Pod Security Standards
# - v1beta1 CronJob → batch/v1
```

### 2. Add missing PDBs for stateful workloads

```bash
# Template for database workloads
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: postgres-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: postgres
EOF
```

### 3. Convert bare pods to managed workloads

```bash
# Find bare pods
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Convert to Deployment (example)
kubectl create deployment NAME --image=IMAGE --replicas=1 --dry-run=client -o yaml > deployment.yaml
```

## Phase 5: Automation & Tooling

### 1. Set up monitoring and alerting

**Cloud Monitoring alerting policies for:**
- Clusters approaching End of Support
- Failed upgrade operations
- PDB violations during upgrades
- Node version skew exceeding 1 minor version

**Example alerting policy:**
```bash
gcloud alpha monitoring policies create --policy-from-file=- <<EOF
displayName: "GKE Version EoS Warning"
conditions:
- displayName: "Cluster approaching EoS"
  conditionThreshold:
    filter: 'resource.type="gke_cluster"'
    comparison: COMPARISON_LESS_THAN
    thresholdValue: 2592000  # 30 days in seconds
    aggregations:
    - alignmentPeriod: 300s
      perSeriesAligner: ALIGN_MEAN
EOF
```

### 2. Implement fleet-wide upgrade sequencing

```bash
# Configure rollout sequencing (requires fleet membership)
gcloud container fleet clusterupgrade update \
  --project=PROJECT_ID \
  --upstream-fleet=DEV_PROJECT_ID \
  --default-upgrade-soaking=168h  # 7 days soak time
```

### 3. Create upgrade runbooks and automation

**Infrastructure as Code template for standardized clusters:**
```yaml
# terraform/cluster.tf
resource "google_container_cluster" "primary" {
  name               = var.cluster_name
  location           = var.region
  release_channel {
    channel = var.environment == "prod" ? "REGULAR" : "RAPID"
  }
  
  maintenance_policy {
    maintenance_exclusion {
      exclusion_name = "no-minor-upgrades"
      start_time     = "2024-01-01T00:00:00Z"
      end_time       = "2030-01-01T00:00:00Z"
      exclusion_options {
        scope = "NO_MINOR_UPGRADES"
      }
    }
    
    daily_maintenance_window {
      start_time = var.environment == "prod" ? "02:00" : "03:00"
    }
  }
}
```

## Phase 6: Ongoing Fleet Management

### 1. Monthly health assessments

```bash
#!/bin/bash
# fleet-health-check.sh
echo "=== GKE Fleet Health Report ===" 
echo "Date: $(date)"

# Version distribution
echo "Version Distribution:"
gcloud container clusters list --format="value(currentMasterVersion)" | sort | uniq -c

# EoS warnings
echo "Clusters approaching EoS:"
for CLUSTER in $(gcloud container clusters list --format="value(name,location)"); do
  # Check EoS status and alert if <60 days
done

# Channel distribution
echo "Release Channel Distribution:"
gcloud container clusters list --format="value(releaseChannel.channel)" | sort | uniq -c
```

### 2. Establish upgrade cadence

**Recommended schedule:**
- **Patches:** Automatic (control via maintenance windows)
- **Minor versions:** Quarterly, user-triggered
  - Dev/staging: Week 1 of quarter
  - Production: Week 3 of quarter (after 2-week soak)
- **Emergency patches:** Within 7 days of release

### 3. Self-service developer guidelines

Create documentation for teams:
```markdown
# GKE Workload Readiness Checklist
- [ ] All containers have resource requests/limits
- [ ] StatefulSets have appropriate PDBs
- [ ] No deprecated APIs in manifests
- [ ] Graceful shutdown handling (SIGTERM)
- [ ] Health checks configured
```

## Tools Summary

**GKE provides these self-service assessment tools:**

1. **Insights & Recommendations dashboard** - Deprecation warnings, version issues
2. **GKE release schedule** - Version availability and EoS timelines
3. **Upgrade info API** - Programmatic access to upgrade targets and status  
4. **Cloud Monitoring** - Built-in metrics for cluster health and upgrade events
5. **Scheduled upgrade notifications** - 72-hour advance warning for control plane upgrades
6. **Fleet rollout sequencing** - Multi-cluster upgrade orchestration

The combination of these tools + the commands above will help you systematically assess your fleet, prioritize fixes, and establish sustainable upgrade practices.

**Key insight:** Don't try to fix everything at once. Focus on eliminating immediate risks (EoS clusters, deprecated APIs) first, then standardize on release channels and maintenance controls, then optimize for your long-term operational model.