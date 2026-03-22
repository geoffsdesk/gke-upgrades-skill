# GKE Fleet Modernization Plan

You've inherited a common scenario - a "snowflake fleet" with inconsistent upgrade management. Here's a systematic approach to get your clusters into a healthy, automated lifecycle.

## Phase 1: Fleet Assessment & Discovery

### Inventory your fleet
```bash
# Get all clusters with versions and channels
gcloud container clusters list --format="table(
  name,
  location,
  currentMasterVersion,
  releaseChannel.channel:label=CHANNEL,
  status
)" > cluster-inventory.csv

# Detailed per-cluster analysis
for cluster in $(gcloud container clusters list --format="value(name,location)" | tr '\t' ':'); do
  name=$(echo $cluster | cut -d: -f1)
  zone=$(echo $cluster | cut -d: -f2)
  echo "=== $name ($zone) ==="
  
  # Version and channel info
  gcloud container clusters describe $name --region $zone \
    --format="value(currentMasterVersion,releaseChannel.channel,autopilot.enabled)"
    
  # Check auto-upgrade status and EoS risk
  gcloud container clusters get-upgrade-info $name --region $zone \
    --format="yaml(autoUpgradeStatus,endOfStandardSupportTimestamp)"
done
```

### Use GKE's self-service assessment tools

**1. GKE Deprecation Insights Dashboard**
- Console → Kubernetes Engine → Insights
- Shows deprecated API usage across all clusters
- Critical for planning upgrades that won't break workloads
- Export findings to prioritize remediation

**2. GKE Release Schedule**
- https://cloud.google.com/kubernetes-engine/docs/release-schedule
- Shows version availability by channel and EoS dates
- Use to understand your risk exposure

**3. Per-cluster upgrade readiness**
```bash
# Check what each cluster would upgrade to
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION \
  --format="table(
    autoUpgradeStatus:label=STATUS,
    minorTargetVersion:label=TARGET_MINOR,
    patchTargetVersion:label=TARGET_PATCH,
    endOfStandardSupportTimestamp:label=EOS_DATE
  )"
```

## Phase 2: Risk Triage & Prioritization

### Categorize clusters by risk level

**CRITICAL (fix immediately):**
- Clusters on versions approaching End of Support (<90 days)
- Clusters with deprecated API usage that will break on upgrade
- Production clusters on "No channel" (missing key upgrade controls)

**HIGH (fix within 30 days):**
- Clusters >6 months behind latest stable
- GPU/AI workload clusters without proper maintenance exclusions
- Clusters without maintenance windows configured

**MEDIUM (fix within 90 days):**
- Dev/test clusters on inconsistent channels
- Clusters missing PDBs or proper resource requests

### Create a risk matrix
```bash
# Generate cluster risk report
echo "CLUSTER,ZONE,VERSION,CHANNEL,EOS_RISK,DEPRECATED_APIS" > risk-assessment.csv

for cluster in $(gcloud container clusters list --format="value(name,location)" | tr '\t' ':'); do
  name=$(echo $cluster | cut -d: -f1)
  zone=$(echo $cluster | cut -d: -f2)
  
  version=$(gcloud container clusters describe $name --region $zone --format="value(currentMasterVersion)")
  channel=$(gcloud container clusters describe $name --region $zone --format="value(releaseChannel.channel)")
  
  # Check for deprecated API usage (requires kubectl access)
  deprecated_apis="UNKNOWN"
  if kubectl config get-contexts | grep -q $name; then
    kubectl config use-context $name
    deprecated_count=$(kubectl get --raw /metrics 2>/dev/null | grep apiserver_request_total | grep deprecated | wc -l)
    deprecated_apis=$deprecated_count
  fi
  
  echo "$name,$zone,$version,$channel,CHECK_MANUALLY,$deprecated_apis" >> risk-assessment.csv
done
```

## Phase 3: Standardize Fleet Configuration

### Define your target state

**Recommended fleet architecture:**
- **Dev environments:** Regular channel (faster updates, good for testing)
- **Staging environments:** Regular channel (same as prod for parity)  
- **Production environments:** Stable channel (battle-tested versions)
- **Compliance/slow-change prod:** Extended channel (24-month support)

### Migrate "No channel" clusters first (highest priority)

**Why this matters:** "No channel" clusters lack critical upgrade control features:
- No "no minor or node upgrades" exclusions (only basic 30-day blocks)
- No per-nodepool maintenance exclusions  
- No Extended support option
- Limited granular control

**Migration process:**
```bash
# For each "No channel" cluster, migrate to Regular (closest to legacy behavior)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel regular

# Or Extended channel for maximum flexibility around EoS enforcement
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel extended
```

**Important:** When migrating with existing maintenance exclusions, add a temporary "no_upgrades" exclusion first, then translate policies. Some exclusion types don't translate 1:1 between "No channel" and release channels.

### Configure consistent maintenance policies

**Standard maintenance configuration for prod clusters:**
```bash
# Set maintenance window (off-peak hours)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-window-start "2024-01-06T06:00:00Z" \
  --maintenance-window-end "2024-01-06T10:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Add "no minor or node upgrades" exclusion for maximum control
# (allows CP security patches, blocks disruptive changes)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "prod-protection" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Phase 4: Workload Readiness Assessment

### Use GKE's built-in checks
```bash
# Check for workloads without proper resource management (critical for Autopilot)
kubectl get pods -A -o json | jq -r '
  .items[] | 
  select(.spec.containers[] | .resources.requests == null) | 
  "\(.metadata.namespace)/\(.metadata.name) - missing resource requests"'

# Find bare pods that won't survive upgrades
kubectl get pods -A -o json | jq -r '
  .items[] | 
  select(.metadata.ownerReferences | length == 0) | 
  "\(.metadata.namespace)/\(.metadata.name) - bare pod, needs controller"'

# Check PDB coverage for critical workloads
kubectl get pdb -A -o wide
```

### Deprecated API remediation
Use the GKE Deprecation Insights dashboard to identify and fix deprecated API usage. Common issues:
- Old apiVersions in Helm charts
- Deprecated Ingress configurations  
- Legacy RBAC resources
- Outdated CRDs from operators

## Phase 5: Staged Upgrade Campaign

### Start with lowest-risk clusters
1. **Dev clusters first** - test your upgrade procedures
2. **Staging clusters** - validate application compatibility  
3. **Production clusters last** - with proven upgrade procedures

### Use GKE's upgrade orchestration features

**For large fleets (10+ clusters):**
```bash
# Configure rollout sequencing (all clusters must be on same channel)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --enable-rollout-sequencing \
  --rollout-sequence-stage STAGE_NUMBER \
  --rollout-sequence-soak-duration DURATION
```

**For smaller fleets:** Use maintenance windows to stagger timing manually.

## Self-Service Tools Summary

GKE provides these tools for fleet management:

| Tool | Purpose | How to access |
|------|---------|---------------|
| **GKE Deprecation Insights** | Find deprecated API usage | Console → K8s Engine → Insights |
| **Release Schedule** | Version availability & EoS dates | Cloud docs + `gcloud get-server-config` |
| **Upgrade Info API** | Per-cluster upgrade targets & status | `gcloud container clusters get-upgrade-info` |
| **Scheduled Upgrade Notifications** | 72h advance notice (opt-in, preview) | Cloud Logging |
| **Fleet observability** | Cross-cluster monitoring | Console fleet view |
| **Rollout sequencing** | Automated multi-cluster upgrades | `gcloud` rollout flags |

## Phase 6: Ongoing Fleet Hygiene

### Establish operational practices

**Monthly fleet review:**
```bash
# Generate fleet health report
gcloud container clusters list \
  --format="table(name,location,currentMasterVersion,releaseChannel.channel,status)" \
  --filter="status=RUNNING" > monthly-fleet-report.csv
```

**Quarterly upgrade campaigns:**
- Review deprecation insights
- Plan major version upgrades during maintenance windows
- Test in dev/staging first

**Continuous monitoring:**
- Set up alerting for clusters approaching EoS
- Monitor auto-upgrade notifications in Cloud Logging
- Track upgrade success/failure rates

### Prevent future drift

**Use Infrastructure as Code:**
```yaml
# Terraform example for consistent cluster config
resource "google_container_cluster" "primary" {
  release_channel {
    channel = "REGULAR"  # or "STABLE" for prod
  }
  
  maintenance_policy {
    recurring_window {
      start_time = "2024-01-06T06:00:00Z"
      end_time   = "2024-01-06T10:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SA"
    }
  }
}
```

**Standardize on release channels + exclusions** instead of manual version pinning. This gives you the control you need while staying on the supported, automated upgrade path that makes GKE valuable.

The key insight: GKE's primary value is **automated lifecycle management**. Getting your fleet onto release channels with appropriate maintenance controls is far more important than achieving perfect version consistency. Focus on automation and policy-driven upgrades rather than manual coordination.