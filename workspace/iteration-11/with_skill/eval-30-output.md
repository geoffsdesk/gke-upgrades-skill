# GKE Fleet Recovery Plan

You're inheriting a classic "snowflake fleet" — let's get you to a healthy, standardized state. Here's a systematic approach using GKE's self-service tools.

## Phase 1: Fleet Assessment (Week 1)

### 1.1 Inventory and Visibility

**Get the full picture first:**
```bash
# List all clusters with versions and channels
gcloud container clusters list --format="table(
  name,
  zone,
  currentMasterVersion,
  releaseChannel.channel:label=CHANNEL,
  status
)"

# Per-cluster detailed assessment
for cluster in $(gcloud container clusters list --format="value(name)"); do
  echo "=== $cluster ==="
  gcloud container clusters describe $cluster --zone ZONE --format="yaml(
    name,
    currentMasterVersion,
    releaseChannel,
    maintenancePolicy,
    nodePools[].name,
    nodePools[].version,
    nodePools[].upgradeSettings
  )"
done
```

**GKE Fleet Management Console** (if available in your org):
- Navigate to GKE → Fleet → Overview
- Shows fleet-wide version distribution, channel enrollment, and health metrics
- Identifies clusters approaching End of Support

### 1.2 Version Support Status

**Critical assessment — which clusters are at risk:**
```bash
# Check auto-upgrade status and EoS dates for each cluster
for cluster in $(gcloud container clusters list --format="value(name,zone)"); do
  name=$(echo $cluster | cut -d' ' -f1)
  zone=$(echo $cluster | cut -d' ' -f2)
  echo "=== $name ==="
  gcloud container clusters get-upgrade-info $name --region $zone \
    --format="table(
      autoUpgradeStatus,
      endOfStandardSupportTimestamp,
      minorTargetVersion,
      patchTargetVersion
    )"
done
```

**Use GKE Deprecation Insights:**
- GKE Console → Kubernetes Engine → [specific cluster] → Details
- Deprecation insights dashboard shows deprecated API usage across your fleet
- Critical for identifying workloads that will break on upgrade

### 1.3 Workload Assessment

**Identify high-risk workloads:**
```bash
# Clusters with stateful workloads
kubectl get statefulsets -A --all-clusters

# Bare pods (won't survive upgrades)
kubectl get pods -A --all-clusters -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Missing resource requests (breaks Autopilot)
kubectl get pods -A --all-clusters -o json | \
  jq '.items[] | select(.spec.containers[].resources.requests == null) | {ns:.metadata.namespace, name:.metadata.name}'
```

## Phase 2: Stabilization Strategy (Week 2-3)

### 2.1 Immediate Risk Mitigation

**Stop the bleeding — prevent forced upgrades on broken clusters:**
```bash
# Add 30-day "no upgrades" exclusion to clusters with known issues
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "fleet-recovery-freeze" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades
```

**This buys you 30 days to fix workloads and plan upgrades properly.**

### 2.2 Channel Standardization Plan

**Target state for most organizations:**
- **Dev/Test:** Regular channel (good balance of freshness + stability)
- **Staging:** Regular channel 
- **Production:** Stable channel (maximum stability) or Regular (if you need faster security patches)

**Legacy "No channel" migration priority:**
```bash
# Migrate clusters off "No channel" — start with dev/test
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular

# For production clusters needing maximum control
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel stable
```

**Extended channel consideration:** If you have clusters with very slow upgrade cycles or compliance requirements, consider Extended channel for up to 24 months of support (extra cost during extended period).

### 2.3 Maintenance Window Standardization

**Establish predictable upgrade windows:**
```bash
# Production clusters — weekend maintenance
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T06:00:00Z" \
  --maintenance-window-end "2024-01-06T10:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Dev clusters — weeknight maintenance  
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T22:00:00Z" \
  --maintenance-window-end "2024-01-06T04:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=TU"
```

## Phase 3: Workload Remediation (Week 3-4)

### 3.1 Fix Bare Pods
**Wrap in Deployments or Jobs:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: legacy-pod-wrapper
spec:
  replicas: 1
  selector:
    matchLabels:
      app: legacy-app
  template:
    # Copy spec from existing bare pod
```

### 3.2 Add PodDisruptionBudgets
**For critical workloads:**
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: critical-app-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: critical-app
```

### 3.3 Resource Requests (Autopilot requirement)
**Add to all containers:**
```yaml
resources:
  requests:
    cpu: "100m"
    memory: "128Mi"
  limits:
    cpu: "500m"
    memory: "512Mi"
```

### 3.4 Fix Deprecated API Usage
**Use the deprecation insights dashboard to identify and update:**
- Replace deprecated API versions in manifests
- Update helm charts and operators
- Test in dev clusters before production

## Phase 4: Systematic Upgrades (Week 4-8)

### 4.1 Upgrade Sequencing Plan

**Phase 4A: Dev/Test clusters first**
- Remove "no upgrades" exclusion 
- Let auto-upgrades happen naturally
- Validate workload health

**Phase 4B: Staging clusters**
- Remove exclusions after dev validation
- Same versions as production for proper testing

**Phase 4C: Production clusters**  
- Use "no minor or node upgrades" exclusion for maximum control
- Manual upgrades during maintenance windows
- Skip-level node pool upgrades where possible (e.g., 1.31→1.33)

### 4.2 Per-Cluster Upgrade Runbook

```bash
# 1. Pre-flight check
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
  --format="table(currentMasterVersion,nodePools[].version)"
kubectl get pods -A | grep -v Running | grep -v Completed

# 2. Control plane first (auto or manual)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# 3. Configure node pool surge (Standard only)
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# 4. Node pool upgrade (skip-level where possible)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION

# 5. Validation
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed
```

## Phase 5: Long-term Health (Ongoing)

### 5.1 Fleet Monitoring Setup

**GKE Fleet Observability** (if available):
- Enable fleet-wide metrics collection
- Set up alerts for version drift, failed upgrades
- Monitor deprecated API usage across the fleet

**Custom monitoring:**
```bash
# Weekly fleet health check script
#!/bin/bash
echo "=== GKE Fleet Health Report ==="
echo "Date: $(date)"
echo ""

echo "=== Version Distribution ==="
gcloud container clusters list \
  --format="table(name,currentMasterVersion,releaseChannel.channel)"

echo ""
echo "=== Clusters Approaching EoS ==="
# Check clusters with EoS within 60 days
for cluster in $(gcloud container clusters list --format="value(name,zone)"); do
  # ... check EoS dates and alert
done
```

### 5.2 Standardized Maintenance Exclusions

**For production workloads needing tight control:**
```bash
# "No minor or node upgrades" — allows CP security patches, blocks disruptive changes
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "production-control" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**This exclusion automatically renews when new minor versions are adopted.**

### 5.3 Fleet Governance

**Establish these standards:**
- **Channel policy:** Regular for dev/staging, Stable/Regular for prod
- **No "No channel" clusters** — migrate all to release channels
- **Maintenance windows:** Aligned with business requirements  
- **Upgrade cadence:** Auto-upgrades with exclusions for control, not manual-only
- **Workload standards:** PDBs, resource requests, no bare pods
- **Version drift limits:** No more than 1 minor version between environments

## Self-Service Tools Summary

| Tool | Purpose | Access |
|------|---------|--------|
| **GKE Release Schedule** | Version availability timeline | [cloud.google.com/kubernetes-engine/docs/release-schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) |
| **Deprecation Insights** | API deprecation across fleet | GKE Console → cluster → Details |
| **Fleet Management** | Fleet-wide visibility | GKE Console → Fleet (if enabled) |
| **Upgrade Info API** | EoS dates, auto-upgrade targets | `gcloud container clusters get-upgrade-info` |
| **Scheduled Notifications** | 72h upgrade alerts | Cloud Logging (opt-in, preview) |
| **GKE Fleet Observability** | Cross-cluster monitoring | Separate GCP service |

This plan gets you from chaos to a well-managed fleet in ~8 weeks. Start with assessment and stabilization — don't rush into upgrades until workloads are ready.