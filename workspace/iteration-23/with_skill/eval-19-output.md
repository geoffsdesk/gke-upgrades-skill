# GKE Upgrade Notification Triage System

Here's a decision framework to classify and respond to different GKE upgrade notifications effectively.

## Notification Types & Action Matrix

| Notification Type | Urgency | Action Required | Timeline | Owner |
|-------------------|---------|-----------------|----------|--------|
| **Security patch available** | HIGH | Review + Plan | 7-14 days | Security team |
| **Auto-upgrade scheduled (72h notice)** | MEDIUM | Review + Defer if needed | 72 hours | Platform team |
| **Version available** | LOW | Plan for next cycle | Next maintenance window | Platform team |
| **End-of-life warning** | HIGH (30d) / CRITICAL (7d) | Immediate upgrade planning | Based on timeline | Platform team + Management |
| **Deprecated API detected** | HIGH | Fix before upgrade | Before next auto-upgrade | App teams |
| **Auto-upgrade completed** | INFO | Validate cluster health | 24 hours | Platform team |

## Triage Decision Tree

### 1. Security Patch Available
**Sample notification:** "Security patch 1.29.8-gke.1031000 is now available"

```
✅ ALWAYS ACT
• Review CVE details in GKE release notes
• Check if patch is in your release channel
• Plan upgrade within 7-14 days (sooner for critical CVEs)
• Test in staging first
• Monitor for auto-upgrade if on release channel
```

**Commands:**
```bash
# Check if patch is available in your channel
gcloud container get-server-config --zone ZONE --format="yaml(channels)"

# Check current auto-upgrade target
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

### 2. Auto-upgrade Scheduled (72h advance notice)
**Sample notification:** "Cluster will be auto-upgraded to 1.29.8 on 2024-03-15 between 02:00-06:00 UTC"

**Decision criteria:**
- **DEFER if:** Active deployment freeze, critical business event, insufficient testing
- **ALLOW if:** Patch-only upgrade, tested in staging, maintenance window acceptable

**Defer commands (if needed):**
```bash
# Apply temporary 30-day "no upgrades" exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "business-freeze" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time $(date -u -d "+30 days" +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_upgrades
```

### 3. Version Available
**Sample notification:** "Kubernetes 1.30 is now available in Regular channel"

```
📋 PLAN FOR NEXT CYCLE
• Add to upgrade backlog
• Schedule staging validation
• Review breaking changes in release notes
• No immediate action required
```

### 4. End-of-Life Warning
**Sample notification:** "Version 1.27 reaches end-of-support on 2024-04-01"

**Timeline-based response:**
- **90+ days:** Add to quarterly planning
- **30-60 days:** HIGH priority - begin upgrade planning
- **7-30 days:** CRITICAL - accelerate upgrade timeline
- **<7 days:** EMERGENCY - forced upgrade imminent

**Emergency response (<7 days to EoS):**
```bash
# Check EoS timeline
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Consider Extended channel for more time (if available)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

### 5. Deprecated API Detected
**Sample notification:** "Cluster uses deprecated APIs that will be removed in Kubernetes 1.30"

```
🚨 BLOCK AUTO-UPGRADES UNTIL FIXED
• GKE automatically pauses auto-upgrades when deprecated APIs are detected
• Check deprecation insights dashboard
• Coordinate with app teams to update manifests
• Do not manually override the pause without fixing APIs first
```

**Diagnosis commands:**
```bash
# Check deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Check GKE deprecation insights
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=LOCATION \
  --project=PROJECT_ID
```

## Notification Configuration Best Practices

### Enable the right notifications
```bash
# Enable 72h scheduled upgrade notifications (preview)
gcloud container clusters update CLUSTER_NAME \
  --send-scheduled-upgrade-notifications

# Subscribe to cluster notifications via Pub/Sub
gcloud pubsub subscriptions create gke-cluster-notifications \
  --topic projects/PROJECT_ID/topics/gke-cluster-notifications
```

### Cloud Logging queries for different notification types

**Security patches available:**
```
resource.type="gke_cluster"
protoPayload.methodName="google.container.v1.ClusterManager.UpdateCluster"
protoPayload.request.update.desiredNodeVersion:"security"
```

**Auto-upgrade scheduled:**
```
resource.type="gke_cluster" 
jsonPayload.eventType="UPGRADE_AVAILABLE"
jsonPayload.currentVersion != jsonPayload.targetVersion
```

**Deprecated API warnings:**
```
resource.type="gke_cluster"
jsonPayload.reason="DeprecatedAPIUsage"
```

## Escalation Matrix

| Scenario | Primary Owner | Escalation | Decision Maker |
|----------|---------------|------------|----------------|
| Security patch (HIGH/CRITICAL CVE) | Security team | CTO/CISO | Security team |
| Auto-upgrade during freeze | Platform team | Engineering manager | Platform team lead |
| EoS <30 days | Platform team | Engineering manager + App teams | Engineering manager |
| Deprecated API blocking upgrade | App teams | Platform team + App team leads | App team leads |
| Failed auto-upgrade | Platform team | GKE support (if cluster impact) | Platform team lead |

## Weekly Triage Process

### Monday: Review upcoming notifications
```bash
# Check upgrade targets for all clusters
for cluster in $(gcloud container clusters list --format="value(name)"); do
  echo "=== $cluster ==="
  gcloud container clusters get-upgrade-info $cluster --region REGION
done

# Check maintenance exclusions expiring soon
gcloud container clusters describe CLUSTER_NAME --region REGION \
  --format="value(maintenancePolicy.window.maintenanceExclusions)"
```

### Wednesday: Validate staging upgrades
- Confirm staging clusters received patches/upgrades successfully
- Run smoke tests on upgraded staging environments
- Clear production clusters for auto-upgrade if staging validated

### Friday: Plan next week's maintenance
- Review any manual upgrades needed
- Check for conflicts with deployment schedules
- Communicate planned maintenance to stakeholders

## Automation Recommendations

### 1. Alert routing by notification type
```bash
# Set up different Slack channels or email lists
# Security patches → #security-alerts
# Auto-upgrades → #platform-team  
# EoS warnings → #platform-team + #engineering-leads
```

### 2. Auto-acknowledge informational notifications
```python
# Example Cloud Function to auto-ack "upgrade completed" notifications
def process_gke_notification(event, context):
    if event['jsonPayload']['eventType'] == 'UPGRADE_COMPLETE':
        # Auto-acknowledge, trigger post-upgrade validation
        trigger_cluster_health_check(event['resource']['labels']['cluster_name'])
```

### 3. Staging cluster early warning
Configure staging clusters on Rapid channel to get 2-4 weeks advance notice of what's coming to production (Regular/Stable channel).

## Key Principles

1. **Security patches always require action** - even if just planning
2. **72-hour notifications need a decision** - defer or allow, don't ignore
3. **EoS warnings are countdown timers** - urgency increases as date approaches  
4. **Deprecated APIs block auto-upgrades** - fix the root cause, don't override
5. **"Version available" is planning input** - not an immediate action item

**Remember:** GKE's auto-upgrade system is designed to keep you secure and current. The notification system helps you control timing and scope, not avoid upgrades entirely. Use maintenance windows and exclusions to align upgrades with your change management process, not to indefinitely defer them.