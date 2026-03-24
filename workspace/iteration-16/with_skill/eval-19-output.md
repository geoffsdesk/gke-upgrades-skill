# GKE Upgrade Notification Triage System

## Notification Types & Response Matrix

| Notification Type | Urgency | Action Required | Timeline | Response |
|------------------|---------|----------------|----------|----------|
| **Auto-upgrade scheduled** | Medium | Optional | 72h before upgrade | Review/exclude if needed |
| **Security patch available** | High | Plan upgrade | 7-14 days | Test → deploy quickly |
| **End-of-Support (EoS) warning** | Critical | Mandatory | 30-60 days | Immediate planning |
| **New version available** | Low | Informational | No deadline | Update roadmap only |
| **Deprecated API detected** | High | Fix before upgrade | ASAP | Auto-upgrades paused |
| **Upgrade failure/retry** | Critical | Immediate | Now | Diagnose and fix |

## Triage Decision Tree

```
1. Does the subject contain "End of Support" or "EoS"?
   → YES: Priority 1 (Critical) - Start upgrade planning immediately
   → NO: Continue to step 2

2. Does the subject contain "security" or "CVE"?
   → YES: Priority 2 (High) - Plan security upgrade within 7-14 days
   → NO: Continue to step 3

3. Does the subject contain "auto-upgrade scheduled" or "maintenance"?
   → YES: Priority 3 (Medium) - Review in next 24-48h, exclude if needed
   → NO: Continue to step 4

4. Does the subject contain "deprecated API" or "upgrade blocked"?
   → YES: Priority 2 (High) - Fix API issues to unblock auto-upgrades
   → NO: Continue to step 5

5. Does the subject contain "failed" or "retry"?
   → YES: Priority 1 (Critical) - Diagnose stuck upgrade immediately
   → NO: Priority 4 (Low) - Informational, update roadmap
```

## Response Playbooks by Priority

### Priority 1: Critical (EoS warnings, upgrade failures)

**EoS Warnings:**
```bash
# Check which clusters are affected
gcloud container clusters list \
  --format="table(name,location,currentMasterVersion,releaseChannel.channel)" \
  --filter="currentMasterVersion:VERSION_FROM_NOTIFICATION"

# Check auto-upgrade target and timeline
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Immediate actions:
# 1. Schedule upgrade planning meeting within 48h
# 2. Identify test/staging clusters for validation
# 3. Check deprecated API usage
# 4. Consider Extended channel migration for more time
```

**Upgrade Failures:**
```bash
# Check operation status
gcloud container operations list --cluster CLUSTER_NAME --region REGION --limit=5

# Diagnose common issues
kubectl get pdb -A | grep "0.*0"  # PDBs blocking drain
kubectl get pods -A | grep Pending  # Resource constraints
kubectl get events -A --field-selector type=Warning | tail -20
```

### Priority 2: High (Security patches, deprecated APIs)

**Security Patches:**
- **Timeline:** Test within 3-5 days, deploy to production within 7-14 days
- **Validation:** Deploy to dev/staging first, run security scans
- **Rollout:** Use maintenance windows, consider accelerated patches for critical CVEs

**Deprecated API Detection:**
```bash
# Comprehensive API usage check
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# GKE recommender insights
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=REGION \
    --project=PROJECT_ID
```

### Priority 3: Medium (Scheduled auto-upgrades)

**Review within 24-48h:**
1. Check if upgrade timing conflicts with releases/events
2. Verify maintenance windows are appropriate
3. Apply temporary exclusion if needed:

```bash
# Apply "no upgrades" exclusion for emergency freeze
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "emergency-freeze-$(date +%Y%m%d)" \
  --add-maintenance-exclusion-start-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-end-time "$(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-scope no_upgrades
```

### Priority 4: Low (Version availability, informational)

**No immediate action required:**
- Update internal roadmaps and version tracking
- Note new features for future planning
- File for quarterly upgrade planning sessions

## Notification Setup & Filtering

### Enable scheduled upgrade notifications (72h advance warning)
```bash
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --send-scheduled-upgrade-notifications
```

### Cloud Logging filters for different notification types

**EoS warnings:**
```
resource.type="gke_cluster"
jsonPayload.message:("end of support" OR "EoS")
severity>=WARNING
```

**Auto-upgrade scheduled:**
```
resource.type="gke_cluster" 
protoPayload.methodName="google.container.v1.ClusterManager.UpdateCluster"
protoPayload.metadata.operationType="UPGRADE_MASTER"
```

**Security-related upgrades:**
```
resource.type="gke_cluster"
(jsonPayload.message:("security" OR "CVE") OR labels."gke.googleapis.com/security-update"="true")
```

### Email alerting setup
```bash
# Create notification channel
gcloud alpha monitoring channels create \
    --notification-content-type=email \
    --channel-config='{"emailAddress":"YOUR-TEAM@company.com"}' \
    --display-name="GKE Upgrades Team"

# Create alerting policy for critical notifications
gcloud alpha monitoring policies create \
    --notification-channels=NOTIFICATION_CHANNEL_ID \
    --display-name="GKE Critical Upgrade Alerts" \
    --condition-filter='resource.type="gke_cluster"' \
    --condition-trigger-count=1
```

## Team Workflows

### Weekly Triage Meeting (30 min)
- Review all Priority 2+ notifications from past week
- Plan upcoming maintenance windows
- Check cluster version drift across environments
- Update upgrade roadmap

### Monthly Planning Session (60 min)
- Review upcoming EoS dates (next 6 months)
- Plan major version upgrades
- Evaluate release channel strategy
- Review notification effectiveness

### Quarterly Review
- Analyze upgrade success rates and timings
- Adjust notification thresholds
- Update runbooks based on lessons learned
- Review channel strategy (Rapid/Regular/Stable/Extended)

## Notification Fatigue Prevention

### Consolidate similar notifications
- Group by cluster and time window
- Use Cloud Logging aggregation instead of per-cluster emails
- Set up daily/weekly digest emails rather than real-time alerts for low-priority items

### Focus on actionable items
- **Never alert on:** "New version available in Rapid channel" (too early)
- **Always alert on:** EoS warnings, security patches, scheduled upgrades
- **Context-dependent:** Version availability in Regular/Stable (only if you're behind)

### Sample notification rules
```bash
# High-priority: EoS within 60 days
resource.type="gke_cluster"
jsonPayload.message:"end of support"
jsonPayload.daysUntilEoS<=60

# Medium-priority: Auto-upgrade in next 7 days  
resource.type="gke_cluster"
protoPayload.operationType="UPGRADE_MASTER"
timestamp>="2024-01-01" AND timestamp<="2024-01-08"

# Low-priority: Version available (suppress for Rapid channel)
resource.type="gke_cluster"
jsonPayload.channel!="RAPID"
jsonPayload.message:"version available"
```

## Key Principles

1. **EoS notifications are never optional** — these trigger mandatory upgrades
2. **Security patches need rapid response** — test quickly, deploy within 2 weeks
3. **Scheduled auto-upgrades can be deferred** — but need active decision within 72h
4. **Version availability is usually informational** — unless you're significantly behind
5. **Failed upgrades need immediate attention** — they often indicate broader cluster issues

This triage system ensures your team responds appropriately to each notification type without getting overwhelmed by upgrade noise.