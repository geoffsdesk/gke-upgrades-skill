# GKE Upgrade Notification Triage System

## Notification Types & Action Matrix

| Notification Type | Urgency | Action Required | Timeline | Who Handles |
|------------------|---------|-----------------|----------|-------------|
| **Security patch available** | 🟡 Medium | Monitor auto-upgrade | Auto-applied within days-weeks | Platform team awareness |
| **Auto-upgrade scheduled (72h notice)** | 🟢 Low | Optional: prepare/exclude | 72 hours | Platform team |
| **End of Support (EoS) warning** | 🔴 High | Plan upgrade immediately | 30-90 days before EoS | Platform + app teams |
| **New minor version available** | 🟢 Low | Plan for next cycle | No immediate action | Platform team |
| **Deprecated API detected** | 🔴 High | Fix immediately | Auto-upgrades paused until fixed | App teams |
| **Upgrade failed/stuck** | 🔴 High | Investigate and resolve | Immediate | Platform team |

## Triage Decision Tree

```
1. Does the notification mention "End of Support" or "deprecated API"?
   YES → 🔴 HIGH PRIORITY - Take immediate action
   NO → Continue to #2

2. Does it say "auto-upgrade scheduled" with a specific date?
   YES → 🟡 MEDIUM - Review and optionally prepare
   NO → Continue to #3

3. Does it mention "available" or "new version"?
   YES → 🟢 LOW - Informational, plan for future
   NO → Continue to #4

4. Does it mention "failed" or "stuck"?
   YES → 🔴 HIGH PRIORITY - Immediate troubleshooting needed
   NO → 🟢 LOW - General informational
```

## Action Playbooks

### 🔴 HIGH PRIORITY: End of Support (EoS) Warning

**Sample notification:** "Your GKE cluster will be auto-upgraded from 1.28.x because it reaches End of Support on YYYY-MM-DD"

**Actions:**
```bash
# Check all clusters approaching EoS
gcloud container clusters list --format="table(name,location,currentMasterVersion,releaseChannel.channel)"

# Check auto-upgrade targets and EoS dates
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Options to handle:
# 1. Let auto-upgrade happen (recommended for most clusters)
# 2. Manually upgrade before auto-upgrade kicks in
# 3. Apply temporary "no upgrades" exclusion (30 days max)
# 4. Migrate to Extended channel for longer support (1.27+ only)
```

**Timeline:** Act within 2-4 weeks of notification. EoS auto-upgrades are enforced and cannot be permanently avoided.

### 🔴 HIGH PRIORITY: Deprecated API Detected

**Sample notification:** "Auto-upgrades paused due to deprecated API usage in cluster CLUSTER_NAME"

**Actions:**
```bash
# Find deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Get GKE deprecation insights
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=LOCATION \
    --project=PROJECT_ID \
    --filter="category:SECURITY"

# Check specific deprecated APIs in your workloads
kubectl get deployments,statefulsets,daemonsets -A -o yaml | grep -i "apiVersion.*v1beta"
```

**Timeline:** Fix immediately. Auto-upgrades remain paused until resolved.

### 🟡 MEDIUM: Auto-upgrade Scheduled (72h notice)

**Sample notification:** "Your cluster CLUSTER_NAME is scheduled for auto-upgrade on YYYY-MM-DD between HH:MM-HH:MM"

**Decision points:**
- **Let it proceed:** Most common choice. Ensure monitoring is active.
- **Apply temporary exclusion:** If you have a critical deployment this week.
- **Manually upgrade early:** If you want to control exact timing.

**Actions if proceeding:**
```bash
# Verify current cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed

# Ensure monitoring/alerting active
# Brief team that upgrade is coming
# No other action needed - GKE handles it
```

**Actions if excluding:**
```bash
# Apply 30-day "no upgrades" exclusion
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "critical-period-$(date +%Y%m%d)" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades
```

### 🟢 LOW PRIORITY: New Version Available

**Sample notification:** "Kubernetes 1.32 is now available in the Regular channel"

**Actions:**
- Update internal documentation with new version availability
- Plan testing in dev/staging environments for next upgrade cycle
- Review release notes for new features or breaking changes
- No immediate action required

### 🔴 HIGH PRIORITY: Upgrade Failed/Stuck

**Sample notification:** "Node pool upgrade failed" or operations stuck >4 hours

**Immediate actions:**
```bash
# Check operation status
gcloud container operations list --cluster CLUSTER_NAME --region REGION --limit=3

# Diagnose common issues
kubectl get pdb -A -o wide  # Check for blocking PDBs
kubectl get pods -A | grep -E "Pending|Terminating|CrashLoop"
kubectl get events -A --field-selector reason=FailedScheduling
```

Follow the [troubleshooting runbook](troubleshooting.md) for systematic diagnosis.

## Notification Management Setup

### Configure Cloud Logging notifications
```bash
# Create log-based alert for high-priority notifications
gcloud alpha logging sinks create gke-upgrade-alerts \
  pubsub.googleapis.com/projects/PROJECT_ID/topics/gke-alerts \
  --log-filter='resource.type="gke_cluster" AND 
               (jsonPayload.message=~"End of Support" OR 
                jsonPayload.message=~"deprecated API" OR
                jsonPayload.message=~"upgrade.*failed")'
```

### Email filtering rules

Set up email filters to automatically tag/route notifications:

- **Subject contains:** "End of Support" → Label: GKE-HIGH-PRIORITY, Forward to: platform-team
- **Subject contains:** "deprecated API" → Label: GKE-HIGH-PRIORITY, Forward to: app-teams  
- **Subject contains:** "scheduled for auto-upgrade" → Label: GKE-MEDIUM-PRIORITY
- **Subject contains:** "available in" → Label: GKE-LOW-PRIORITY, Auto-archive after reading

## Team Responsibilities

### Platform Team (SRE/DevOps)
- **Monitor:** All upgrade notifications
- **Handle:** Auto-upgrade scheduling, maintenance windows, cluster health
- **Escalate:** Deprecated API issues to application teams
- **Own:** Upgrade failure troubleshooting

### Application Teams  
- **Monitor:** Deprecated API notifications for their services
- **Handle:** Fixing deprecated API usage in their workloads
- **Support:** Testing during planned upgrade cycles

### Management/Leadership
- **Receive:** Summary reports on upgrade status
- **Decide:** Resource allocation for major upgrade projects
- **Approve:** Maintenance exclusions that affect business operations

## Weekly Upgrade Status Report Template

```
GKE Upgrade Status - Week of YYYY-MM-DD

🔴 High Priority Items:
- [ ] EoS clusters: X clusters need upgrade by DATE
- [ ] Deprecated APIs: X workloads blocking auto-upgrades
- [ ] Failed upgrades: X clusters need investigation

🟡 Medium Priority Items:
- [ ] Scheduled auto-upgrades this week: X clusters
- [ ] Maintenance exclusions expiring: X clusters

🟢 Low Priority/Informational:
- [ ] New versions available: K8s X.XX in CHANNEL
- [ ] Successfully upgraded: X clusters this week

Next Actions:
- ...
```

## Recommended Notification Settings

**Enable these notifications:**
- Scheduled upgrade notifications (72h advance notice)
- End of Support warnings
- Deprecated API detection
- Upgrade operation failures

**Consider disabling:**
- "New version available" for Rapid channel (too frequent)
- Patch-level upgrade completions (unless required for compliance)

**Configure notification frequency:**
- EoS warnings: First notification at 90 days, then weekly reminders
- Deprecated APIs: Daily until resolved
- Auto-upgrade schedules: 72h and 24h advance notice

This triage system ensures critical issues get immediate attention while preventing notification fatigue from routine informational updates.