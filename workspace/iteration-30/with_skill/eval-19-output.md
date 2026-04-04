# GKE Upgrade Notification Triage System

## Notification Categories & Actions

### 1. **Upgrade Available Event** *(Informational - No Action Required)*
**What it means:** A new version is available for your cluster but no upgrade is scheduled yet.
**Action:** Monitor only. Review release notes if interested in new features.
**Sample subject:** "New version available for GKE cluster"

### 2. **Scheduled Upgrade Notifications** *(Action Required - 72 Hours)*
**What it means:** An auto-upgrade will happen within 72 hours (opt-in feature).
**Action:** 
- [ ] Review maintenance window timing
- [ ] Apply temporary exclusion if needed to defer
- [ ] Notify stakeholders of upcoming disruption
- [ ] Run pre-upgrade health checks

**Sample subject:** "Scheduled upgrade for GKE cluster in 72 hours"

**Commands to defer if needed:**
```bash
# Apply 30-day "no upgrades" exclusion to defer
gcloud container clusters update CLUSTER_NAME \
    --add-maintenance-exclusion-name="defer-$(date +%Y%m%d)" \
    --add-maintenance-exclusion-start=$(date -u +%Y-%m-%dT%H:%M:%SZ) \
    --add-maintenance-exclusion-end=$(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ) \
    --add-maintenance-exclusion-scope=no_upgrades
```

### 3. **Upgrade Event (Start)** *(Monitor - Validate After)*
**What it means:** An upgrade is currently in progress.
**Action:**
- [ ] Monitor cluster health during upgrade
- [ ] Check for stuck operations after expected completion time
- [ ] Run post-upgrade validation checklist

**Sample subject:** "GKE cluster upgrade started"

### 4. **Minor Version End of Support** *(Urgent Action Required)*
**What it means:** Your cluster version will reach End of Support soon and will be force-upgraded.
**Action:**
- [ ] **Immediate:** Plan upgrade within 30 days
- [ ] Test workloads against target version
- [ ] Schedule maintenance window
- [ ] Consider Extended channel for 24-month support (1.27+ only)

**Sample subject:** "GKE cluster version approaching end of support"

**Commands to check EoS timeline:**
```bash
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

### 5. **Security Patch Notifications** *(Review - Usually Auto)*
**What it means:** Security patches are available or applied automatically.
**Action:**
- [ ] Review CVE details if provided
- [ ] Monitor application behavior post-patch
- [ ] No blocking action needed (patches auto-apply)

**Sample subject:** "Security update available/applied to GKE cluster"

### 6. **Disruption Events During Upgrade** *(Troubleshoot)*
**What it means:** PDB violations, eviction issues during node pool upgrades.
**Action:**
- [ ] Check if upgrade is progressing or stuck
- [ ] Review PDB configurations
- [ ] Investigate resource constraints

**Sample subject:** Contains keywords like "PDB_VIOLATION" or "EvictionBlocked"

## Triage Decision Tree

```
📧 GKE Notification Received
├─ Contains "end of support" or "EoS"? 
│  └─ 🚨 HIGH PRIORITY - Plan upgrade within 30 days
├─ Contains "scheduled upgrade in 72 hours"?
│  └─ ⚠️  MEDIUM PRIORITY - Review timing, defer if needed
├─ Contains "upgrade started" or "upgrade completed"?
│  └─ 📊 MONITOR - Validate cluster health
├─ Contains "version available" or "new release"?
│  └─ ℹ️  INFORMATIONAL - No action required
├─ Contains "security patch" or CVE?
│  └─ 📋 REVIEW - Monitor post-patch behavior
└─ Contains "PDB_VIOLATION" or "EvictionBlocked"?
   └─ 🔧 TROUBLESHOOT - Check upgrade progress
```

## Notification Setup & Configuration

### Enable Scheduled Upgrade Notifications (72h advance warning)
```bash
gcloud container clusters update CLUSTER_NAME \
    --enable-scheduled-upgrades
```

### Configure Pub/Sub for Programmatic Processing
```bash
# Create topic for GKE notifications
gcloud pubsub topics create gke-cluster-upgrades

# Subscribe cluster to publish notifications
gcloud container clusters update CLUSTER_NAME \
    --notification-config=pubsub=projects/PROJECT_ID/topics/gke-cluster-upgrades
```

### Cloud Logging Queries for Each Notification Type

**All GKE upgrade events:**
```
resource.type="gke_cluster"
protoPayload.methodName=~"google.container.v1.ClusterManager.(UpdateCluster|UpgradeCluster|SetMasterAuth)"
```

**End of Support warnings:**
```
resource.type="gke_cluster"
jsonPayload.message=~".*end.of.support.*"
```

**Upgrade start/complete events:**
```
resource.type="gke_cluster" 
protoPayload.metadata.operationType=~"(UPDATE_CLUSTER|UPGRADE_MASTER)"
```

## Team Playbook by Priority

### 🚨 HIGH PRIORITY: End of Support (Action within 30 days)
**Responsible:** Platform team lead
**SLA:** Acknowledge within 4 hours, plan within 48 hours

1. Check current version and EoS date: `gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION`
2. Review breaking changes in release notes between current → next minor
3. Test deprecated API usage: `kubectl get --raw /metrics | grep deprecated`
4. Schedule upgrade maintenance window
5. Consider Extended channel migration for 24-month support:
   ```bash
   gcloud container clusters update CLUSTER_NAME --release-channel=extended
   ```

### ⚠️ MEDIUM PRIORITY: Scheduled Upgrade (72h window)
**Responsible:** On-call engineer
**SLA:** Review within 8 hours

1. Confirm upgrade timing aligns with maintenance window
2. If timing is bad, apply temporary exclusion (max 30 days)
3. Run pre-upgrade checklist
4. Notify stakeholders of planned disruption

### 📊 MONITOR: Upgrade In Progress
**Responsible:** Monitoring team
**SLA:** Check status every 30 minutes during upgrade

1. Monitor upgrade progress: `gcloud container operations list --cluster CLUSTER_NAME`
2. Check for stuck nodes: `kubectl get nodes -o wide`
3. Validate health after completion: `kubectl get pods -A | grep -v Running`

### ℹ️ INFORMATIONAL: Version Available
**Responsible:** Platform team
**SLA:** Review within 1 week

1. Review release notes for interesting features
2. Update internal Kubernetes roadmap
3. No immediate action required

## Notification Filtering & Routing

### Email Rules (Gmail/Outlook)
- **Subject contains** "end of support" → Label: **GKE-URGENT**, Forward to platform-team@
- **Subject contains** "scheduled upgrade" → Label: **GKE-ACTION**, Forward to on-call@
- **Subject contains** "upgrade started"/"completed" → Label: **GKE-MONITOR**
- **Subject contains** "version available" → Label: **GKE-INFO**, Archive

### Slack Integration Example
```yaml
# If using Cloud Logging → Pub/Sub → Cloud Function → Slack
notification_routing:
  end_of_support: "#platform-alerts"
  scheduled_upgrade: "#on-call"
  upgrade_started: "#monitoring"
  version_available: "#platform-info"
```

## Automated Response Templates

### High Priority (EoS) Response
```
🚨 GKE End of Support Alert
Cluster: ${CLUSTER_NAME}
Current Version: ${CURRENT_VERSION}
EoS Date: ${EOS_DATE}
Days Remaining: ${DAYS_REMAINING}

Action Required: Plan upgrade within 30 days
Assigned: Platform Team Lead
Deadline: ${EOS_DATE - 30 days}

Next Steps:
1. Review breaking changes in release notes
2. Test deprecated APIs  
3. Schedule maintenance window
4. Consider Extended channel migration
```

### Medium Priority (Scheduled) Response
```
⚠️ GKE Auto-Upgrade Scheduled
Cluster: ${CLUSTER_NAME}
Scheduled Time: ${UPGRADE_TIME}
Target Version: ${TARGET_VERSION}

Action: Review timing and defer if needed
Assigned: On-call Engineer
Window: 72 hours

Commands to defer:
gcloud container clusters update ${CLUSTER_NAME} \
    --add-maintenance-exclusion-scope=no_upgrades \
    --add-maintenance-exclusion-start=${NOW} \
    --add-maintenance-exclusion-end=${NOW + 30d}
```

This triage system ensures your team responds appropriately to each notification type while avoiding alert fatigue from purely informational messages.