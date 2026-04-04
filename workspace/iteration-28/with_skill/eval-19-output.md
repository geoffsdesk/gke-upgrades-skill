# GKE Upgrade Notification Triage System

Based on GKE's official notification types, here's a triage system to help you categorize and respond to upgrade notifications appropriately.

## Notification Categories & Actions

### 🚨 **URGENT - Immediate Action Required**

**Minor version at or near end of support**
- **What it means:** Your cluster's minor version is approaching End of Support (EoS)
- **Timeline:** Act within days to weeks before EoS date
- **Action required:** Plan and execute upgrade to supported version
- **Consequence of ignoring:** Forced upgrade to next minor version at EoS

```bash
# Check EoS timeline
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

### ⚠️ **HIGH PRIORITY - Plan Within 72 Hours**

**Scheduled upgrade notifications (Preview - March 2026)**
- **What it means:** Auto-upgrade will happen in 72 hours
- **Timeline:** 72-hour advance notice via Cloud Logging
- **Action options:**
  - Accept the upgrade (no action needed)
  - Apply temporary "no upgrades" exclusion to defer up to 30 days
  - Adjust maintenance window timing
- **Consequence of ignoring:** Auto-upgrade proceeds as scheduled

```bash
# Defer if needed (up to 30 days)
gcloud container clusters update CLUSTER_NAME \
  --add-maintenance-exclusion-name "defer-$(date +%Y%m%d)" \
  --add-maintenance-exclusion-start $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end $(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades
```

### 📊 **MEDIUM PRIORITY - Monitor & Plan**

**Upgrade available event**
- **What it means:** New version available in your release channel
- **Timeline:** No urgency - version becomes auto-upgrade target in 1-4 weeks
- **Action required:** Review release notes, plan testing in dev/staging
- **Consequence of ignoring:** Auto-upgrade will happen during maintenance window

**New patch change to new COS milestone during extended support**
- **What it means:** Patch with Container-Optimized OS update available (Extended channel only)
- **Timeline:** Plan within maintenance cycle
- **Action required:** Test compatibility, schedule upgrade
- **Consequence of ignoring:** Auto-upgrade during maintenance window

### ✅ **INFORMATIONAL - Monitor Only**

**Upgrade event (start)**
- **What it means:** Upgrade has begun on the cluster
- **Timeline:** Monitor for 1-4 hours until completion
- **Action required:** Watch for completion, validate workloads afterward
- **Consequence of ignoring:** None - informational only

**Disruption events during nodepool upgrade**
- **What it means:** PDB violations, eviction issues during node pool upgrades
- **Timeline:** Real-time during upgrade
- **Action required:** Monitor, intervene if upgrade stalls
- **Consequence of ignoring:** Upgrade may stall, requiring troubleshooting

## Triage Decision Tree

```
New GKE notification received
├── Contains "end of support" or "EoS"? 
│   └── YES → 🚨 URGENT: Check EoS date, plan upgrade immediately
├── Contains "scheduled" and mentions specific date?
│   └── YES → ⚠️ HIGH: 72h to decide - accept, defer, or reschedule
├── Contains "available" or "new version"?
│   └── YES → 📊 MEDIUM: Review release notes, plan testing
└── Contains "upgrade started" or "disruption"?
    └── YES → ✅ INFO: Monitor progress, validate after completion
```

## Recommended Response Runbook

### For End of Support Warnings

```bash
# 1. Check current EoS timeline
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# 2. Plan upgrade path (sequential minor versions)
# Current: 1.28 → Target: 1.31 = Upgrade 1.28→1.29→1.30→1.31

# 3. Apply temporary exclusion if needed during planning
gcloud container clusters update CLUSTER_NAME \
  --add-maintenance-exclusion-name "eos-planning" \
  --add-maintenance-exclusion-start $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end $(date -u -d '+14 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades
```

### For Scheduled Upgrade Notifications

```bash
# Option 1: Accept the upgrade (no action needed)
echo "Auto-upgrade will proceed as scheduled"

# Option 2: Defer the upgrade
gcloud container clusters update CLUSTER_NAME \
  --add-maintenance-exclusion-name "defer-maintenance" \
  --add-maintenance-exclusion-start $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end $(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades

# Option 3: Reschedule maintenance window
gcloud container clusters update CLUSTER_NAME \
  --maintenance-window-start "2026-01-18T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### For Upgrade Available Notifications

```bash
# 1. Review what's new
echo "Check GKE release notes: https://cloud.google.com/kubernetes-engine/docs/release-notes"

# 2. Check for deprecated APIs in your cluster
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# 3. Plan testing in dev environment first
# 4. No immediate action required - auto-upgrade will happen in maintenance window
```

## Notification Monitoring Setup

### Enable Scheduled Upgrade Notifications (Preview)
```bash
gcloud container clusters update CLUSTER_NAME \
  --enable-scheduled-upgrades \
  --region REGION
```

### Cloud Logging Query for All GKE Notifications
```
resource.type="gke_cluster"
(
  jsonPayload.message=~".*end of support.*" OR
  jsonPayload.message=~".*scheduled.*upgrade.*" OR
  jsonPayload.message=~".*upgrade.*available.*" OR
  protoPayload.metadata.operationType=~"(UPDATE_CLUSTER|UPGRADE_MASTER)"
)
```

### Pub/Sub Integration for Automated Responses
```bash
# Subscribe to cluster notifications
gcloud pubsub subscriptions create gke-upgrade-notifications \
  --topic=projects/PROJECT_ID/topics/gke-upgrades
```

## Best Practices for Notification Management

### 1. **Automate EoS Monitoring**
- Set up alerts 30 days before EoS dates
- Use `gcloud container clusters get-upgrade-info` in monitoring scripts
- Track EoS dates in your asset management system

### 2. **Standardize Response Times**
- EoS warnings: 48-hour response SLA
- Scheduled upgrades: 24-hour decision SLA  
- Available versions: Review within 1 week
- Disruption events: Real-time monitoring during upgrades

### 3. **Environment-Specific Handling**
- **Dev clusters:** Accept all auto-upgrades, minimal intervention
- **Staging clusters:** 7-day soak after dev, then auto-upgrade
- **Production clusters:** Manual approval for minor versions, auto-patch OK

### 4. **Integration with Change Management**
- Forward EoS warnings to change advisory board
- Log all maintenance exclusions in ticketing system
- Document upgrade decisions and outcomes

## Sample Alert Configurations

### Slack/Teams Integration
```yaml
# Example alerting logic
if notification.contains("end of support"):
    severity = "urgent"
    channel = "#platform-urgent"
    escalate = "oncall"
elif notification.contains("scheduled") and notification.contains("72"):
    severity = "high" 
    channel = "#platform-ops"
    escalate = "business_hours"
else:
    severity = "info"
    channel = "#platform-info"
    escalate = "none"
```

This triage system ensures you respond appropriately to each notification type while avoiding alert fatigue. The key is distinguishing between **actionable** notifications (EoS warnings, scheduled upgrades) and **informational** ones (upgrade started, available versions).