# GKE Fleet Remediation Plan

Your situation is unfortunately common — inherited GKE fleets often accumulate technical debt over time. Here's a systematic approach to get your fleet healthy and establish good ongoing practices.

## Assessment Phase: Understanding Your Current State

### 1. Fleet inventory and health assessment

```bash
# Get comprehensive cluster inventory
gcloud container clusters list \
  --format="table(
    name,
    location,
    currentMasterVersion,
    releaseChannel.channel:label=CHANNEL,
    status,
    currentNodeCount,
    autopilot.enabled:label=AUTOPILOT
  )"

# For each cluster, get detailed upgrade info
for cluster in $(gcloud container clusters list --format="value(name,location)"); do
  name=$(echo $cluster | cut -d' ' -f1)
  location=$(echo $cluster | cut -d' ' -f2)
  echo "=== $name ($location) ==="
  gcloud container clusters get-upgrade-info $name --region $location 2>/dev/null || \
  gcloud container clusters get-upgrade-info $name --zone $location
done
```

### 2. GKE's built-in assessment tools

**GKE Deprecation Dashboard (Console):**
- Navigate to GKE → Clusters → [Select cluster] → Insights tab
- Shows deprecated API usage, version compatibility issues, and security recommendations
- Automatically detects blocking issues that would cause auto-upgrades to pause

**Recommender API (programmatic):**
```bash
# Get all deprecation and compatibility insights
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=us-central1 \
  --project=PROJECT_ID \
  --format="table(
    name.basename(),
    insightSubtype,
    severity,
    category,
    description
  )"
```

**Binary authorization vulnerabilities (if enabled):**
```bash
# Check for container image vulnerabilities
gcloud container binauthz attestors list
```

### 3. Cluster categorization matrix

Create a spreadsheet tracking:

| Cluster | Environment | Channel | Current Version | Target Version | EoS Date | Risk Level | Priority |
|---------|------------|---------|-----------------|----------------|----------|------------|----------|
| prod-us-1 | Production | No channel | 1.27.8 | 1.30.x | 2024-06-01 | HIGH | 1 |
| staging-eu | Staging | Regular | 1.29.2 | 1.30.x | 2025-01-15 | MEDIUM | 2 |

**Risk levels:**
- **CRITICAL:** EoS within 30 days, deprecated APIs detected
- **HIGH:** EoS within 90 days, >2 minor versions behind
- **MEDIUM:** On supported version but >1 minor behind current
- **LOW:** On current/recent version, good maintenance posture

## Remediation Strategy

### Phase 1: Stop the bleeding (Weeks 1-2)

**Priority 1 — Critical EoS clusters:**
```bash
# For clusters approaching EoS with deprecated APIs
# 1. Apply 30-day "no upgrades" exclusion to buy time
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "emergency-freeze" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -d '+30 days' -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades

# 2. Fix deprecated API usage immediately
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
# Address each deprecated API before exclusion expires
```

**Priority 2 — Migrate legacy "No channel" clusters:**
```bash
# Move to Regular channel (closest to legacy behavior)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular

# Or Extended channel if you need maximum control
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

### Phase 2: Establish control (Weeks 2-4)

**Set up maintenance windows fleet-wide:**
```bash
# Example: Weekend maintenance window
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-end "2024-01-06T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Configure maintenance exclusions for control:**
```bash
# "No minor or node upgrades" - allows CP security patches, blocks disruptive changes
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "controlled-upgrades" \
  --add-maintenance-exclusion-until-end-of-support \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### Phase 3: Version convergence (Weeks 4-8)

**Multi-environment channel strategy:**
- **Dev/Test:** Regular channel (gets updates ~1 week after Rapid)
- **Staging:** Regular channel (same as dev for testing)
- **Production:** Stable channel (gets updates ~2-3 weeks after Regular)

**Upgrade sequencing approach:**
1. Upgrade dev clusters first, soak for 1 week
2. Upgrade staging, run full test suite, soak for 1 week  
3. Upgrade production during scheduled maintenance windows

**Skip-level upgrades to catch up faster:**
```bash
# Instead of 1.27→1.28→1.29→1.30, do 1.27→1.29→1.30 (within 2-version skew)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.29.x-gke.xxx

# Wait for CP upgrade, then nodes (can skip levels too)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.29.x-gke.xxx
```

### Phase 4: Operational excellence (Weeks 8-12)

**Set up monitoring and alerting:**
```bash
# Enable scheduled upgrade notifications (72h advance warning)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --send-scheduled-upgrade-notifications

# Set up Cloud Logging alert for upgrade events
# Query: resource.type="gke_cluster" protoPayload.metadata.operationType=~"(UPDATE_CLUSTER|UPGRADE_MASTER)"
```

**Implement rollout sequencing for large fleets:**
```bash
# Configure dev→staging→prod sequence with soak times
gcloud container fleet clusterupgrade update \
  --project=PROJECT_ID \
  --upstream-fleet=dev-project-id \
  --default-upgrade-soaking=7d
```

## Self-Service Tools and Automation

### 1. GKE Release Schedule
**URL:** https://cloud.google.com/kubernetes-engine/docs/release-schedule
- Shows when versions become available in each channel
- Best-case auto-upgrade timing (actual may be later)
- End-of-support dates for planning

### 2. Upgrade Info API
```bash
# Programmatic access to upgrade status
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
# Returns: autoUpgradeStatus, EoS timestamps, target versions
```

### 3. GKE Recommender Integration
```bash
# Export all insights to CSV for spreadsheet analysis
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=LOCATION \
  --project=PROJECT_ID \
  --format=csv > gke-insights.csv
```

### 4. Fleet management with Terraform
```hcl
# Standardize cluster configuration across fleet
resource "google_container_cluster" "standard" {
  for_each = var.clusters
  
  name     = each.key
  location = each.value.location
  
  release_channel {
    channel = each.value.channel  # "REGULAR", "STABLE"
  }
  
  maintenance_policy {
    recurring_window {
      start_time = "2024-01-06T02:00:00Z"
      end_time   = "2024-01-06T06:00:00Z" 
      recurrence = "FREQ=WEEKLY;BYDAY=SA"
    }
  }
}
```

## Ongoing Fleet Health Practices

### 1. Weekly health checks
```bash
#!/bin/bash
# fleet-health-check.sh
echo "=== GKE Fleet Health Report ===" 
echo "Generated: $(date)"

for cluster in $(gcloud container clusters list --format="value(name,location)"); do
  name=$(echo $cluster | cut -d' ' -f1)
  location=$(echo $cluster | cut -d' ' -f2)
  
  version=$(gcloud container clusters describe $name --region $location --format="value(currentMasterVersion)")
  channel=$(gcloud container clusters describe $name --region $location --format="value(releaseChannel.channel)")
  
  echo "$name | $location | $channel | $version"
done
```

### 2. Proactive deprecation monitoring
- Set up alerts on GKE deprecation insights
- Run monthly scans for deprecated API usage
- Track Kubernetes upstream deprecation schedules

### 3. Version drift prevention
- Keep dev and prod clusters within 1 minor version
- Use "no minor" exclusions + manual minor upgrades to control timing
- Never let clusters fall >6 months behind without a plan

## Common Pitfalls to Avoid

1. **Don't default to "No channel"** — use release channels with exclusions for control
2. **Don't chain 30-day exclusions indefinitely** — accumulates security debt
3. **Don't upgrade prod first** — always validate in lower environments
4. **Don't ignore deprecated APIs** — they cause auto-upgrade pauses and emergency situations
5. **Don't assume weekend upgrades are safe** — validate your workload's maintenance window tolerance

## Success Metrics

**Short-term (3 months):**
- All clusters on supported versions (not EoS)
- All clusters on release channels (no "No channel")
- Deprecated API usage eliminated
- Maintenance windows configured fleet-wide

**Long-term (6+ months):**
- Version drift <2 minor versions between environments
- Auto-upgrades enabled with predictable timing
- Zero emergency/forced upgrades
- Upgrade-related incidents <1 per quarter

This systematic approach will transform your chaotic fleet into a well-managed, predictable infrastructure. Focus on stopping the bleeding first, then building sustainable practices for ongoing health.