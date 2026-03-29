# GKE Upgrade Notification Triage System

## Notification Classification & Response Matrix

| Notification Type | Urgency | Action Required | Response Timeline | Sample Subject Lines |
|-------------------|---------|-----------------|-------------------|---------------------|
| **🔴 Critical - Immediate Action** | High | Yes | 24-48 hours | "GKE cluster will be upgraded due to security vulnerability", "End of support enforcement" |
| **🟡 Important - Plan Action** | Medium | Yes | 1-2 weeks | "GKE auto-upgrade scheduled", "Version approaching end of support" |
| **🟢 Informational - Monitor** | Low | Monitor | Review monthly | "New GKE version available", "Scheduled maintenance window" |
| **⚪ Optional - Awareness** | Minimal | Optional | Review quarterly | "Feature updates", "Regional capacity changes" |

---

## 🔴 Critical Notifications (Act Within 24-48 Hours)

### **Security Vulnerability Patches**
- **Subject contains**: "security vulnerability", "CVE", "security patch", "urgent upgrade"
- **Content indicates**: Forced upgrade due to security issue
- **Action**: Apply immediately or use 30-day "no upgrades" exclusion to defer while planning
```bash
# Emergency deferral (max 30 days)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "security-patch-defer" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time $(date -u -d '+30 days' +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_upgrades
```

### **End of Support (EoS) Enforcement**
- **Subject contains**: "end of support", "EoS enforcement", "version no longer supported"
- **Content indicates**: Cluster will be force-upgraded within days
- **Action**: 
  - **Option 1**: Let force-upgrade proceed (simplest, but no control over timing)
  - **Option 2**: Trigger manual upgrade immediately for better timing control
  - **Option 3**: Migrate to Extended channel (versions 1.27+) for up to 24 months support
```bash
# Check EoS timeline
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Option 2: Manual upgrade with timing control
gcloud container clusters upgrade CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION

# Option 3: Migrate to Extended channel (if available)
gcloud container clusters update CLUSTER_NAME --zone ZONE --release-channel extended
```

### **Deprecated API Breaking Changes**
- **Subject contains**: "deprecated APIs", "API removal", "compatibility issues"
- **Content indicates**: APIs your cluster uses will be removed
- **Action**: Update workloads to use non-deprecated APIs before upgrade
```bash
# Check deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Review GKE deprecation insights
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=LOCATION --project=PROJECT_ID
```

---

## 🟡 Important Notifications (Plan Within 1-2 Weeks)

### **Auto-Upgrade Scheduled**
- **Subject contains**: "auto-upgrade scheduled", "maintenance window", "cluster upgrade planned"
- **Content indicates**: Specific date/time for auto-upgrade
- **Action**: Decide whether to accept scheduled timing or control it

**Decision Matrix:**
```
Good timing (off-peak, no critical releases) → ✅ Let auto-upgrade proceed
Bad timing (high-traffic period, code freeze) → 🛠️ Apply maintenance controls
Want to test first → 🧪 Apply "no upgrades" exclusion, test manually, then remove
```

**Control options:**
```bash
# Option A: Defer with "no upgrades" exclusion (30-day max)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "defer-upgrade" \
  --add-maintenance-exclusion-start-time START_TIME \
  --add-maintenance-exclusion-end-time END_TIME \
  --add-maintenance-exclusion-scope no_upgrades

# Option B: Trigger manual upgrade at preferred time
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION

# Option C: Adjust maintenance window for future upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "YYYY-MM-DDTHH:MM:SSZ" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### **Version Approaching End of Support**
- **Subject contains**: "approaching end of support", "version will reach EoS", "migrate before"
- **Content indicates**: 30-90 day warning before EoS
- **Action**: Plan upgrade to supported version or migrate to Extended channel
```bash
# Check timeline and target versions
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Plan upgrade - start with dev/staging environments
# Use release channel + maintenance exclusions for maximum control
```

### **Node Pool Mixed Versions**
- **Subject contains**: "node version skew", "mixed versions detected", "nodes behind control plane"
- **Content indicates**: Nodes are 2+ versions behind control plane (approaching skew limit)
- **Action**: Upgrade node pools within 2 weeks to avoid reaching the 2-minor-version skew limit
```bash
# Check version skew
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# Upgrade node pools (skip-level upgrades are supported within skew limits)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

---

## 🟢 Informational Notifications (Review Monthly)

### **New Version Available**
- **Subject contains**: "new version available", "version X.Y.Z released", "update available"
- **Content indicates**: New version in your release channel, no forced timeline
- **Action**: Review for new features, plan non-urgent upgrade
```bash
# Check what's available vs. current
gcloud container get-server-config --zone ZONE --format="yaml(channels)"

# Review release notes for new features between versions
# Plan upgrade during next maintenance cycle
```

### **Maintenance Window Notifications**
- **Subject contains**: "maintenance window", "scheduled maintenance", "no action required"
- **Content indicates**: Routine maintenance will occur, cluster remains available
- **Action**: Note timing, no action required unless you have disruption-sensitive workloads

### **Version Migration Reminders**
- **Subject contains**: "migrate to release channel", "no channel deprecated", "channel benefits"
- **Content indicates**: General recommendation to use release channels vs. static versions
- **Action**: Evaluate migration during next planning cycle (not urgent)

---

## ⚪ Optional Notifications (Review Quarterly)

### **Feature Announcements**
- **Subject contains**: "new features", "regional availability", "service updates"
- **Content indicates**: New GKE capabilities, regional expansions
- **Action**: Evaluate if features benefit your use case

### **Capacity and Regional Changes**
- **Subject contains**: "capacity updates", "regional changes", "quota adjustments"
- **Content indicates**: Changes to machine type availability, regional capacity
- **Action**: Note for future planning, especially for large clusters

---

## Notification Management Setup

### **1. Configure Notification Filtering**
Set up email filters or labels to automatically categorize notifications:

**Gmail/Google Workspace filters:**
- From: `google-noreply@google.com` + Subject contains `security` → Label: GKE-Critical
- From: `google-noreply@google.com` + Subject contains `scheduled` → Label: GKE-Important
- From: `google-noreply@google.com` + Subject contains `available` → Label: GKE-Info

### **2. Enable Structured Notifications (Recommended)**
Use Cloud Logging and Pub/Sub for programmatic notification handling:

```bash
# Enable GKE cluster notifications to Pub/Sub
gcloud pubsub topics create gke-cluster-notifications

gcloud logging sinks create gke-notifications \
  pubsub.googleapis.com/projects/PROJECT_ID/topics/gke-cluster-notifications \
  --log-filter='resource.type="gke_cluster" AND (protoPayload.metadata.operationType="UPDATE_CLUSTER" OR protoPayload.metadata.operationType="UPGRADE_MASTER" OR jsonPayload.eventType="UPGRADE_AVAILABLE")'
```

### **3. Set Up Scheduled Upgrade Notifications (Preview)**
For 72-hour advance warning of auto-upgrades:
```bash
# Enable 72h advance notifications via Cloud Logging
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --send-scheduled-upgrade-notifications
```

---

## Response Workflow

### **Daily Triage (5 minutes)**
```markdown
- [ ] Check GKE-Critical label → Act within 24-48h
- [ ] Review any new EoS warnings → Plan upgrade timeline
- [ ] Note any scheduled auto-upgrades → Decide timing
```

### **Weekly Review (15 minutes)**
```markdown
- [ ] Process GKE-Important notifications
- [ ] Update upgrade calendar with scheduled dates
- [ ] Check deprecation insights dashboard
- [ ] Verify maintenance windows align with business needs
```

### **Monthly Planning (30 minutes)**
```markdown
- [ ] Review GKE-Info notifications for upgrade candidates
- [ ] Plan version progression across dev/staging/prod
- [ ] Evaluate new features and release channel strategy
- [ ] Update upgrade runbooks based on recent changes
```

---

## Quick Decision Tree

```
New GKE notification received
├── Contains "security", "CVE", "EoS enforcement"? 
│   ├── YES → 🔴 Act within 24-48 hours
│   └── NO → Continue
├── Contains "scheduled", "auto-upgrade", "approaching EoS"?
│   ├── YES → 🟡 Plan within 1-2 weeks  
│   └── NO → Continue
├── Contains "available", "maintenance window", "no action"?
│   ├── YES → 🟢 Review monthly
│   └── NO → ⚪ Optional, review quarterly
```

**Key principle**: When in doubt about urgency, check the GKE console **Notifications** tab or run `gcloud container clusters get-upgrade-info` — these show the actual timeline and severity of any pending actions.

This triage system will help you focus on notifications that actually require action while staying informed about routine updates without alert fatigue.