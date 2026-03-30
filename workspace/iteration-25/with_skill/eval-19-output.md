# GKE Upgrade Notification Triage System

I'll help you create a clear triage system to distinguish actionable notifications from informational ones. GKE sends several notification types through different channels - let me break down each type and your required response.

## Notification Types & Response Matrix

### 1. **Upgrade Available Event** 📊
**Source:** Cloud Logging, Pub/Sub cluster notifications  
**Message:** "New version X.Y.Z is available for cluster ABC"  
**Action Required:** ❌ **NONE** - Informational only  
**Rationale:** Auto-upgrades will handle this automatically based on your maintenance windows and release channel. Only act if you want to upgrade ahead of schedule.

### 2. **Scheduled Upgrade Notifications** ⏰
**Source:** Cloud Logging (72 hours before auto-upgrade)  
**Message:** "Control plane auto-upgrade scheduled for [DATE/TIME]"  
**Action Required:** ✅ **VALIDATE** - High priority  
**Response:**
- [ ] Verify timing aligns with maintenance windows
- [ ] Check for conflicting deployments or critical business events
- [ ] Apply "no upgrades" exclusion if deferral needed (30-day max)
- [ ] Notify stakeholders of upcoming upgrade

### 3. **Minor Version at or Near End of Support** 🚨
**Source:** Cloud Logging, Pub/Sub cluster notifications  
**Message:** "Cluster version X.Y approaching end of support on [DATE]"  
**Action Required:** ✅ **PLAN UPGRADE** - Critical  
**Response Timeline:**
- **90+ days before EoS:** Informational, plan upgrade
- **30 days before EoS:** Begin upgrade planning
- **7 days before EoS:** Must upgrade or apply temporary exclusion
- **At EoS:** Forced upgrade occurs

### 4. **Upgrade Event (Start)** 🔄
**Source:** Cloud Logging, Pub/Sub cluster notifications  
**Message:** "Upgrade started on cluster ABC from X.Y.Z to A.B.C"  
**Action Required:** ❌ **MONITOR** - Track progress only  
**Response:**
- Monitor upgrade progress via console or `gcloud container operations list`
- Be available for troubleshooting if upgrade gets stuck

### 5. **Disruption Events During Nodepool Upgrade** ⚠️
**Source:** Cloud Logging, Pub/Sub cluster notifications  
**Event Types:** `POD_PDB_VIOLATION`, `POD_NOT_ENOUGH_PDB`, PDB timeout  
**Action Required:** ✅ **INVESTIGATE** - Medium priority  
**Response:**
- Check PDB configurations: `kubectl get pdb -A`
- Relax overly restrictive PDBs temporarily if blocking upgrade
- Monitor for force-eviction after 1-hour timeout

### 6. **Security Patch Notifications** 🛡️
**Source:** GKE Security Bulletins, Release Notes  
**Message:** "CVE-XXXX-YYYY addressed in version X.Y.Z"  
**Action Required:** ⚡ **ACCELERATE** if severity is Critical/High  
**Response:**
- Review CVE severity and exploitability
- For Critical: Consider manual upgrade ahead of auto-schedule
- For Medium/Low: Let auto-upgrade handle normally

## Email Notification Configuration

Here's how to configure email notifications for the actionable items:

```bash
# Create Pub/Sub topic for GKE notifications
gcloud pubsub topics create gke-cluster-notifications

# Create subscription
gcloud pubsub subscriptions create gke-notifications-email \
    --topic=gke-cluster-notifications

# Configure cluster to send notifications
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --notification-config=pubsub=projects/PROJECT_ID/topics/gke-cluster-notifications
```

## Triage Workflow

### **CRITICAL (Immediate Action Required)**
- End of Support warnings ≤ 7 days
- Disruption events blocking upgrades
- Security patches for Critical/High CVEs

**Response:** Within 4 hours during business hours, 24 hours on weekends

### **HIGH (Action Required Within 1-2 Days)**
- Scheduled upgrade notifications (72h advance)
- End of Support warnings 8-30 days out

**Response:** Plan and validate within 2 business days

### **MEDIUM (Monitor Only)**
- Upgrade start events
- Disruption events that resolve automatically

**Response:** Acknowledge and monitor, no immediate action

### **LOW (Informational)**
- Version available notifications
- End of Support warnings 90+ days out

**Response:** File for future planning, no immediate action

## Alert Routing by Notification Content

Use this filtering logic for your alerting system:

```yaml
# Example Cloud Monitoring alert policy
conditions:
  # CRITICAL: EoS within 7 days
  - displayName: "GKE EoS Critical"
    conditionThreshold:
      filter: 'resource.type="gke_cluster" AND jsonPayload.upgradeAvailableEvent.resourceType="MASTER" AND jsonPayload.type="MINOR_VERSION_AT_OR_NEAR_EOS"'
    notification_channels: ["pager_duty_critical"]
  
  # HIGH: Scheduled upgrade notification
  - displayName: "GKE Scheduled Upgrade"
    conditionThreshold:
      filter: 'resource.type="gke_cluster" AND jsonPayload.type="UPGRADE_EVENT" AND jsonPayload.eventType="SCHEDULED"'
    notification_channels: ["email_team", "slack_ops"]
  
  # MEDIUM: PDB violations during upgrade
  - displayName: "GKE PDB Violations"
    conditionThreshold:
      filter: 'resource.type="gke_cluster" AND (jsonPayload.reason="POD_PDB_VIOLATION" OR jsonPayload.reason="POD_NOT_ENOUGH_PDB")'
    notification_channels: ["slack_ops"]
```

## Maintenance Exclusion Quick Reference

For deferring upgrades when notifications indicate bad timing:

```bash
# Defer ALL upgrades for up to 30 days (use sparingly)
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "code-freeze-q4" \
    --add-maintenance-exclusion-start-time "2024-12-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-12-31T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades

# Block minor upgrades but allow security patches (recommended for production)
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

## Notification Fatigue Prevention

**Recommendations:**
1. **Aggregate notifications** - Group by cluster/environment rather than individual notifications
2. **Use different channels** - Critical to PagerDuty, High to email, Medium to Slack
3. **Suppress duplicates** - Filter repeated "version available" messages for same version
4. **Business hours routing** - EoS warnings during business hours, emergencies 24/7

**Sample notification suppression:**
```bash
# Only alert once per version per cluster for "available" notifications
gcloud logging sinks create gke-upgrades-dedupe \
    bigquery.googleapis.com/projects/PROJECT/datasets/gke_notifications \
    --log-filter='resource.type="gke_cluster" AND jsonPayload.type="UPGRADE_AVAILABLE_EVENT"'
```

## Key Takeaway

**90% of GKE notifications are informational.** The auto-upgrade system handles routine maintenance. You only need to act on:
- Scheduled upgrade conflicts with business events
- End of Support deadlines
- Security patches requiring acceleration
- Upgrade disruptions that don't self-resolve

Focus your attention on these actionable items and let GKE's automation handle the rest.