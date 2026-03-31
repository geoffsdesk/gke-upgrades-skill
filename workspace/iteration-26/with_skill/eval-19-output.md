# GKE Upgrade Notification Triage System

Based on GKE's official cluster notification types, here's a structured approach to prioritize and respond to upgrade notifications.

## Notification Classification & Response Matrix

### 🔴 **CRITICAL - Immediate Action Required**
**Notification:** Minor version at or near end of support
**Timeline:** Act within 1-2 weeks
**Action Required:**
- [ ] Review current cluster versions: `gcloud container clusters list --format="table(name,location,currentMasterVersion,releaseChannel.channel)"`
- [ ] Check EoS timeline: `gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION`
- [ ] Plan immediate upgrade or apply temporary "no upgrades" exclusion (30-day max)
- [ ] For versions 1.27+: Consider migrating to Extended channel for 24-month support

**Why Critical:** GKE will force-upgrade at EoS. Unplanned forced upgrades carry higher risk than controlled upgrades.

### 🟡 **HIGH - Plan Action**
**Notification:** Upgrade available event (new minor version)
**Timeline:** Plan within 1-4 weeks depending on channel
**Action Required:**
- [ ] Check if it's a minor version or patch: compare against current version
- [ ] Review GKE release notes for breaking changes
- [ ] Schedule upgrade testing in dev/staging environment
- [ ] Plan production upgrade timing (coordinate with maintenance windows)

**Context:** New minor versions introduce features and potential breaking changes. Patches are lower risk but still benefit from validation.

### 🟠 **MEDIUM - Monitor & Plan**
**Notification:** Upgrade event (start) - auto-upgrade beginning
**Timeline:** Monitor immediately, validate within 24-48 hours
**Action Required:**
- [ ] Monitor upgrade progress: `gcloud container operations list --cluster CLUSTER_NAME --region REGION`
- [ ] Check for stuck operations or pod eviction issues
- [ ] Run post-upgrade validation checklist once complete
- [ ] Document any issues for future upgrades

**Context:** Auto-upgrade is already happening. Focus shifts to monitoring and validation.

### 🟢 **LOW - Informational**
**Notification:** New patch change to new COS milestone during extended support
**Timeline:** Acknowledge, plan for next maintenance window
**Action Required:**
- [ ] Note the availability for next scheduled maintenance
- [ ] No immediate action required unless security-critical

**Context:** Extended support clusters get notifications about patch availability. These are typically applied during regular maintenance.

## Triage Workflow

### Step 1: Identify Notification Type
Use this regex pattern to parse your email notifications:
- **EoS Warning:** Contains "end of support" or "end-of-life"
- **Upgrade Available:** Contains "upgrade available" + version number
- **Upgrade Started:** Contains "upgrade event" + "start"
- **Patch Available:** Contains "COS milestone" or "patch"

### Step 2: Environment-Specific Response

**Production Clusters:**
- EoS notifications → Immediate triage meeting
- Minor upgrade available → Schedule within 2-4 weeks with full testing
- Upgrade started → Active monitoring, on-call awareness

**Development/Staging Clusters:**
- EoS notifications → Upgrade within 1 week (use as prod rehearsal)
- Upgrade available → Accept auto-upgrades or upgrade immediately
- Upgrade started → Passive monitoring

### Step 3: Multi-Cluster Coordination

```bash
# Quick cluster version audit
gcloud container clusters list \
  --format="table(name,location,currentMasterVersion,releaseChannel.channel)" \
  --sort-by="releaseChannel.channel,currentMasterVersion"
```

**Rollout Strategy:**
1. Dev clusters first (canary for breaking changes)
2. Staging validation (full workload testing)
3. Production rollout (staggered if multi-cluster)

## Notification Configuration Best Practices

### Enable Structured Notifications
```bash
# Configure cluster notifications via Pub/Sub for programmatic processing
gcloud pubsub topics create gke-cluster-notifications
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --notification-config=pubsub=projects/PROJECT_ID/topics/gke-cluster-notifications
```

### Scheduled Upgrade Notifications (Preview - March 2026)
```bash
# Enable 72-hour advance notifications
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --enable-scheduled-upgrades
```

### Filter by Priority
Set up email rules or Slack integrations that:
- **Red alert:** "end of support" notifications
- **Yellow alert:** "upgrade available" for minor versions
- **Green info:** patch notifications, upgrade started events

## Response Templates

### For EoS Notifications
```
PRIORITY: CRITICAL
Cluster: [cluster-name]
Current: [version]
EoS Date: [date]
Action: Schedule upgrade by [date-2weeks]
Owner: [team]
```

### For Minor Version Available
```
PRIORITY: HIGH  
Cluster: [cluster-name]
Available: [new-version]
Breaking Changes: [link to release notes]
Test Window: [dates]
Prod Window: [dates]
```

### For Auto-Upgrade Started
```
PRIORITY: MEDIUM
Cluster: [cluster-name]
Upgrading: [old] → [new]
Monitor: [dashboard-link]
ETA: [estimated completion]
```

## Automation Recommendations

### Cloud Function Triage Bot
Create a Cloud Function that:
- Parses Pub/Sub cluster notifications
- Classifies by type and urgency
- Creates tickets in your task system
- Sends targeted alerts to appropriate teams

### Monitoring Integration
```bash
# Set up alerting for stuck upgrades
gcloud alpha monitoring policies create \
  --notification-channels=NOTIFICATION_CHANNEL_ID \
  --display-name="GKE Upgrade Stuck" \
  --condition-filter='resource.type="gke_cluster"' \
  --condition-comparison="COMPARISON_GT" \
  --condition-threshold-value=3600
```

## Decision Tree Summary

```
Notification Received
├── Contains "end of support"? → 🔴 CRITICAL (Act within 1-2 weeks)
├── Contains "upgrade available" + minor version? → 🟡 HIGH (Plan within 1-4 weeks)
├── Contains "upgrade event" + "start"? → 🟠 MEDIUM (Monitor immediately)
└── Contains "patch" or "COS milestone"? → 🟢 LOW (Next maintenance window)
```

This triage system ensures you respond appropriately to each notification type while avoiding upgrade fatigue from over-reacting to routine maintenance notifications.