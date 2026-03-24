# GKE Fleet Health Assessment & Modernization Plan

You've inherited a classic "snowflake fleet" — clusters with frozen versions, inconsistent channels, and accumulated technical debt. Here's how to systematically assess and modernize your GKE estate using Google's self-service tools.

## Phase 1: Discovery & Assessment (Week 1-2)

### Self-service assessment tools

**1. GKE Fleet Management Dashboard**
```bash
# Enable fleet management for unified view
gcloud services enable gkehub.googleapis.com
gcloud container fleet memberships register CLUSTER_NAME \
  --gke-cluster=LOCATION/CLUSTER_NAME \
  --enable-workload-identity

# View fleet-wide status
gcloud container fleet memberships list
```

**2. Deprecation Insights Dashboard**
- Navigate to GKE → Insights tab in Cloud Console
- Shows fleet-wide deprecated API usage, version skew, and security issues
- Programmatic access:
```bash
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=LOCATION \
  --project=PROJECT_ID \
  --filter="category.displayName:Kubernetes"
```

**3. Fleet inventory script**
```bash
#!/bin/bash
# Generate fleet health report
echo "Cluster,Zone,Channel,Control_Plane_Version,Node_Versions,EoS_Status,Last_Upgrade"

for cluster in $(gcloud container clusters list --format="value(name,zone)"); do
  name=$(echo $cluster | cut -d' ' -f1)
  zone=$(echo $cluster | cut -d' ' -f2)
  
  # Get cluster details
  gcloud container clusters describe $name --zone $zone \
    --format="csv[no-heading](
      name,
      zone,
      releaseChannel.channel,
      currentMasterVersion,
      nodePools[].version.list():label=NODE_VERSIONS,
      status,
      updateTime
    )"
done > fleet-inventory.csv
```

**4. Version compatibility check**
```bash
# Check version skew across fleet
for cluster in $(gcloud container clusters list --format="value(name,zone)"); do
  name=$(echo $cluster | cut -d' ' -f1)
  zone=$(echo $cluster | cut -d' ' -f2)
  
  echo "=== $name ==="
  gcloud container clusters get-upgrade-info $name --zone $zone \
    --format="table(
      autoUpgradeStatus,
      minorTargetVersion,
      patchTargetVersion,
      endOfStandardSupportTimestamp,
      endOfExtendedSupportTimestamp
    )"
done
```

### What to look for in your assessment

**Red flags (immediate attention needed):**
- Clusters on versions reaching End of Support within 3 months
- Version skew >2 minor versions between control plane and nodes
- "No channel" clusters (legacy configuration)
- Deprecated API usage blocking auto-upgrades
- PDB violations preventing upgrades

**Yellow flags (plan for next quarter):**
- Inconsistent channels across environments (dev=Rapid, prod=Stable causes drift)
- No maintenance windows configured
- Missing PDBs on stateful workloads
- Overly restrictive maintenance exclusions

## Phase 2: Triage & Prioritization (Week 2-3)

### Risk-based prioritization matrix

| Priority | Criteria | Action Timeline |
|----------|----------|-----------------|
| **P0 (Immediate)** | EoS within 30 days, security vulnerabilities | This week |
| **P1 (High)** | EoS within 3 months, deprecated APIs blocking upgrades | Next 2 weeks |
| **P2 (Medium)** | Version skew, "No channel" migration needed | Next month |
| **P3 (Low)** | Channel standardization, maintenance window optimization | Next quarter |

### Emergency EoS handling

For clusters approaching End of Support:

**Option A — Emergency upgrade (if workloads are resilient):**
```bash
# Apply temporary "no upgrades" exclusion to buy 30 days
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "emergency-planning" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time $(date -u -d '+30 days' +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_upgrades
```

**Option B — Extended channel migration (for compliance/slow-moving clusters):**
```bash
# Migrate to Extended channel for up to 24 months support (1.27+)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

## Phase 3: Standardization Strategy

### Target state architecture

**Recommended channel strategy:**
- **Dev/Test environments:** Regular channel (balanced cadence)
- **Staging:** Regular channel (same as dev for consistency)
- **Production:** Regular or Stable channel + maintenance controls
- **Compliance/regulated:** Extended channel + strict maintenance exclusions

**Why avoid different channels per environment:**
- Version drift is inevitable — dev on Rapid (1.32) while prod on Stable (1.30)
- No rollout sequencing possible across different channels
- Different upgrade cadences make coordination impossible

**Better approach — same channel with upgrade controls:**
```bash
# All environments on Regular channel
# Use maintenance exclusions to control production upgrades
gcloud container clusters update PROD_CLUSTER \
  --zone ZONE \
  --release-channel regular \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

### "No channel" migration plan

**Step 1 — Assessment:**
```bash
# List all "No channel" clusters
gcloud container clusters list \
  --format="table(name, zone, releaseChannel.channel)" \
  --filter="releaseChannel.channel:NULL"
```

**Step 2 — Migration with safety controls:**
```bash
# Add temporary freeze before migration
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time $(date -u -d '+30 days' +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_upgrades

# Migrate to Regular channel (closest to legacy behavior)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular

# Replace with persistent exclusion for production clusters
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion "channel-migration" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Phase 4: Operational Excellence

### Fleet-wide maintenance windows

**Production cluster template:**
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2026-01-04T03:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA" \
  --maintenance-patch-version-disruption-interval=30d \
  --maintenance-minor-version-disruption-interval=60d
```

**Development cluster template:**
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2026-01-01T02:00:00Z" \
  --maintenance-window-duration 6h \
  --maintenance-window-recurrence "FREQ=DAILY" \
  --maintenance-patch-version-disruption-interval=7d
```

### Monitoring & alerting setup

**1. Scheduled upgrade notifications (Preview - March 2026):**
```bash
# Enable 72-hour advance notifications
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --send-scheduled-upgrade-notifications
```

**2. Cloud Logging alert policies:**
```bash
# Create alert for EoS warnings
gcloud logging policies create \
  --policy-from-file=eod-warning-policy.yaml
```

Policy file example:
```yaml
displayName: "GKE EoS Warning"
conditions:
- displayName: "Version approaching EoS"
  conditionThreshold:
    filter: |
      resource.type="gke_cluster"
      protoPayload.metadata.operationType="UPGRADE_MASTER"
      protoPayload.metadata.upgradeEvent.resourceType="MASTER"
    comparison: COMPARISON_EQUAL
    thresholdValue: 1
```

**3. Fleet health dashboard query:**
```sql
-- Use in Cloud Monitoring or export to BigQuery
SELECT
  resource.labels.cluster_name,
  resource.labels.location,
  jsonPayload.currentMasterVersion,
  jsonPayload.releaseChannel,
  timestamp
FROM `PROJECT.dataset.gke_logs`
WHERE resource.type = "gke_cluster"
  AND jsonPayload.operationType = "UPDATE_CLUSTER"
ORDER BY timestamp DESC
```

## Phase 5: Automation & GitOps

### Infrastructure as Code templates

**Terraform module for standardized clusters:**
```hcl
module "gke_cluster" {
  source = "./modules/gke-standard"
  
  name     = var.cluster_name
  location = var.location
  
  # Standardized configuration
  release_channel         = "REGULAR"
  maintenance_start_time  = "03:00"
  maintenance_recurrence  = "FREQ=WEEKLY;BYDAY=SA"
  
  # Environment-specific overrides
  maintenance_exclusions = var.environment == "prod" ? [{
    name  = "prod-freeze"
    scope = "NO_MINOR_OR_NODE_UPGRADES"
  }] : []
}
```

### Fleet upgrade orchestration

**For sophisticated teams with 10+ clusters:**
```bash
# Enable rollout sequencing
gcloud container fleet clusterupgrade update \
  --project=PROJECT_ID \
  --upstream-fleet=DEV_FLEET_PROJECT \
  --default-upgrade-soaking=7d
```

**For most teams — simpler approach:**
Use different maintenance windows to stagger upgrades:
- Dev: Daily 2-8 AM
- Staging: Weekly Saturday 1-7 AM  
- Prod: Weekly Saturday 3-7 AM (with "no minor" exclusion + manual triggers)

## Self-Service Tools Summary

| Tool | Purpose | Access Method |
|------|---------|---------------|
| **GKE Insights Dashboard** | Deprecated APIs, version skew, security issues | Console → GKE → Insights |
| **Fleet Management** | Multi-cluster inventory and operations | `gcloud container fleet` |
| **Upgrade Info API** | Auto-upgrade targets, EoS dates | `gcloud container clusters get-upgrade-info` |
| **Release Schedule** | Version availability timeline | [GKE Release Schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) |
| **Recommender API** | Programmatic insights and recommendations | `gcloud recommender insights list` |
| **Cloud Monitoring** | Fleet health metrics and alerting | Console → Monitoring → Dashboards |

## Success Metrics

Track these KPIs monthly:
- **Version currency:** % clusters within 2 minor versions of latest
- **Channel standardization:** % clusters on appropriate release channels  
- **EoS risk:** # clusters approaching End of Support within 90 days
- **Deprecated API usage:** # insights flagging deprecated APIs
- **Upgrade velocity:** Average time from version availability to deployment

## Common Pitfalls to Avoid

1. **Don't rush the assessment phase** — understanding your current state prevents breaking production
2. **Don't migrate all clusters simultaneously** — stagger "No channel" → release channel migrations
3. **Don't ignore deprecated APIs** — they cause auto-upgrades to pause, creating EoS risk
4. **Don't use different channels as your primary environment segregation** — use same channel + exclusions
5. **Don't disable auto-upgrades permanently** — use maintenance exclusions with time bounds instead

This plan takes 4-6 weeks to execute fully but gets you from "inherited chaos" to "well-managed fleet" with minimal production risk. Start with the assessment tools to understand what you're working with, then tackle the highest-risk clusters first.