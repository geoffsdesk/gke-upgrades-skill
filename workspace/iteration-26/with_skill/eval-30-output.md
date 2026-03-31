# GKE Fleet Modernization Plan

You've inherited a common scenario - let me help you systematically assess and modernize your GKE fleet using GKE's built-in tools.

## Phase 1: Assessment & Discovery

### Use GKE's Fleet-wide Assessment Tools

**GKE Recommender Insights (your primary assessment tool):**
```bash
# Get fleet-wide deprecation and version insights
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=- \
    --project=PROJECT_ID \
    --filter="category.category:RELIABILITY" \
    --format="table(name.segment(5),insightSubtype,description)"

# Focus on critical issues
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=- \
    --project=PROJECT_ID \
    --filter="insightSubtype:(DEPRECATED_API_USAGE OR VERSION_SKEW OR EOS_VERSION)" \
    --format="csv(name.segment(5),insightSubtype,description,targetResources[0].name)"
```

**Fleet inventory script:**
```bash
# Create comprehensive fleet inventory
for region in $(gcloud compute regions list --format="value(name)"); do
  gcloud container clusters list --region=$region --format="csv(name,location,releaseChannel.channel,currentMasterVersion,nodePools[0].version,status)" 2>/dev/null
done > gke-fleet-inventory.csv
```

**Version spread analysis:**
```bash
# Count clusters by version
gcloud container clusters list --format="value(currentMasterVersion)" | sort | uniq -c | sort -nr

# Identify "snowflake" clusters (manually frozen versions)
gcloud container clusters list --filter="releaseChannel.channel IS NULL" --format="table(name,location,currentMasterVersion,status)"
```

## Phase 2: Prioritization Matrix

**Risk categories (handle in this order):**

### Priority 1: Security & Compliance Risk
- Clusters approaching/at End of Support (EoS)
- Deprecated API usage blocking auto-upgrades
- Legacy "No channel" clusters (highest technical debt)

### Priority 2: Operational Risk  
- Version skew >1 minor (nodes far behind control plane)
- Mixed channels within same environment (dev vs prod inconsistency)
- Clusters without maintenance windows

### Priority 3: Efficiency Opportunities
- Autopilot migration candidates (stateless workloads)
- Consolidation opportunities (underutilized clusters)
- Right-sizing recommendations

## Phase 3: Systematic Remediation

### Step 1: Emergency EoS Mitigation

**Check EoS status across fleet:**
```bash
# Find clusters at/near EoS
gcloud container clusters list --format="table(name,location,currentMasterVersion)" | while read name location version; do
  if [[ "$name" != "NAME" ]]; then
    gcloud container clusters get-upgrade-info $name --region=$location --format="value(endOfStandardSupportTimestamp)" 2>/dev/null
  fi
done
```

**Apply temporary protection for critical clusters:**
```bash
# 30-day "no upgrades" exclusion for clusters that can't be upgraded immediately
gcloud container clusters update CLUSTER_NAME \
    --region REGION \
    --add-maintenance-exclusion-name "emergency-freeze" \
    --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
    --add-maintenance-exclusion-end-time $(date -u -d '+30 days' +"%Y-%m-%dT%H:%M:%SZ") \
    --add-maintenance-exclusion-scope no_upgrades
```

### Step 2: Channel Normalization Strategy

**Recommended target state:**
- **Dev/Staging:** Regular channel (balanced cadence)
- **Production:** Regular or Stable channel (your choice based on risk tolerance)
- **Regulated/Compliance:** Extended channel (24-month support, manual minor control)

**Migration commands:**
```bash
# Migrate legacy "No channel" to Regular (closest to legacy behavior)
gcloud container clusters update CLUSTER_NAME \
    --region REGION \
    --release-channel regular

# For maximum control production environments
gcloud container clusters update CLUSTER_NAME \
    --region REGION \
    --release-channel extended \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

**Channel migration validation:**
```bash
# Verify channel migration success and check auto-upgrade targets
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

### Step 3: Standardized Maintenance Controls

**Production cluster template:**
```bash
gcloud container clusters update CLUSTER_NAME \
    --region REGION \
    --maintenance-window-start "2025-01-04T02:00:00Z" \
    --maintenance-window-end "2025-01-04T06:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

This gives you:
- Saturday 2-6 AM maintenance window
- Automatic security patches (control plane only)
- Manual control over minor versions and node upgrades
- Protection until version reaches EoS

### Step 4: Deprecated API Remediation

**GKE automatically pauses auto-upgrades when deprecated APIs are detected.** Use GKE's built-in detection:

```bash
# Check which clusters have blocked upgrades due to deprecated APIs
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=- \
    --project=PROJECT_ID \
    --filter="insightSubtype:DEPRECATED_API_USAGE" \
    --format="table(name.segment(5):label=CLUSTER,description,targetResources[0].name:label=RESOURCE)"
```

**Quick kubectl check for active usage:**
```bash
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated | head -10
```

**Common deprecated API fixes:**
- `extensions/v1beta1` Ingress → `networking.k8s.io/v1`
- `apps/v1beta1` Deployment → `apps/v1`  
- `policy/v1beta1` PodSecurityPolicy → Pod Security Standards

## Phase 4: Fleet Governance & Automation

### Rollout Sequencing for Multi-Cluster Coordination

For sophisticated platform teams managing 10+ clusters:

```bash
# Configure fleet-based rollout sequencing
gcloud container fleet clusterupgrade update \
    --project=PROJECT_ID \
    --upstream-fleet=dev-fleet-project \
    --default-upgrade-soaking=24h
```

This ensures dev clusters upgrade before production automatically.

### Monitoring & Alerting Setup

**Key monitoring queries:**
```bash
# Clusters approaching EoS (30 days out)
gcloud container clusters list --format="json" | jq -r '.[] | select(.currentMasterVersion | test("1\\.(2[89]|30)")) | {name, location, version: .currentMasterVersion}'

# Clusters with blocked auto-upgrades
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=- \
    --project=PROJECT_ID \
    --filter="insightSubtype:DEPRECATED_API_USAGE AND state.state:ACTIVE"
```

**Set up scheduled upgrade notifications:**
```bash
# Enable 72-hour advance notifications (Preview - March 2026)
gcloud container clusters update CLUSTER_NAME \
    --region REGION \
    --enable-scheduled-upgrades
```

## Phase 5: Long-term Fleet Strategy

### Recommended Steady State

**Channel strategy:**
- All environments on **same channel** (Regular recommended)
- Use **rollout sequencing** for upgrade ordering
- **Maintenance windows** for timing control
- **Maintenance exclusions** only for disruption-intolerant workloads

**Alternative for ultimate control (regulated environments):**
- **Extended channel** with persistent "no minor or node" exclusions  
- Manual minor upgrades during planned maintenance windows
- Automatic security patches only

### Autopilot Migration Assessment

Identify Autopilot candidates:
```bash
# Find clusters with stateless workloads (good Autopilot candidates)
kubectl get deployments -A -o json | jq -r '.items[] | select(.spec.template.spec.volumes == null or (.spec.template.spec.volumes | length == 0) or all(.spec.template.spec.volumes[]; .emptyDir or .configMap or .secret)) | "\(.metadata.namespace)/\(.metadata.name)"'
```

Autopilot benefits: no node management, automatic patching, pay-per-pod billing.

## Self-Service Tools Summary

**GKE provides these built-in assessment tools:**
1. **GKE Recommender Insights** - deprecation detection, version skew, EoS warnings
2. **Upgrade Info API** - EoS dates, auto-upgrade targets, rollback status  
3. **GKE Release Schedule** - version availability timeline across channels
4. **Console Insights Dashboard** - visual fleet health overview
5. **Cluster Notifications** - Pub/Sub events for upgrade status
6. **Scheduled Upgrade Notifications** - 72h advance warning (preview)

## Implementation Timeline

**Week 1:** Assessment and emergency EoS protection
**Week 2-4:** Channel normalization (5-10 clusters per week)  
**Week 5-8:** Deprecated API remediation
**Week 9-12:** Maintenance control standardization
**Ongoing:** Monitor with GKE tools, establish governance

Start with the GKE Recommender Insights - it's your primary fleet health tool and will surface the highest-priority issues automatically.