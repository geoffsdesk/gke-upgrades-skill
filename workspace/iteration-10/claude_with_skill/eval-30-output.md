# GKE Fleet Health Recovery Plan

You're facing a common "inherited technical debt" scenario. Here's a systematic approach to assess, prioritize, and remediate your GKE fleet using GKE's self-service tools.

## Phase 1: Fleet Discovery & Assessment

### Inventory your entire fleet

```bash
# Get all clusters across all regions/zones
gcloud container clusters list --format="table(name,location,currentMasterVersion,releaseChannel.channel:label=CHANNEL,status)"

# More detailed inventory with node versions
for cluster in $(gcloud container clusters list --format="value(name,location)"); do
  name=$(echo $cluster | cut -d$'\t' -f1)
  location=$(echo $cluster | cut -d$'\t' -f2)
  echo "=== $name ($location) ==="
  gcloud container clusters describe $name --region=$location --format="table(
    name,
    currentMasterVersion:label=CP_VERSION,
    releaseChannel.channel:label=CHANNEL,
    nodePools[].name:label=NODE_POOL,
    nodePools[].version:label=NODE_VERSION,
    nodePools[].status:label=STATUS
  )"
done
```

### Check upgrade readiness and EoS status

```bash
# Check auto-upgrade status for each cluster
for cluster in $(gcloud container clusters list --format="value(name,location)"); do
  name=$(echo $cluster | cut -d$'\t' -f1)
  location=$(echo $cluster | cut -d$'\t' -f2)
  echo "=== $name ($location) ==="
  gcloud container clusters get-upgrade-info $name --region=$location
done
```

### Use GKE's deprecation insights dashboard

1. Go to GKE → Clusters → Select cluster → Observability tab
2. Look for "Deprecation insights" section
3. This shows deprecated API usage that will break on upgrade
4. Export findings for each cluster

### Assess workload health patterns

```bash
# Quick cluster health check script
check_cluster_health() {
  local cluster=$1
  local location=$2
  
  echo "=== Health Check: $cluster ($location) ==="
  
  # Get kubeconfig
  gcloud container clusters get-credentials $cluster --region=$location
  
  # Check for bare pods (upgrade risk)
  echo "Bare pods:"
  kubectl get pods -A -o json | jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
  
  # Check PDBs
  echo "PDBs:"
  kubectl get pdb -A
  
  # Check for missing resource requests (Autopilot blocker)
  echo "Pods without resource requests:"
  kubectl get pods -A -o json | jq -r '.items[] | select(.spec.containers[]?.resources?.requests == null) | "\(.metadata.namespace)/\(.metadata.name)"'
  
  echo ""
}

# Run for each cluster
for cluster in $(gcloud container clusters list --format="value(name,location)"); do
  name=$(echo $cluster | cut -d$'\t' -f1)
  location=$(echo $cluster | cut -d$'\t' -f2)
  check_cluster_health $name $location
done
```

## Phase 2: Risk Assessment & Prioritization

### Create a fleet inventory spreadsheet

| Cluster | Environment | Channel | CP Version | Node Versions | EoS Risk | Deprecated APIs | Workload Risk | Priority |
|---------|-------------|---------|------------|---------------|----------|-----------------|---------------|----------|
| prod-1 | Production | No channel | 1.28.x | 1.27.x, 1.28.x | HIGH (EoS in 30d) | apps/v1beta1 | StatefulSets | P0 |
| dev-2 | Development | Rapid | 1.30.x | 1.30.x | LOW | None | Stateless | P2 |

### Risk factors (sort by these):

**P0 (Emergency):**
- Versions approaching EoS in <60 days
- Security vulnerabilities in current version
- Deprecated APIs breaking in target version

**P1 (High):**
- "No channel" clusters (missing modern upgrade controls)
- Version skew >1 minor between CP/nodes
- Mission-critical workloads on old versions

**P2 (Medium):**
- Clusters behind by 2+ minor versions but not EoS-critical
- Inconsistent channel strategy across environments

**P3 (Low):**
- Already on supported versions but need channel alignment
- Minor configuration cleanup

## Phase 3: Standardization Strategy

### Define your target state

**Recommended channel strategy:**
```
Development → Rapid (early feature access, faster feedback)
Staging → Regular (production validation)
Production → Stable (maximum stability) or Regular (faster security patches)
Compliance → Extended (when 24-month support is required)
```

**Version policy:**
- All clusters in an environment tier on the same channel
- No more than 1 minor version spread within a tier
- All clusters enrolled in auto-upgrades (never "No channel")

### Migration plan template

For each cluster group:

1. **Emergency fixes first** (P0 clusters)
2. **Migrate "No channel" to release channels** (P1)
3. **Align versions within environment tiers** (P2)
4. **Standardize maintenance policies** (P3)

## Phase 4: Execution Runbooks

### Emergency EoS remediation (P0 clusters)

```bash
# For clusters approaching EoS - immediate upgrade
CLUSTER_NAME="your-cluster"
REGION="your-region"

# Check available versions
gcloud container get-server-config --region=$REGION --format="yaml(channels)"

# Emergency upgrade to next supported version
gcloud container clusters upgrade $CLUSTER_NAME \
  --region=$REGION \
  --master \
  --cluster-version=NEXT_SUPPORTED_VERSION

# Then upgrade node pools
gcloud container node-pools upgrade POOL_NAME \
  --cluster=$CLUSTER_NAME \
  --region=$REGION \
  --cluster-version=NEXT_SUPPORTED_VERSION
```

### Migrate "No channel" to release channels

```bash
# Step 1: Add temporary protection during migration
gcloud container clusters update $CLUSTER_NAME \
  --region=$REGION \
  --add-maintenance-exclusion-name "migration-protection" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades

# Step 2: Enroll in appropriate release channel
gcloud container clusters update $CLUSTER_NAME \
  --region=$REGION \
  --release-channel regular  # or stable/extended as appropriate

# Step 3: Configure proper maintenance controls
gcloud container clusters update $CLUSTER_NAME \
  --region=$REGION \
  --maintenance-window-start "2024-01-06T06:00:00Z" \
  --maintenance-window-end "2024-01-06T10:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Step 4: Remove temporary protection
gcloud container clusters update $CLUSTER_NAME \
  --region=$REGION \
  --remove-maintenance-exclusion-name "migration-protection"

# Step 5: Add permanent control (optional)
gcloud container clusters update $CLUSTER_NAME \
  --region=$REGION \
  --add-maintenance-exclusion-name "controlled-upgrades" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

### Batch fleet operations

```bash
# Apply consistent maintenance windows across fleet
MAINTENANCE_WINDOW="2024-01-06T06:00:00Z"
MAINTENANCE_END="2024-01-06T10:00:00Z"

for cluster in $(gcloud container clusters list --format="value(name,location)" --filter="releaseChannel.channel:regular"); do
  name=$(echo $cluster | cut -d$'\t' -f1)
  location=$(echo $cluster | cut -d$'\t' -f2)
  
  echo "Configuring maintenance window for $name"
  gcloud container clusters update $name \
    --region=$location \
    --maintenance-window-start $MAINTENANCE_WINDOW \
    --maintenance-window-end $MAINTENANCE_END \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
done
```

## Phase 5: Ongoing Fleet Management

### GKE's built-in fleet management tools

**1. Multi-cluster observability:**
- GKE Enterprise dashboard shows fleet-wide version compliance
- Security posture dashboard for CVE exposure
- Deprecation insights across all clusters

**2. Scheduled upgrade notifications (preview):**
```bash
# Enable 72-hour advance notifications via Cloud Logging
gcloud container clusters update $CLUSTER_NAME \
  --region=$REGION \
  --enable-upgrade-notifications
```

**3. Fleet monitoring queries:**
```bash
# Regular fleet health check
gcloud container clusters list \
  --format="table(
    name:label=CLUSTER,
    location:label=LOCATION,
    currentMasterVersion:label=CP_VERSION,
    releaseChannel.channel:label=CHANNEL,
    status:label=STATUS
  )" \
  --sort-by=location

# Check for version drift
gcloud container clusters list \
  --format="csv[no-heading](name,location,currentMasterVersion)" | \
  sort -k3 | \
  uniq -c -f2
```

### Automation recommendations

**Create monitoring alerts for:**
- Clusters approaching EoS (60-day warning)
- Failed upgrade operations
- Version skew between environments
- New deprecated API usage

**Use Cloud Functions to:**
- Auto-apply maintenance windows to new clusters
- Send Slack notifications for upgrade completions
- Generate monthly fleet compliance reports

### Success metrics

Track these over time:
- % clusters on supported versions
- % clusters with proper maintenance windows configured  
- % clusters on release channels (vs "No channel")
- Mean time to upgrade across fleet
- Version spread within environment tiers

## Quick-start checklist

```
Fleet Recovery Checklist
- [ ] Complete fleet inventory (versions, channels, locations)
- [ ] Identify P0 EoS risks - upgrade immediately
- [ ] Migrate all "No channel" clusters to release channels
- [ ] Standardize maintenance windows across fleet
- [ ] Configure "no minor or node upgrades" exclusions for production
- [ ] Set up fleet monitoring dashboard
- [ ] Document upgrade procedures for each environment tier
- [ ] Train team on GKE auto-upgrade model vs manual upgrades
- [ ] Schedule regular fleet health reviews (monthly)
```

The key insight: **embrace GKE's auto-upgrade model** with proper controls (maintenance windows + exclusions) rather than fighting it with manual version pinning. This gives you predictability AND security compliance without operational overhead.