# GKE Fleet Health Recovery Plan

You're facing a classic "inherited technical debt" scenario. Here's a systematic approach to assess, prioritize, and remediate your GKE fleet using GKE's built-in assessment tools.

## Phase 1: Assessment & Discovery (Week 1-2)

### Fleet Inventory & Health Assessment

**Use GKE's built-in assessment tools:**

```bash
# Get cluster inventory across all projects/regions
for project in $(gcloud projects list --format="value(projectId)"); do
  echo "=== Project: $project ==="
  gcloud container clusters list --project=$project --format="table(
    name,
    location,
    currentMasterVersion,
    releaseChannel.channel:label=CHANNEL,
    status,
    autopilot.enabled:label=AUTOPILOT
  )"
done > cluster-inventory.txt
```

**GKE Deprecation Insights Dashboard** (primary assessment tool):
- Console → Kubernetes Engine → Insights tab
- Shows deprecated API usage, version skew, EoS warnings across your entire fleet
- Prioritizes clusters by risk level (critical/high/medium/low)
- Export insights programmatically:

```bash
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=LOCATION \
  --project=PROJECT_ID \
  --format="table(
    name.basename(),
    insightSubtype,
    category,
    severity,
    targetResources[0].basename()
  )"
```

**Cluster upgrade readiness check:**
```bash
# Check auto-upgrade status and EoS dates for each cluster
gcloud container clusters get-upgrade-info CLUSTER_NAME \
  --region REGION \
  --format="yaml(
    autoUpgradeStatus,
    endOfStandardSupportTimestamp,
    endOfExtendedSupportTimestamp,
    minorTargetVersion,
    patchTargetVersion
  )"
```

### Risk Categorization Matrix

Create a spreadsheet with these columns:
- **Cluster Name/Project** 
- **Current Version** (how far behind latest?)
- **Channel** (No channel = highest risk)
- **EoS Date** (urgent if <30 days)
- **Deprecated APIs** (from insights dashboard)
- **Workload Criticality** (prod/staging/dev)
- **Risk Score** (Critical/High/Medium/Low)

**Risk scoring criteria:**
- **Critical:** No channel + EoS <30 days + prod workloads
- **High:** No channel + deprecated APIs + prod workloads  
- **Medium:** 3+ minor versions behind + prod workloads
- **Low:** Dev/staging clusters on release channels

## Phase 2: Emergency Stabilization (Week 2-3)

### Handle Critical & High Risk Clusters First

**For "No channel" clusters approaching EoS:**

1. **Migrate to Extended channel** (maximum flexibility, no forced minor upgrades):
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

2. **Apply "no minor or node upgrades" exclusion** for immediate control:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

This gives you up to 24 months of support while you plan proper upgrades.

**For clusters with deprecated API usage:**

1. **Check GKE deprecation insights** for the specific APIs
2. **Apply "no upgrades" exclusion** (30-day emergency brake):
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "api-remediation" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades
```
3. **Fix deprecated API usage** within the 30-day window

## Phase 3: Systematic Fleet Modernization (Week 3-8)

### Target State Architecture

**Recommended fleet configuration:**
- **Dev clusters:** Regular channel (balanced timing)
- **Staging clusters:** Regular channel  
- **Production clusters:** Stable or Regular channel (your choice based on risk tolerance)
- **All clusters:** Maintenance windows during off-peak hours
- **Conservative production:** "no minor or node upgrades" exclusion with manual minor upgrades

### Migration Strategy by Environment

**1. Start with dev/staging clusters** (lowest risk):
```bash
# Migrate to Regular channel
gcloud container clusters update DEV_CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular

# Set maintenance window for off-peak hours
gcloud container clusters update DEV_CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2026-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SUN"
```

**2. Production clusters** (use Extended channel for maximum control):
```bash
# Extended channel delays EoS enforcement, gives 24-month support
gcloud container clusters update PROD_CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --maintenance-window-start "2026-01-01T03:00:00Z" \
  --maintenance-window-duration 3h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

This configuration:
- Automatically applies security patches to control plane
- Blocks disruptive minor/node upgrades until you manually trigger them
- Provides 24 months of support (cost only during extended period)
- Perfect for inherited production workloads that need stability

### Fleet-wide Upgrade Orchestration

**For sophisticated teams managing 10+ clusters, configure rollout sequencing:**

```bash
# Create fleet memberships (lightweight, no overhead)
gcloud container fleet memberships register DEV_CLUSTER_NAME \
  --cluster=DEV_CLUSTER_NAME \
  --cluster-location=ZONE

# Configure upgrade sequence: dev → staging → prod with soak time
gcloud container fleet clusterupgrade update \
  --project=DEV_PROJECT_ID \
  --upstream-fleet=DEV_FLEET \
  --default-upgrade-soaking=48h

gcloud container fleet clusterupgrade update \
  --project=STAGING_PROJECT_ID \
  --upstream-fleet=STAGING_FLEET \
  --default-upgrade-soaking=72h
```

**Important:** Rollout sequencing only works when all clusters are on the **same release channel**. If you have dev=Regular, prod=Stable, sequencing can't orchestrate them.

## Phase 4: Process & Automation (Week 6+)

### Monitoring & Alerting Setup

**Enable scheduled upgrade notifications** (72-hour advance warning):
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --send-scheduled-upgrade-notifications
```

**Set up Cloud Logging alert policies:**
```sql
# Query for EoS warnings
resource.type="gke_cluster" 
AND protoPayload.metadata.operationType="UPDATE_CLUSTER"
AND severity="WARNING"
```

**Create deprecation insight monitoring:**
```bash
# Weekly check for new deprecated API usage
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=- \
  --project=PROJECT_ID \
  --filter="insightSubtype=DEPRECATED_API_USAGE"
```

### Standardized Upgrade Runbooks

Create environment-specific runbooks:

**Dev/Staging (auto-upgrade enabled):**
- Regular channel + maintenance windows
- Let auto-upgrades handle minor versions
- Manual intervention only for deprecated API fixes

**Production (controlled upgrades):**
- Extended channel + "no minor or node upgrades" exclusion
- Manual minor upgrades during scheduled maintenance windows
- Required: staging validation before production upgrade

### Fleet Health Dashboard

Track these KPIs monthly:
- **Version freshness:** % of clusters within 1 minor version of latest
- **Channel compliance:** % of clusters on release channels (vs "No channel")
- **EoS risk:** # of clusters <90 days from End of Support
- **Deprecated API debt:** # of clusters with deprecated API usage
- **Auto-upgrade effectiveness:** % of upgrades that complete without intervention

## Key Success Metrics

**30-day targets:**
- [ ] Zero clusters in "No channel" configuration
- [ ] Zero clusters <30 days from EoS 
- [ ] All deprecated API usage remediated
- [ ] Maintenance windows configured on all clusters

**90-day targets:**
- [ ] All clusters on appropriate release channels
- [ ] Rollout sequencing configured (if applicable)
- [ ] Standardized upgrade runbooks for each environment type
- [ ] Monitoring/alerting for upgrade events

**Ongoing hygiene:**
- Monthly fleet health reviews using GKE insights dashboard
- Quarterly major upgrade planning sessions
- Proactive deprecated API monitoring and remediation

## Emergency Procedures

**If a cluster gets force-upgraded due to EoS:**
1. Don't panic — the cluster remains functional
2. Check for workload issues caused by API version changes
3. Apply maintenance exclusions to prevent further auto-upgrades
4. Fix any deprecated API usage that caused the original delay
5. Document lessons learned and update your monitoring

**Cost optimization during remediation:**
- Extended channel costs only apply during the extended support period (after standard 14 months)
- "No minor or node upgrades" exclusions don't incur extra costs
- Consider cluster consolidation if you discover underutilized dev/staging clusters

This systematic approach leverages GKE's built-in assessment tools to give you visibility into your fleet's health, then provides a prioritized path to get everything into a well-managed state. The Extended channel + maintenance exclusions combination is particularly valuable for inherited production workloads that need maximum control during the stabilization period.