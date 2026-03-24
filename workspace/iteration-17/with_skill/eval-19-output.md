# GKE Upgrade Notification Triage System

## Notification Types & Priority Matrix

| Notification Type | Urgency | Action Required | Timeline | What It Means |
|-------------------|---------|----------------|----------|---------------|
| **End of Support (EoS) Warning** | 🔴 **HIGH** | Plan upgrade immediately | 30-60 days | Your version will be force-upgraded soon |
| **Security Patch Available** | 🟡 **MEDIUM** | Review and plan | 7-14 days | Critical security fixes available |
| **Auto-upgrade Scheduled** | 🟡 **MEDIUM** | Review/defer if needed | 72 hours | GKE will auto-upgrade during your maintenance window |
| **New Version Available** | 🟢 **LOW** | Informational | No deadline | New version released in your channel |
| **Deprecated API Usage** | 🔴 **HIGH** | Fix before upgrade | Before next minor | Your workloads use deprecated APIs |

## Triage Decision Tree

```
📧 GKE Notification Received
│
├── Contains "End of Support" or "EoS"?
│   ├── YES → 🔴 HIGH: Plan upgrade within 30 days
│   └── NO → Continue
│
├── Contains "security" or "CVE"?
│   ├── YES → 🟡 MEDIUM: Review CVE severity, plan patch
│   └── NO → Continue
│
├── Contains "scheduled upgrade" or "will be upgraded"?
│   ├── YES → 🟡 MEDIUM: Review timing, apply exclusion if needed
│   └── NO → Continue
│
├── Contains "deprecated API" or "removal"?
│   ├── YES → 🔴 HIGH: Update workloads before next upgrade
│   └── NO → Continue
│
└── Otherwise → 🟢 LOW: File for planning, no immediate action
```

## Response Playbooks by Notification Type

### 🔴 HIGH Priority: End of Support Warning

**Sample notification:** *"Cluster 'prod-cluster' version 1.28.x will reach end of support on [DATE]. Upgrade required."*

**Immediate actions (within 24 hours):**
```bash
# Check current status
gcloud container clusters get-upgrade-info prod-cluster --region us-central1

# Apply temporary exclusion if you need more time (max 30 days)
gcloud container clusters update prod-cluster \
  --region us-central1 \
  --add-maintenance-exclusion-name "eos-extension" \
  --add-maintenance-exclusion-start-time "2024-01-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-02-14T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**Planning actions (within 1 week):**
- [ ] Schedule upgrade planning meeting
- [ ] Review deprecated API usage (most common blocker)
- [ ] Plan sequential minor version upgrades if multiple versions behind
- [ ] Coordinate with application teams for compatibility testing

### 🔴 HIGH Priority: Deprecated API Usage

**Sample notification:** *"Cluster 'prod-cluster' uses deprecated APIs that will be removed in Kubernetes 1.29."*

**Immediate actions:**
```bash
# Check deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Get detailed deprecation insights
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=us-central1 \
  --project=PROJECT_ID \
  --filter="category:SECURITY"
```

**Critical:** GKE automatically pauses auto-upgrades when deprecated API usage is detected. You MUST fix these before any upgrade will proceed.

### 🟡 MEDIUM Priority: Auto-upgrade Scheduled

**Sample notification:** *"Cluster 'prod-cluster' is scheduled for auto-upgrade to 1.29.1 during your maintenance window on Saturday 2-6 AM."*

**Decision matrix:**
- ✅ **Allow upgrade:** Do nothing. GKE will upgrade during your maintenance window.
- ⏸️ **Defer upgrade:** Apply maintenance exclusion to control timing.
- 🚀 **Accelerate upgrade:** Trigger manual upgrade before scheduled time.

**To defer (common during code freezes, major releases, holidays):**
```bash
# Apply "no upgrades" exclusion for 30 days max
gcloud container clusters update prod-cluster \
  --region us-central1 \
  --add-maintenance-exclusion-name "holiday-freeze" \
  --add-maintenance-exclusion-start-time "2024-12-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-01-15T00:00:00Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**To accelerate (gain control over exact timing):**
```bash
# Trigger upgrade manually during your preferred window
gcloud container clusters upgrade prod-cluster \
  --region us-central1 \
  --cluster-version 1.29.1
```

### 🟡 MEDIUM Priority: Security Patch Available

**Sample notification:** *"Security patch 1.28.5 available for cluster 'prod-cluster' addressing CVE-2024-XXXX."*

**Triage by CVE severity:**
- **CRITICAL (CVSS 9.0-10.0):** Upgrade within 7 days
- **HIGH (CVSS 7.0-8.9):** Upgrade within 14 days  
- **MEDIUM/LOW:** Follow normal patching cadence

**Check CVE details:**
```bash
# Review GKE release notes for CVE details
gcloud container get-server-config --region us-central1 \
  --format="yaml(channels)"

# Enable accelerated patching for faster compliance (optional)
gcloud container clusters update prod-cluster \
  --region us-central1 \
  --patch-update accelerated
```

### 🟢 LOW Priority: New Version Available

**Sample notification:** *"Kubernetes 1.30.0 is now available in the Regular channel."*

**Actions:**
- [ ] File in upgrade planning backlog
- [ ] Review release notes for new features/changes
- [ ] Test in dev/staging environments
- [ ] No immediate action required

## Notification Sources & Configuration

### Email Notifications
Google Cloud sends upgrade notifications to:
- Project owners/editors
- Cluster-specific IAM principals with container.clusters.get permission
- Custom notification channels (Cloud Monitoring alerting policies)

### Proactive Monitoring Setup
Set up Cloud Monitoring alerting for upgrade events:

```bash
# Create Pub/Sub topic for cluster events
gcloud pubsub topics create gke-cluster-events

# Subscribe to GKE cluster notifications
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --notification-config pubsub=projects/PROJECT_ID/topics/gke-cluster-events
```

### Scheduled Upgrade Notifications (Preview)
Enable 72-hour advance notifications:
```bash
gcloud container clusters update prod-cluster \
  --region us-central1 \
  --send-scheduled-upgrade-notifications
```

## Team Response Matrix

| Role | EoS Warning | Security Patch | Scheduled Upgrade | API Deprecation |
|------|-------------|---------------|-------------------|-----------------|
| **Platform Team** | Plan upgrade, coordinate timeline | Assess CVE, plan patch | Review timing, apply exclusions if needed | Identify affected workloads |
| **App Teams** | Test compatibility, update deprecated APIs | Review app-level security impact | Prepare for brief disruption | Update API usage in code |
| **SRE/Ops** | Schedule maintenance windows | Monitor for incidents post-patch | Monitor upgrade progress | Update monitoring/alerting |
| **Security Team** | Review compliance requirements | Validate CVE remediation | N/A (unless security implications) | N/A |

## Filtering & Automation

### Email Filter Rules
Create email filters to automatically label/route notifications:

**Gmail/Outlook rules:**
- Subject contains "End of Support" → Label: GKE-URGENT, Forward to on-call
- Subject contains "security" OR "CVE" → Label: GKE-SECURITY  
- Subject contains "scheduled upgrade" → Label: GKE-MAINTENANCE
- From: google-cloud-kubernetes-engine-team → Label: GKE-NOTIFICATIONS

### Automation Scripts
For teams managing many clusters, automate triage:

```bash
#!/bin/bash
# Check all clusters for EoS warnings
for cluster in $(gcloud container clusters list --format="value(name,zone)"); do
  cluster_name=$(echo $cluster | cut -d' ' -f1)
  zone=$(echo $cluster | cut -d' ' -f2)
  
  # Check EoS status
  gcloud container clusters get-upgrade-info $cluster_name --zone $zone \
    --format="table(name,endOfStandardSupportTimestamp)"
done
```

## Key Recommendations

### 1. **Don't ignore EoS warnings** — they turn into forced upgrades
Set calendar reminders 60 days before EoS dates. Use Extended channel (24-month support) for mission-critical clusters that need more time.

### 2. **Use maintenance exclusions strategically, not reflexively**
Only defer upgrades during genuine business-critical periods (code freezes, BFCM, major releases). Each 30-day exclusion delays security patches.

### 3. **Fix deprecated APIs immediately**
GKE pauses auto-upgrades when deprecated APIs are detected. The longer you wait, the more APIs accumulate, making eventual upgrades harder.

### 4. **Establish upgrade cadence by environment**
- **Dev clusters:** Rapid channel, auto-upgrade enabled
- **Staging:** Regular channel, auto-upgrade enabled  
- **Prod:** Stable channel with "no minor or node upgrades" exclusion + manual minor upgrades after staging validation

### 5. **Monitor upgrade health, not just notifications**
Set up alerting for failed upgrades, stuck node pools, and post-upgrade application health. Notifications tell you what's planned; monitoring tells you what actually happened.

This triage system turns notification overwhelm into clear, actionable workflows. Focus your attention on EoS warnings and deprecated APIs — these are the only notifications that can force disruptive changes if ignored.