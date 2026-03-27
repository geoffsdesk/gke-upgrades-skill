# GKE Fleet Health Assessment & Recovery Plan

You're inheriting a classic "snowflake fleet" situation. The good news is GKE provides excellent self-service tools to assess your current state and create a systematic recovery plan. Here's your structured approach:

## Phase 1: Discovery & Assessment (Week 1-2)

### Fleet Inventory

First, get the complete picture across all projects:

```bash
# List all GKE clusters across projects
gcloud container clusters list --format="table(
  name,
  location,
  currentMasterVersion,
  status,
  releaseChannel.channel,
  autopilot.enabled
)" --verbosity=none

# For each cluster, get detailed version info
for cluster in $(gcloud container clusters list --format="value(name,location)"); do
  name=$(echo $cluster | cut -d' ' -f1)
  zone=$(echo $cluster | cut -d' ' -f2)
  echo "=== $name ($zone) ==="
  gcloud container clusters get-upgrade-info $name --region $zone
done
```

### Automated Health Assessment Tools

**GKE Recommender (your primary assessment tool):**
```bash
# Get all deprecation insights across projects
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=- \
  --project=PROJECT_ID \
  --format="table(
    name.segment(-1):label=CLUSTER,
    insightSubtype,
    severity,
    description
  )"

# Specific checks for version skew and EoS
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=- \
  --filter="insightSubtype:VERSION_SKEW OR insightSubtype:END_OF_SUPPORT"
```

**Deprecation Dashboard (Console):**
- Navigate to GKE → Insights tab
- Shows deprecated API usage, version issues, security recommendations
- Filterable by cluster, severity, issue type

**Fleet-wide version audit script:**
```bash
#!/bin/bash
# save as fleet-audit.sh

echo "Cluster,Location,Channel,CP_Version,EoS_Date,Node_Pools,Mixed_Versions,Deprecated_APIs"

for cluster in $(gcloud container clusters list --format="value(name,location)"); do
  name=$(echo $cluster | cut -d' ' -f1)
  zone=$(echo $cluster | cut -d' ' -f2)
  
  # Get cluster details
  info=$(gcloud container clusters describe $name --region $zone --format="value(
    releaseChannel.channel,
    currentMasterVersion,
    nodePools[].version.flatten()
  )")
  
  channel=$(echo $info | cut -d' ' -f1)
  cp_version=$(echo $info | cut -d' ' -f2)
  node_versions=$(echo $info | cut -d' ' -f3-)
  
  # Check for version skew
  unique_versions=$(echo $node_versions | tr ' ' '\n' | sort -u | wc -l)
  mixed=$([[ $unique_versions -gt 1 ]] && echo "YES" || echo "NO")
  
  # Check EoS (simplified - use get-upgrade-info for precise dates)
  eos_status="CHECK_MANUALLY"
  
  echo "$name,$zone,$channel,$cp_version,$eos_status,$unique_versions,$mixed,CHECK_INSIGHTS"
done
```

## Phase 2: Categorize & Prioritize (Week 2-3)

### Risk Classification Matrix

| Risk Level | Criteria | Action Priority |
|------------|----------|----------------|
| **Critical** | EoS version, deprecated APIs blocking auto-upgrade, "No channel" | Immediate (30 days) |
| **High** | Version skew >1 minor, security vulnerabilities, mixed node versions | 60 days |
| **Medium** | Suboptimal channel, missing maintenance controls | 90 days |
| **Low** | Optimization opportunities | Next quarter |

### Fleet Segmentation Strategy

**Recommended approach for inherited fleets:**

```bash
# Group 1: Quick wins (dev/test clusters)
# - Migrate to Regular channel immediately
# - Accept auto-upgrades with basic maintenance windows

# Group 2: Production clusters
# - Assess workload sensitivity
# - Plan staged migration to Stable or Extended channel
# - Implement proper maintenance exclusions

# Group 3: Legacy/snowflake clusters
# - Deep assessment required
# - May need recreation vs upgrade-in-place
# - Custom migration timeline
```

## Phase 3: Standardization Plan (Week 3-4)

### Target Architecture (recommend this as your end state)

**Standard Production Pattern:**
```bash
# Extended channel for maximum control
gcloud container clusters update CLUSTER_NAME \
  --release-channel extended \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --maintenance-window-start "2026-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA" \
  --maintenance-patch-version-disruption-interval=2592000s
```

**Standard Dev/Staging Pattern:**
```bash
# Regular channel with controlled timing
gcloud container clusters update CLUSTER_NAME \
  --release-channel regular \
  --maintenance-window-start "2026-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### Migration Decision Framework

For each cluster, decide:

**Upgrade-in-place when:**
- Current version is within 3 minors of latest
- No major deprecated API usage
- Workloads are containerized properly
- Cluster configuration is mostly standard

**Recreate when:**
- Version is 4+ minors behind (upgrade path too risky)
- Heavy deprecated API usage across many versions
- Non-standard cluster configuration (custom networks, etc.)
- Legacy workload patterns (many bare pods, no resource requests)

## Phase 4: Execution (Week 4+)

### Progressive Migration Plan

**Week 4-6: Quick wins (Group 1)**
```bash
# Migrate dev/test clusters to Regular channel
for cluster in $DEV_CLUSTERS; do
  gcloud container clusters update $cluster \
    --release-channel regular \
    --maintenance-window-start "2026-01-01T03:00:00Z" \
    --maintenance-window-duration 2h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
done
```

**Week 6-12: Production clusters (Group 2)**
```bash
# Example production migration sequence
# 1. Apply "no upgrades" exclusion (30-day protection)
gcloud container clusters update PROD_CLUSTER \
  --add-maintenance-exclusion-name "migration-freeze" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades

# 2. Migrate to Extended channel
gcloud container clusters update PROD_CLUSTER \
  --release-channel extended

# 3. Remove temporary exclusion, add permanent control
gcloud container clusters update PROD_CLUSTER \
  --remove-maintenance-exclusion-name "migration-freeze" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Week 12+: Legacy clusters (Group 3)**
- Case-by-case assessment
- Consider recreation for severely outdated clusters

## Self-Service Monitoring & Validation Tools

### Ongoing Health Monitoring

**Set up automated insights collection:**
```bash
#!/bin/bash
# daily-fleet-health.sh - run as cron job

# Check for new deprecation insights
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --filter="stateInfo.state=ACTIVE" \
  --format="csv(name.segment(-1),insightSubtype,severity,description)" \
  > daily-insights.csv

# Check clusters approaching EoS
for cluster in $(gcloud container clusters list --format="value(name,location)"); do
  name=$(echo $cluster | cut -d' ' -f1)
  zone=$(echo $cluster | cut -d' ' -f2)
  gcloud container clusters get-upgrade-info $name --region $zone \
    --format="csv(name,endOfStandardSupportTimestamp,autoUpgradeStatus)"
done > daily-eos-status.csv
```

**Notification setup:**
```bash
# Enable scheduled upgrade notifications (72h advance warning)
for cluster in $ALL_CLUSTERS; do
  gcloud container clusters update $cluster \
    --send-scheduled-upgrade-notifications
done
```

### Fleet-wide Policy Enforcement

**Terraform/Pulumi template for standardized clusters:**
```hcl
# Standard production cluster template
resource "google_container_cluster" "production" {
  release_channel {
    channel = "EXTENDED"
  }
  
  maintenance_policy {
    recurring_window {
      start_time = "2026-01-01T02:00:00Z"
      end_time   = "2026-01-01T06:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SA"
    }
  }
}
```

## Key Success Metrics

Track these metrics monthly:
- **Clusters on release channels:** Target 100% (vs "No channel")
- **Version skew issues:** Target 0 critical insights
- **Deprecated API usage:** Target 0 blocking insights
- **EoS approaching:** Target 60+ days runway minimum
- **Maintenance exclusion coverage:** Target 100% production clusters

## Common Pitfalls to Avoid

1. **Don't migrate all clusters to the same channel** — use dev→Regular, prod→Extended
2. **Don't remove "No channel" exclusions before adding release channel exclusions** — you'll lose upgrade control
3. **Don't ignore GPU driver compatibility** when upgrading GPU clusters
4. **Don't skip deprecation insight cleanup** — auto-upgrades pause when deprecated APIs are detected
5. **Don't chain multiple 30-day "no upgrades" exclusions** — use persistent exclusions for long-term control

## Emergency Procedures

**If you discover a cluster at immediate EoS risk:**
```bash
# Apply 30-day "no upgrades" exclusion for breathing room
gcloud container clusters update CLUSTER_NAME \
  --add-maintenance-exclusion-name "emergency-eos-protection" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades

# Then plan and execute upgrade within the 30-day window
```

Your timeline should be: 2 weeks assessment → 1 week planning → 1 month quick wins → 2 months production standardization. The GKE tools above will give you complete visibility into your current state and automate most of the discovery work.