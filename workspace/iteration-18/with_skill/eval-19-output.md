# GKE Upgrade Notification Triage System

## Notification Types & Action Required

### 🔴 IMMEDIATE ACTION (within 24-48 hours)

**Security Patch Notifications**
- **Subject contains:** "security patch", "CVE", "critical vulnerability"
- **Action:** Apply immediately or schedule within 48 hours
- **Commands:**
```bash
# Check if auto-upgrades are enabled
gcloud container clusters describe CLUSTER_NAME --region REGION \
  --format="value(nodePools[].management.autoUpgrade,releaseChannel.channel)"

# If auto-upgrades disabled, manually upgrade
gcloud container clusters upgrade CLUSTER_NAME --region REGION
```

**End of Support (EoS) Enforcement Warnings**
- **Subject contains:** "will be upgraded", "End of Support", "force upgrade"
- **Timeline:** Usually 2-4 weeks notice before enforcement
- **Action:** Upgrade before the enforcement date OR apply temporary exclusion
```bash
# Check EoS timeline
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Apply 30-day deferral if needed (max one-time extension)
gcloud container clusters update CLUSTER_NAME --region REGION \
  --add-maintenance-exclusion-name "eos-deferral" \
  --add-maintenance-exclusion-start $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end $(date -u -d "+30 days" +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_upgrades
```

### 🟡 SCHEDULE ACTION (within 1-2 weeks)

**Scheduled Auto-Upgrade Notifications (72h advance)**
- **Subject contains:** "scheduled to upgrade", "auto-upgrade planned"
- **Action:** Verify timing works OR apply maintenance exclusion to defer
```bash
# If timing is bad, defer the upgrade
gcloud container clusters update CLUSTER_NAME --region REGION \
  --add-maintenance-exclusion-name "defer-upgrade" \
  --add-maintenance-exclusion-start $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end $(date -u -d "+7 days" +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_upgrades
```

**Deprecated API Usage Warnings**
- **Subject contains:** "deprecated API", "API removal", "compatibility"
- **Action:** Update workloads before next minor version upgrade
```bash
# Check deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Get detailed insights
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=REGION --project=PROJECT_ID
```

### 🟢 INFORMATIONAL (acknowledge, plan for future)

**Version Availability Notifications**
- **Subject contains:** "new version available", "version released"
- **Action:** Note for planning, but no immediate action required
- **Response:** Check if your release channel will auto-upgrade to this version

**Maintenance Window Confirmations**
- **Subject contains:** "maintenance window", "upgrade completed"
- **Action:** Validate cluster health post-upgrade
```bash
# Post-upgrade health check
kubectl get nodes
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
```

**Channel Migration Recommendations**
- **Subject contains:** "consider migrating", "Extended support available"
- **Action:** Evaluate for next maintenance window
- **Note:** No urgency unless you're on "No channel" (legacy)

## Triage Decision Matrix

| Notification Type | Keywords | Timeline | Action |
|------------------|----------|----------|---------|
| **Security Patch** | "CVE", "security", "critical" | 24-48h | Apply patch immediately |
| **EoS Enforcement** | "force upgrade", "will be upgraded" | 2-4 weeks | Upgrade or apply exclusion |
| **Scheduled Upgrade** | "scheduled to upgrade", "72 hours" | 72h | Defer if timing conflicts |
| **Deprecated API** | "deprecated", "API removal" | Before next minor | Update workloads |
| **Version Available** | "new version", "available" | Informational | Plan future upgrades |
| **Maintenance Complete** | "upgrade completed", "successful" | Informational | Validate health |

## Automation Scripts

### Email Filter Rules (Gmail/Outlook)
```
Subject contains: ("CVE" OR "security patch" OR "critical vulnerability")
→ Label: GKE-URGENT, Forward to: oncall@company.com

Subject contains: ("End of Support" OR "force upgrade" OR "will be upgraded")
→ Label: GKE-EOS-WARNING, Forward to: platform-team@company.com

Subject contains: ("scheduled to upgrade" OR "auto-upgrade planned")
→ Label: GKE-SCHEDULED, Calendar: Create 24h reminder

Subject contains: ("new version available" OR "version released")
→ Label: GKE-INFO, Archive after 7 days
```

### Slack Alert Automation
```bash
#!/bin/bash
# webhook-processor.sh
# Parse GKE notification emails and send appropriate Slack alerts

if [[ "$EMAIL_SUBJECT" == *"CVE"* ]] || [[ "$EMAIL_SUBJECT" == *"security"* ]]; then
    curl -X POST -H 'Content-type: application/json' \
        --data '{"text":"🚨 URGENT: GKE Security Patch Required - '$EMAIL_SUBJECT'","channel":"#gke-alerts"}' \
        $SLACK_WEBHOOK_URL
        
elif [[ "$EMAIL_SUBJECT" == *"End of Support"* ]] || [[ "$EMAIL_SUBJECT" == *"force upgrade"* ]]; then
    curl -X POST -H 'Content-type: application/json' \
        --data '{"text":"⚠️ GKE EoS Warning - Action required within 2-4 weeks: '$EMAIL_SUBJECT'","channel":"#gke-maintenance"}' \
        $SLACK_WEBHOOK_URL
        
elif [[ "$EMAIL_SUBJECT" == *"scheduled to upgrade"* ]]; then
    curl -X POST -H 'Content-type: application/json' \
        --data '{"text":"📅 GKE Auto-upgrade scheduled in 72h - Review timing: '$EMAIL_SUBJECT'","channel":"#gke-maintenance"}' \
        $SLACK_WEBHOOK_URL
fi
```

## Proactive Monitoring Setup

### Enable Scheduled Upgrade Notifications
```bash
# Get 72h advance notice of auto-upgrades (preview feature)
gcloud container clusters update CLUSTER_NAME --region REGION \
  --send-scheduled-upgrade-notifications
```

### Cloud Monitoring Alerts
```bash
# Alert on clusters approaching EoS
gcloud alpha monitoring policies create --policy-from-file - <<EOF
{
  "displayName": "GKE Version Approaching EoS",
  "conditions": [{
    "displayName": "Cluster version near end of support",
    "conditionThreshold": {
      "filter": "resource.type=\"gke_cluster\"",
      "comparison": "COMPARISON_LESS_THAN",
      "thresholdValue": 30,
      "aggregations": [{
        "alignmentPeriod": "3600s",
        "perSeriesAligner": "ALIGN_MEAN"
      }]
    }
  }],
  "notificationChannels": ["NOTIFICATION_CHANNEL_ID"]
}
EOF
```

### Deprecation Insight Monitoring
```bash
#!/bin/bash
# check-deprecated-apis.sh - Run weekly via cron

for cluster in $(gcloud container clusters list --format="value(name,location)"); do
    cluster_name=$(echo $cluster | cut -d' ' -f1)
    location=$(echo $cluster | cut -d' ' -f2)
    
    deprecated_count=$(gcloud recommender insights list \
        --insight-type=google.container.DiagnosisInsight \
        --location=$location --project=$PROJECT_ID \
        --filter="category.category=SECURITY" --format="value(name)" | wc -l)
    
    if [[ $deprecated_count -gt 0 ]]; then
        echo "⚠️ Cluster $cluster_name has $deprecated_count deprecated API insights"
        # Send to monitoring/alerting system
    fi
done
```

## Response Playbooks

### Security Patch Response (< 48h)
```bash
# 1. Check cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running

# 2. Apply patch during maintenance window
gcloud container clusters upgrade CLUSTER_NAME --region REGION

# 3. Validate post-upgrade
kubectl get events -A --sort-by='.lastTimestamp' | tail -20
```

### EoS Enforcement Response (2-4 weeks)
```bash
# 1. Check current version and target
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# 2. Plan upgrade path (sequential minor versions)
# Current: 1.31 → Target: 1.33
# Step 1: Upgrade to 1.32
gcloud container clusters upgrade CLUSTER_NAME --region REGION --cluster-version=1.32.X-gke.Y

# Step 2: After validation, upgrade to 1.33
gcloud container clusters upgrade CLUSTER_NAME --region REGION --cluster-version=1.33.X-gke.Y

# 3. Alternative: Apply exclusion for planning time
gcloud container clusters update CLUSTER_NAME --region REGION \
  --add-maintenance-exclusion-scope no_upgrades \
  --add-maintenance-exclusion-name "eos-planning" \
  --add-maintenance-exclusion-start $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end $(date -u -d "+30 days" +"%Y-%m-%dT%H:%M:%SZ")
```

## Key Recommendations

1. **Set up email filters immediately** - Route urgent notifications to on-call, informational ones to a planning queue
2. **Configure maintenance windows** - Ensures auto-upgrades happen during acceptable hours
3. **Use maintenance exclusions strategically** - "no minor or node upgrades" for maximum control while allowing security patches
4. **Monitor the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule)** - Plan upgrades proactively rather than reactively
5. **Enable scheduled upgrade notifications** - 72h advance warning for better planning
6. **Regular deprecation insight checks** - Prevent upgrade blocks from deprecated API usage

The goal is to move from reactive "notification fatigue" to proactive upgrade lifecycle management. Most notifications should be handled automatically through your maintenance windows and release channel selection - you only need to intervene for timing conflicts, security patches, and EoS warnings.