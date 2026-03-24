# GKE Fleet Remediation Plan

You've inherited a typical "legacy fleet" situation. Here's how to systematically assess, prioritize, and remediate your GKE clusters using GKE's built-in tooling.

## Phase 1: Discovery & Assessment (Week 1-2)

### Fleet-wide inventory

Start with a comprehensive audit using GKE Fleet Management:

```bash
# Enable Fleet API (if not already enabled)
gcloud services enable gkehub.googleapis.com

# Register all clusters to Fleet for centralized visibility
for cluster in $(gcloud container clusters list --format="value(name,location)"); do
  gcloud container fleet memberships register $cluster --gke-cluster=$cluster
done

# Get fleet-wide view
gcloud container fleet memberships list --format="table(name,endpoint.gkeCluster.clusterMissing)"
```

### Cluster health assessment

Use this script to audit all clusters:

```bash
#!/bin/bash
# cluster-audit.sh

echo "Cluster,Zone,Mode,Version,Channel,EoS_Date,Status,Risk_Level"

for cluster_info in $(gcloud container clusters list --format="csv[no-heading](name,location,autopilot.enabled,currentMasterVersion,releaseChannel.channel)"); do
  IFS=',' read -r name location autopilot version channel <<< "$cluster_info"
  
  # Get EoS info
  eol_info=$(gcloud container clusters get-upgrade-info $name --region=$location --format="value(endOfStandardSupportTimestamp)" 2>/dev/null || echo "unknown")
  
  # Determine risk
  if [[ "$channel" == "" ]]; then
    risk="HIGH - No Channel"
  elif [[ "$eol_info" != "unknown" && $(date -d "$eol_info" +%s) -lt $(date -d "+30 days" +%s) ]]; then
    risk="CRITICAL - EoS <30 days"
  elif [[ "$version" =~ 1\.(2[0-9]|30)\. ]]; then
    risk="MEDIUM - Old version"
  else
    risk="LOW"
  fi
  
  echo "$name,$location,$autopilot,$version,$channel,$eol_info,$risk"
done
```

### GKE's built-in assessment tools

**1. Deprecation insights dashboard:**
```bash
# Check for deprecated API usage across fleet
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=global \
  --format="table(name,description,lastRefreshTime)"
```

**2. Security posture assessment:**
```bash
# Binary Authorization violations
gcloud container binauthz attestations list

# Pod Security Standard violations
kubectl get events -A --field-selector reason=FailedCreate | grep -i "pod security"
```

**3. Cost optimization insights:**
```bash
# Right-sizing recommendations
gcloud recommender recommendations list \
  --recommender=google.compute.instance.MachineTypeRecommender \
  --location=ZONE \
  --format="table(name,description,primaryImpact.costProjection.cost.units)"
```

## Phase 2: Risk-Based Prioritization (Week 2-3)

### Priority matrix

| Priority | Criteria | Action Timeline |
|----------|----------|----------------|
| **P0 (Emergency)** | EoS < 30 days, "No channel" + old version | Immediate (1-2 weeks) |
| **P1 (High)** | "No channel" on supported versions | 1 month |
| **P2 (Medium)** | Release channels but >2 versions behind | 2-3 months |
| **P3 (Low)** | Modern versions, proper channels | Ongoing maintenance |

### Sample triage output

```bash
# Generate prioritized remediation list
gcloud container clusters list \
  --format="table(name,location,currentMasterVersion,releaseChannel.channel,status)" \
  --filter="releaseChannel.channel:''" --sort-by="currentMasterVersion"
```

## Phase 3: Remediation Strategy

### For "No channel" clusters (Priority 1)

**Migration path:** No channel → Regular/Stable channel with maintenance exclusions

```bash
# Step 1: Check version availability in target channel
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels.REGULAR.validVersions)"

# Step 2: If version is available, migrate directly
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular

# Step 3: If version is NOT available, you'll be "ahead of channel"
# Add exclusion to control timing until channel catches up
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular \
  --add-maintenance-exclusion-name "migration-freeze" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time $(date -u -d "+90 days" +"%Y-%m-%dT%H:%M:%SZ")
```

**⚠️ Migration warning:** If your current version isn't available in the target channel, your cluster will be "ahead of channel" and won't receive auto-upgrades until the channel catches up. You'll still get patches but not minor upgrades.

### For severely outdated clusters (EoS risk)

**Option A - Emergency upgrade:**
```bash
# Direct upgrade to latest supported version
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version LATEST_SUPPORTED_VERSION

# Then migrate node pools (if Standard)
for pool in $(gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE --format="value(name)"); do
  gcloud container node-pools upgrade $pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version LATEST_SUPPORTED_VERSION
done
```

**Option B - Recreate cluster (for hopeless cases):**
If a cluster is 5+ versions behind with complex workloads, it may be faster to create a fresh cluster and migrate workloads.

### For mixed-version fleets

**Standardization strategy:**
1. **Dev/Test:** Rapid channel
2. **Staging:** Regular channel  
3. **Production:** Stable channel

All environments should stay within 1 minor version of each other. Use maintenance exclusions + manual minor upgrades to keep them synchronized.

## Phase 4: Governance & Automation

### Fleet-wide policies

**1. Maintenance windows:**
```bash
# Standardize maintenance windows across fleet
for cluster in $(gcloud container clusters list --format="value(name,location)"); do
  gcloud container clusters update $cluster \
    --maintenance-window-start "2024-01-01T02:00:00Z" \
    --maintenance-window-end "2024-01-01T06:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
done
```

**2. Fleet-wide monitoring:**
```bash
# Create Cloud Monitoring dashboard for upgrade health
gcloud alpha monitoring dashboards create --config-from-file=fleet-dashboard.json
```

**3. Automated fleet health checks:**
```bash
#!/bin/bash
# fleet-health-check.sh - Run weekly

echo "=== GKE Fleet Health Report ==="
echo "Date: $(date)"

# Clusters approaching EoS
echo "🚨 CRITICAL - Approaching End of Support:"
gcloud container clusters list --format="table(name,location,currentMasterVersion)" \
  --filter="currentMasterVersion~1.2[0-9]"

# No channel clusters
echo "⚠️  HIGH - Legacy 'No Channel' clusters:"
gcloud container clusters list --format="table(name,location,currentMasterVersion)" \
  --filter="NOT releaseChannel.channel:*"

# Deprecated API usage
echo "📊 Deprecated API Usage:"
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=global \
  --format="table(targetResources,description)"
```

## Phase 5: Self-Service Tools & Monitoring

### Built-in GKE Fleet Management features

**1. Fleet-wide upgrade orchestration:**
```bash
# Configure rollout sequencing (for large fleets)
gcloud container fleet clusterupgrade update \
  --default-upgrade-soaking=7d \
  --upstream-fleet=PROJECT_ID
```

**2. Fleet observability:**
```bash
# Enable Fleet observability for centralized metrics
gcloud container fleet observability enable \
  --project=PROJECT_ID
```

**3. Scheduled upgrade notifications (Preview):**
```bash
# Opt into 72-hour advance notifications
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --enable-scheduled-upgrade-notifications
```

### Monitoring dashboards

Create Cloud Monitoring dashboards tracking:
- Clusters by version and channel
- EoS timeline tracking
- Failed upgrade operations
- Deprecated API usage trends

### GitOps integration

Store cluster configurations in Git with automated drift detection:
```yaml
# clusters.yaml
clusters:
  - name: prod-us-central1
    channel: stable
    version: auto
    maintenanceWindow: "SAT 02:00-06:00 UTC"
    exclusions:
      - scope: no_minor_or_node_upgrades
        until: end_of_support
```

## Success Metrics

Track these KPIs monthly:
- **% clusters on release channels** (target: 100%)
- **% clusters within 2 minor versions of latest** (target: 80%+)
- **Average time to patch deployment** (target: <30 days)
- **Upgrade failure rate** (target: <5%)
- **Clusters approaching EoS** (target: 0)

## Timeline Summary

- **Week 1-2:** Discovery and risk assessment
- **Week 3-6:** Emergency P0/P1 remediation  
- **Month 2-3:** Systematic P2 cleanup
- **Month 4+:** Steady-state maintenance with automation

This approach gets your fleet from "inherited chaos" to "well-managed" systematically, using GKE's native tooling rather than complex external solutions.