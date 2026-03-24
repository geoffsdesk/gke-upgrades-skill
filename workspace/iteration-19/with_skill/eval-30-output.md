# GKE Fleet Modernization Plan

You're dealing with the classic "inherited snowflake fleet" scenario. Here's a systematic approach to assess, prioritize, and modernize your clusters using GKE's self-service tooling.

## Phase 1: Fleet Assessment & Inventory

### Discovery and mapping
```bash
# Get all clusters across projects/regions
gcloud container clusters list --format="table(
  name,
  location,
  releaseChannel.channel:label=CHANNEL,
  currentMasterVersion:label=CP_VERSION,
  nodePools[].version.list():label=NODE_VERSIONS,
  status
)" --sort-by=location

# Export for analysis
gcloud container clusters list --format="csv(
  name,
  location,
  releaseChannel.channel,
  currentMasterVersion,
  nodePools[].version.list(),
  nodePools[].name.list(),
  autopilot.enabled
)" > cluster-inventory.csv
```

### Deprecation and EoS assessment
```bash
# Check for deprecated API usage (blocks auto-upgrades)
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=LOCATION \
  --project=PROJECT_ID \
  --format="table(name.segment(-1):label=CLUSTER,
    insightSubtype:label=ISSUE_TYPE,
    description)" \
  --filter="insightSubtype:(DEPRECATED_API_USAGE OR VERSION_SKEW OR END_OF_SUPPORT)"

# Check upgrade targets and EoS dates for each cluster
for cluster in $(gcloud container clusters list --format="value(name,zone)"); do
  echo "=== $cluster ==="
  gcloud container clusters get-upgrade-info $cluster --format="yaml"
done
```

### GKE Console fleet view
Navigate to **GKE Console → Fleet management** for visual overview:
- Clusters by version (heat map shows version spread)
- Security posture (deprecated APIs, EoS warnings)
- Insights dashboard (recommender violations)
- Fleet workloads view (applications across clusters)

## Phase 2: Risk Assessment & Prioritization

### High-priority clusters (fix first)
1. **EoS versions** — forced upgrades imminent
2. **"No channel" clusters** — missing modern upgrade controls  
3. **Deprecated API usage** — auto-upgrades paused
4. **Version skew >2 minors** — nodes can't be upgraded

### Medium-priority clusters
- Extreme version spread (1.25 and 1.31 in same fleet)
- Missing maintenance windows/exclusions
- Legacy node pool configurations

### Risk categorization script
```bash
#!/bin/bash
# cluster-risk-assessment.sh

echo "=== HIGH RISK CLUSTERS ==="
gcloud container clusters list --format="table(name,location,currentMasterVersion)" \
  --filter="releaseChannel.channel:'' AND currentMasterVersion<1.30"

echo "=== DEPRECATED API CLUSTERS ==="
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=us-central1 \
  --project=PROJECT_ID \
  --filter="insightSubtype:DEPRECATED_API_USAGE" \
  --format="value(targetResources[0].name.segment(-1))" | sort -u

echo "=== VERSION SKEW CLUSTERS ==="
for cluster_info in $(gcloud container clusters list --format="value(name,zone)"); do
  cluster=$(echo $cluster_info | cut -d' ' -f1)
  zone=$(echo $cluster_info | cut -d' ' -f2)
  
  # Check if any nodepool is >2 versions behind
  skew=$(gcloud container clusters describe $cluster --zone=$zone \
    --format="value(nodePools[].version[])" | tr ' ' '\n' | sort -u | wc -l)
  
  if [ $skew -gt 2 ]; then
    echo "$cluster ($zone) - $skew different versions"
  fi
done
```

## Phase 3: Fleet Modernization Strategy

### Target state architecture
```
Environment Strategy:
- Dev: Regular channel + "no minor" exclusion + manual minor upgrades
- Staging: Regular channel + "no minor" exclusion + manual minor upgrades  
- Prod: Regular or Stable channel + "no minor" exclusion + manual minor upgrades

This keeps all environments on the same minor version in steady state while giving you manual control over minor version progression. Patches flow automatically (security compliance) but are controlled by maintenance windows for timing.
```

### Migration sequence (recommended order)

**1. Fix deprecated APIs first** (blocks everything else)
```bash
# For each cluster with deprecated API usage:
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
# Address the specific APIs, then verify
gcloud recommender insights list --insight-type=google.container.DiagnosisInsight
```

**2. Migrate "No channel" to Regular/Stable**
```bash
# For each "No channel" cluster:
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**3. Establish maintenance windows fleet-wide**
```bash
# Production pattern: Saturday 2-6 AM
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2025-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**4. Version consolidation** (bring clusters to same minor version)
- Target: Latest stable minor supported by all your workloads
- Sequence: Dev → Staging → Prod (manual upgrades with validation)
- Use skip-level upgrades where possible (1.28→1.30→1.32)

## Phase 4: Self-Service Tooling for Ongoing Management

### GKE recommender and insights
```bash
# Weekly fleet health check
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=LOCATION \
  --project=PROJECT_ID \
  --format="table(name.segment(-1):label=CLUSTER,
    insightSubtype:label=ISSUE,
    severity,
    description)"

# Set up automated alerting
gcloud alpha monitoring policies create --policy-from-file=gke-insights-policy.yaml
```

### Upgrade info API for planning
```bash
# Check auto-upgrade targets across fleet
for cluster_zone in $(gcloud container clusters list --format="value(name,zone)"); do
  cluster=$(echo $cluster_zone | cut -d' ' -f1)
  zone=$(echo $cluster_zone | cut -d' ' -f2)
  
  echo "=== $cluster ==="
  gcloud container clusters get-upgrade-info $cluster --region $zone \
    --format="yaml(autoUpgradeStatus,minorTargetVersion,patchTargetVersion,endOfStandardSupportTimestamp)"
done
```

### Scheduled upgrade notifications (preview)
```bash
# Enable 72h advance notifications
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --send-scheduled-upgrade-notifications
  
# Monitor via Cloud Logging
gcloud logging read "resource.type=gke_cluster AND jsonPayload.upgradeType:scheduled" \
  --format="table(timestamp,resource.labels.cluster_name,jsonPayload.upgradeType)"
```

### GKE release schedule for planning
Bookmark: https://cloud.google.com/kubernetes-engine/docs/release-schedule
- Shows when versions arrive in each channel
- EoS dates for longer-range planning
- Best-case auto-upgrade timing

## Phase 5: Operational Excellence

### Fleet governance
```bash
# Policy-as-code with Config Connector
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerCluster
metadata:
  name: cluster-template
spec:
  releaseChannel:
    channel: REGULAR
  maintenancePolicy:
    recurringWindow:
      recurrence: "FREQ=WEEKLY;BYDAY=SA"
      window:
        startTime: "2025-01-01T02:00:00Z"
        endTime: "2025-01-01T06:00:00Z"
  # Standard configuration across fleet
```

### Monitoring and alerting setup
```yaml
# Cloud Monitoring alert policy for EoS versions
displayName: "GKE Cluster Approaching EoS"
conditions:
  - displayName: "Version EoS within 30 days"
    conditionThreshold:
      filter: resource.type="gke_cluster"
      comparison: COMPARISON_LESS_THAN
      thresholdValue: 2592000  # 30 days in seconds
      duration: 300s
```

### Progressive rollout with fleet sequencing
```bash
# Set up dev → staging → prod rollout order
gcloud container fleet clusterupgrade update \
  --project=DEV_PROJECT \
  --upstream-fleet=projects/STAGING_PROJECT \
  --default-upgrade-soaking=7d
```

## Sample modernization runbook

```markdown
## Cluster Modernization Runbook

**Target cluster:** [NAME] | **Current state:** No channel, 1.28, deprecated APIs

### Pre-work
- [ ] Fix deprecated API usage (check recommender insights)
- [ ] Verify workload compatibility with target version 1.31
- [ ] Schedule maintenance window (weekend)

### Migration steps
1. **Add maintenance exclusion** (prevent auto-upgrade during migration)
   ```bash
   gcloud container clusters update CLUSTER \
     --add-maintenance-exclusion-scope no_upgrades \
     --add-maintenance-exclusion-start-time 2025-01-15T00:00:00Z \
     --add-maintenance-exclusion-end-time 2025-01-22T00:00:00Z
   ```

2. **Migrate to release channel**
   ```bash
   gcloud container clusters update CLUSTER \
     --release-channel regular
   ```

3. **Sequential control plane upgrades** (1.28→1.29→1.30→1.31)
   ```bash
   gcloud container clusters upgrade CLUSTER --master --cluster-version 1.29.x-gke.latest
   # Wait, validate, repeat for 1.30, 1.31
   ```

4. **Skip-level node pool upgrade** (1.28→1.31)
   ```bash
   gcloud container node-pools upgrade POOL --cluster-version 1.31.x-gke.latest
   ```

5. **Set permanent maintenance controls**
   ```bash
   gcloud container clusters update CLUSTER \
     --maintenance-window-start "2025-01-01T02:00:00Z" \
     --maintenance-window-duration 4h \
     --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA" \
     --add-maintenance-exclusion-scope no_minor_upgrades \
     --add-maintenance-exclusion-until-end-of-support
   ```

6. **Remove temporary exclusion**
   ```bash
   gcloud container clusters update CLUSTER \
     --remove-maintenance-exclusion-name temp-migration-freeze
   ```
```

## Key recommendations

1. **Start with the GKE Console fleet view** — visual overview beats CLI for initial assessment
2. **Use GKE recommender insights** — automated detection of deprecated APIs, version skew, EoS warnings
3. **Fix deprecated APIs before everything else** — they block auto-upgrades and cause cascading issues
4. **Migrate off "No channel" immediately** — missing critical upgrade control features
5. **Standardize on Regular channel + "no minor" exclusions** — gives you patch compliance with minor version control
6. **Don't try to fix everything at once** — sequence by risk level and validate each step

The tooling exists to make this manageable — leverage GKE's built-in assessment and planning features rather than trying to script everything from scratch.