# GKE Upgrade Notification Triage System

This guide helps you categorize GKE notifications by urgency and determine which require immediate action versus which are informational.

## Notification Categories & Response Actions

### 🚨 **URGENT - Action Required Within Days**

**End of Support (EoS) Warnings**
- **Trigger:** "Your cluster will be automatically upgraded due to version end of support"
- **Timeline:** Usually 30-60 days before forced upgrade
- **Action Required:** 
  - Plan upgrade immediately or apply temporary "no upgrades" exclusion (max 30 days)
  - Consider migrating to Extended channel for longer support (24 months)
- **Commands:**
  ```bash
  # Check EoS timeline
  gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
  
  # Apply temporary deferral (max 30 days)
  gcloud container clusters update CLUSTER_NAME \
    --add-maintenance-exclusion-name="eos-deferral" \
    --add-maintenance-exclusion-start="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --add-maintenance-exclusion-end="$(date -u -d '+29 days' +%Y-%m-%dT%H:%M:%SZ)" \
    --add-maintenance-exclusion-scope=no_upgrades
  ```

**Critical Security Patches**
- **Trigger:** CVE notifications with "High" or "Critical" severity
- **Timeline:** Apply within 7-14 days
- **Action Required:** Allow auto-upgrade or manually trigger patch upgrade
- **Commands:**
  ```bash
  # Check if patch is already scheduled
  gcloud container clusters describe CLUSTER_NAME --region REGION \
    --format="value(maintenancePolicy)"
  ```

### ⚠️ **MEDIUM - Plan Within 2-4 Weeks**

**Scheduled Auto-Upgrade Notifications**
- **Trigger:** "Your cluster is scheduled to be automatically upgraded"
- **Timeline:** Usually 7-14 days advance notice
- **Action Options:**
  - **No action:** Let auto-upgrade proceed during maintenance window
  - **Defer:** Apply exclusion if timing conflicts with releases/holidays
  - **Accelerate:** Trigger manually in controlled window
- **Decision Matrix:**
  ```
  Production cluster + holiday season → Apply temporary exclusion
  Development cluster → Let auto-upgrade proceed
  Critical release week → Apply "no upgrades" exclusion
  Normal operations → No action needed (auto-upgrade is preferred)
  ```

**Deprecated API Usage Warnings**
- **Trigger:** "Your cluster uses APIs that will be removed"
- **Timeline:** Plan remediation before next minor version upgrade
- **Action Required:** Update manifests/operators to use supported APIs
- **Commands:**
  ```bash
  # Check deprecated API usage
  kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
  
  # Get detailed deprecation insights
  gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=REGION --project=PROJECT_ID
  ```

### 📋 **LOW - Informational/Long-term Planning**

**Version Availability Notifications**
- **Trigger:** "New Kubernetes version X.Y.Z is now available"
- **Timeline:** No immediate action needed
- **Use For:** Long-term planning, testing in dev environments
- **Action:** Add to upgrade backlog, test in lower environments first

**Release Channel Promotion**
- **Trigger:** "Version promoted from Rapid to Regular channel"
- **Timeline:** Informational only
- **Use For:** Understanding upgrade pipeline timing

**Maintenance Window Reminders**
- **Trigger:** "Upcoming maintenance window"
- **Timeline:** 24-48 hours before window
- **Action:** Ensure on-call coverage, validate monitoring

## Triage Workflow

### Step 1: Identify Notification Type
```bash
# Check current cluster status
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Look for these key indicators in the output:
# - endOfStandardSupportTimestamp (EoS warning)
# - autoUpgradeStatus (scheduled upgrade)
# - currentVersion vs minorTargetVersion (version gap)
```

### Step 2: Risk Assessment Matrix

| Cluster Type | EoS Warning | Security Patch | Auto-Upgrade | API Deprecation |
|-------------|-------------|----------------|--------------|-----------------|
| **Production** | 🚨 URGENT | ⚠️ MEDIUM | ⚠️ MEDIUM | ⚠️ MEDIUM |
| **Staging** | ⚠️ MEDIUM | 📋 LOW | 📋 LOW | ⚠️ MEDIUM |
| **Development** | 📋 LOW | 📋 LOW | 📋 LOW | 📋 LOW |

### Step 3: Response Actions by Priority

**🚨 URGENT Response (same day):**
1. Review notification details and timeline
2. Check if temporary exclusion is needed
3. Create upgrade plan or apply deferral
4. Notify stakeholders of required action

**⚠️ MEDIUM Response (within 1 week):**
1. Add to sprint/planning cycle
2. Schedule upgrade window
3. Prepare pre/post-upgrade checklists
4. Test in lower environment first

**📋 LOW Response (next planning cycle):**
1. Log in upgrade tracking system
2. Update long-term roadmap
3. Consider for next quarterly upgrade cycle

## Automated Notification Processing

### Email Filter Rules
Create email filters to auto-categorize GKE notifications:

```
Subject contains "end of support" OR "will be automatically upgraded"
→ Label: GKE-URGENT, Forward to: platform-team@company.com

Subject contains "security" AND "critical"
→ Label: GKE-URGENT

Subject contains "scheduled to be automatically upgraded"
→ Label: GKE-MEDIUM

Subject contains "version available" OR "promoted to"
→ Label: GKE-INFO, Auto-archive
```

### Cloud Monitoring Alerting Policy

Set up alerts for critical GKE events:

```bash
# Example policy for EoS warnings
gcloud alpha monitoring policies create --policy-from-file=- <<EOF
displayName: "GKE End of Support Warning"
conditions:
- displayName: "GKE cluster approaching EoS"
  conditionThreshold:
    filter: 'resource.type="gke_cluster"'
    comparison: COMPARISON_GREATER_THAN
    thresholdValue: 0
notification_channels: ["projects/PROJECT_ID/notificationChannels/CHANNEL_ID"]
EOF
```

## Recommended Controls by Environment

### Production Clusters
```bash
# Conservative auto-upgrade controls
gcloud container clusters update PROD_CLUSTER \
  --release-channel stable \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --maintenance-window-start "2024-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```
**Result:** Only CP security patches auto-apply. All minor/node upgrades require manual trigger.

### Staging Clusters
```bash
# Moderate auto-upgrade controls
gcloud container clusters update STAGING_CLUSTER \
  --release-channel regular \
  --maintenance-window-start "2024-01-01T01:00:00Z" \
  --maintenance-window-duration 6h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```
**Result:** Auto-upgrades with 1-day head start before production.

### Development Clusters
```bash
# Minimal controls - let GKE manage
gcloud container clusters update DEV_CLUSTER \
  --release-channel regular
```
**Result:** Full auto-upgrades with default timing.

## Escalation Matrix

| Notification Type | First Responder | Escalation (if no response in 24h) |
|-------------------|----------------|-----------------------------------|
| EoS Warning | Platform Team | Engineering Manager + SRE Lead |
| Critical Security | Security Team | CISO + Platform Team |
| Auto-Upgrade | Platform Team | Engineering Manager |
| API Deprecation | App Teams | Platform Team (if not resolved in 2 weeks) |

## Documentation Integration

### Runbook Links by Notification Type

**EoS Warnings → [Emergency Upgrade Runbook]**
- Pre-flight checks focused on compatibility
- Skip-level upgrade path planning
- Rollback procedures

**Security Patches → [Security Patch Runbook]**
- CVE impact assessment
- Patch-only upgrade validation
- Security scanning post-upgrade

**Scheduled Upgrades → [Standard Upgrade Runbook]**
- Full pre/post checklists
- Progressive rollout across environments
- Workload validation procedures

**API Deprecations → [API Migration Runbook]**
- Deprecated API discovery
- Manifest update procedures
- Operator upgrade coordination

This triage system transforms noisy GKE notifications into actionable workflows, ensuring critical issues get immediate attention while informational updates don't create alert fatigue.