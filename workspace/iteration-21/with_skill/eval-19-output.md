# GKE Upgrade Notification Triage System

## Notification Classification Matrix

| Notification Type | Urgency | Action Required | Timeline | Who Should Handle |
|------------------|---------|----------------|----------|-------------------|
| **Auto-upgrade scheduled (72h)** | Medium | Optional | 72 hours | Platform team |
| **Version available** | Low | Optional | No deadline | Dev team |
| **End-of-life warning** | High | Required | 30-90 days | Platform team |
| **Security patch auto-upgrade** | Medium-High | Monitor | 7-14 days | Security + Platform |
| **Deprecated API usage** | High | Required | Before next minor | Dev team |
| **Upgrade failed/stuck** | Critical | Required | Immediate | On-call team |

## Detailed Triage Guide

### 1. Auto-upgrade Scheduled Notifications (72h advance)

**What it means:** GKE will upgrade your cluster in 72 hours during your maintenance window.

**Triage questions:**
- [ ] Is this a patch upgrade (1.31.1 → 1.31.2) or minor upgrade (1.31 → 1.32)?
- [ ] Are we in a code freeze or critical business period?
- [ ] Do we have capacity to handle issues if something breaks?

**Action matrix:**
```
✅ ALLOW AUTO-UPGRADE:
- Patch upgrades during normal operations
- Minor upgrades in dev/staging environments
- Well-tested upgrade path with recent staging validation

⚠️ DEFER AUTO-UPGRADE:
- Code freeze periods (apply "no upgrades" exclusion)
- Major releases or critical business events
- No staging validation of target version yet
- Team unavailable to handle issues

🚨 EMERGENCY BLOCK:
- Critical production issues ongoing
- Known incompatibilities with your workloads
```

**Commands to defer:**
```bash
# Emergency 30-day freeze (blocks ALL upgrades including patches)
gcloud container clusters update CLUSTER_NAME \
  --add-maintenance-exclusion-name "emergency-freeze" \
  --add-maintenance-exclusion-start $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end $(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades

# Block only minor upgrades (allows security patches)
gcloud container clusters update CLUSTER_NAME \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

### 2. Version Available Notifications

**What it means:** A new version is available in your release channel but won't auto-upgrade yet.

**Default action:** **No action required** - this is informational.

**Optional actions:**
- Test in staging if it's a new minor version
- Review release notes for relevant changes
- Plan manual upgrade if you want to get ahead of auto-upgrade

### 3. End-of-Life (EoS) Warnings

**What it means:** Your version will reach End of Support and be force-upgraded.

**Criticality by timeline:**
- **90 days:** Low - plan upgrade in next sprint
- **30 days:** Medium - prioritize upgrade planning
- **7 days:** High - urgent upgrade needed
- **0 days (EoS reached):** Critical - cluster will be force-upgraded

**Action checklist:**
- [ ] Check current cluster version: `gcloud container clusters describe CLUSTER --zone ZONE --format="value(currentMasterVersion)"`
- [ ] Plan upgrade path to supported version
- [ ] Test upgrade in staging environment
- [ ] Schedule production upgrade before EoS date
- [ ] Consider Extended channel for longer support (versions 1.27+)

### 4. Security Patch Notifications

**What it means:** Critical security patches are being auto-applied faster than normal.

**Default action:** **Monitor** - let auto-upgrade proceed but watch for issues.

**Enhanced monitoring:**
- Check application error rates after upgrade
- Verify control plane API responsiveness
- Monitor for admission webhook failures (common after patches)

**Only block if:**
- Active production incident
- Critical deployment in progress
- Team unavailable for 48+ hours

### 5. Deprecated API Usage Warnings

**What it means:** Your workloads use APIs that will be removed in future versions.

**Criticality:** **High** - this will block auto-upgrades and cause failures.

**Immediate actions:**
- [ ] Check deprecation insights: GKE Console → Clusters → [Cluster] → Insights
- [ ] Run API usage scan: `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated`
- [ ] Use GKE recommender: `gcloud recommender insights list --insight-type=google.container.DiagnosisInsight`

**Timeline:** Fix before the next minor version upgrade where the API is removed.

### 6. Upgrade Failed/Stuck Notifications

**What it means:** An upgrade is stuck and needs intervention.

**Criticality:** **Critical** - cluster may be in mixed state.

**Immediate diagnosis:**
```bash
# Check upgrade operations
gcloud container operations list --cluster CLUSTER --zone ZONE --filter="status=RUNNING"

# Check for common blocking issues
kubectl get pdb -A | grep "0.*0"  # PDBs blocking drain
kubectl get pods -A | grep Pending  # Resource constraints
kubectl get nodes | grep -v Ready  # Node issues
```

**Escalation:** If basic troubleshooting doesn't resolve within 2 hours, contact GKE support with operation ID.

## Automated Triage Workflow

### Cloud Function Alert Router (Optional)

```python
# Example Cloud Function to route GKE notifications
def route_gke_notification(event, context):
    message = base64.b64decode(event['data']).decode('utf-8')
    
    # Parse notification type from Cloud Logging
    if "scheduled upgrade" in message.lower():
        send_to_platform_team(message, priority="medium")
    elif "end of support" in message.lower():
        days_until_eos = extract_timeline(message)
        priority = "critical" if days_until_eos < 7 else "high"
        send_to_platform_team(message, priority=priority)
    elif "deprecated api" in message.lower():
        send_to_dev_team(message, priority="high")
    elif "upgrade failed" in message.lower():
        page_oncall(message, priority="critical")
    else:
        send_to_platform_team(message, priority="low")
```

### Notification Routing Rules

**Platform Team Slack Channel:**
- Auto-upgrade scheduled (all clusters)
- EoS warnings (all environments)
- Version available (prod clusters only)

**Dev Team Slack Channel:**
- Deprecated API usage
- Version available (dev/staging clusters)

**PagerDuty/On-call:**
- Upgrade failures
- EoS warnings <7 days
- Security patches causing issues

**Email Digest (Weekly):**
- Version available notifications
- Low-priority maintenance items

## Standard Operating Procedures

### Weekly GKE Upgrade Review (15 minutes)

**Review dashboard:**
1. Check GKE release schedule: [release schedule page](https://cloud.google.com/kubernetes-engine/docs/release-schedule)
2. Review upgrade notifications from past week
3. Check cluster versions against support timeline
4. Plan upcoming upgrades for next 2-4 weeks

**Use this checklist:**
```
Weekly GKE Review Checklist:
- [ ] Any clusters approaching EoS in next 60 days?
- [ ] Any scheduled auto-upgrades need deferral?
- [ ] Deprecated API usage insights to address?
- [ ] Release notes review for upcoming versions
- [ ] Staging environment upgrade testing needed?
```

### Emergency Response: Unexpected Auto-upgrade

**If you get surprised by an auto-upgrade:**

1. **Don't panic** - auto-upgrades are tested and generally safe
2. **Monitor immediately:**
   ```bash
   # Check cluster health
   kubectl get nodes
   kubectl get pods -A | grep -v Running
   
   # Check application health
   curl -f https://your-app-healthcheck-endpoint
   ```
3. **Check for known issues** in GKE release notes
4. **If issues found:**
   - Apply maintenance exclusion to prevent further upgrades
   - Consider rollback (contact GKE support for control plane rollback)

### Maintenance Exclusion Cheat Sheet

```bash
# Emergency freeze (30 days max, blocks everything)
gcloud container clusters update CLUSTER \
  --add-maintenance-exclusion-scope no_upgrades \
  --add-maintenance-exclusion-start $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end $(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ)

# Block minor versions only (allows security patches)
gcloud container clusters update CLUSTER \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# View current exclusions
gcloud container clusters describe CLUSTER --zone ZONE \
  --format="value(maintenancePolicy.window.maintenanceExclusions)"
```

## Notification Sources Setup

### Enable Scheduled Upgrade Notifications (Preview)
```bash
# Get 72h advance warning for control plane upgrades
gcloud container clusters update CLUSTER_NAME \
  --send-scheduled-upgrade-notifications
```

### Cloud Logging Query for Manual Monitoring
```
resource.type="gke_cluster"
protoPayload.serviceName="container.googleapis.com"
(
  protoPayload.metadata.operationType=~"(UPDATE_CLUSTER|UPGRADE_MASTER|UPGRADE_NODES)" OR
  jsonPayload.reason=~"(UpgradeEvent|MaintenanceEvent)" OR
  textPayload=~"(end.of.support|deprecated)"
)
```

### Pub/Sub Integration
Subscribe to GKE cluster notifications via Cloud Pub/Sub for programmatic handling:
```bash
# Create topic and subscription for cluster events
gcloud pubsub topics create gke-cluster-events
gcloud pubsub subscriptions create gke-alerts --topic=gke-cluster-events
```

## Key Recommendations

1. **Default to allowing auto-upgrades** - they're safer than delaying
2. **Only defer during code freezes or critical issues** - don't make it the norm
3. **Prioritize deprecated API fixes** - these will break future upgrades
4. **Use staging environments** to validate versions before production
5. **Set up proper monitoring** so you know when upgrades complete successfully
6. **Don't ignore EoS warnings** - force-upgrades are harder to handle than planned ones

This triage system helps you focus on notifications that actually need action while filtering out the informational noise.