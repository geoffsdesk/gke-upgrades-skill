# GKE Upgrade Notification Triage System

## Notification Types & Actions

| Notification Type | Example Subject/Content | Action Required | Timeline | Priority |
|------------------|------------------------|-----------------|-----------|-----------|
| **Auto-upgrade scheduled** | "Auto-upgrade scheduled for cluster X" | Monitor only (unless you need to defer) | ~7-14 days notice | Low-Medium |
| **Version available** | "New GKE version available" | No action (informational) | Ongoing | Low |
| **End-of-life warning** | "Version X.Y will reach EoL on DATE" | Plan upgrade or apply exclusion | 30-90 days notice | High |
| **Security patch** | "Security update available/applied" | Monitor application health | Immediate-7 days | Medium-High |
| **Maintenance window conflict** | "Upgrade deferred due to maintenance window" | Review window configuration | As needed | Medium |
| **Upgrade failed/stuck** | "Upgrade operation failed" | Investigate and remediate | Immediate | Critical |

## Triage Decision Tree

```
┌─ Receive GKE notification
│
├─ Contains "End-of-Life" or "EoL"?
│  └─ YES → HIGH PRIORITY
│     ├─ Check timeline (usually 30-90 days)
│     ├─ Plan upgrade or apply maintenance exclusion
│     └─ Add to upgrade roadmap
│
├─ Contains "failed" or "stuck"?
│  └─ YES → CRITICAL PRIORITY
│     ├─ Check cluster health immediately
│     ├─ Follow troubleshooting runbook
│     └─ Escalate to on-call if needed
│
├─ Contains "scheduled" and mentions specific date/time?
│  └─ YES → MEDIUM PRIORITY (Auto-upgrade)
│     ├─ Check if timing conflicts with critical periods
│     ├─ Apply "no upgrades" exclusion if needed (30-day max)
│     ├─ Otherwise, let auto-upgrade proceed
│     └─ Monitor during maintenance window
│
├─ Contains "available" but no dates?
│  └─ YES → LOW PRIORITY (Informational)
│     ├─ File for future reference
│     └─ No immediate action required
│
└─ Contains "security" or "patch"?
   └─ YES → MEDIUM-HIGH PRIORITY
      ├─ Monitor application health post-patch
      ├─ Check for any workload issues
      └─ Log in incident tracking if problems occur
```

## Standard Response Playbook

### HIGH PRIORITY: End-of-Life Warnings

**Sample notification:** *"GKE version 1.28.x will reach end-of-life on March 15, 2025. Clusters will be automatically upgraded to 1.29.x after this date."*

**Response checklist:**
- [ ] Check which clusters are affected: `gcloud container clusters list --format="table(name,zone,currentMasterVersion)" | grep "1.28"`
- [ ] Review upgrade timeline (typically 30-90 days notice)
- [ ] Decide: proactive upgrade or wait for auto-upgrade?
- [ ] If deferring: apply maintenance exclusion (max 30 days past EoL)
- [ ] Add to team's upgrade planning board/calendar
- [ ] Test target version in dev/staging environment

**Commands:**
```bash
# Check affected clusters
gcloud container clusters list --format="table(name,zone,currentMasterVersion)" | grep "VERSION_PATTERN"

# Apply 30-day "no upgrades" exclusion to defer past EoL if needed
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "eol-defer" \
  --add-maintenance-exclusion-start-time $(date -Iseconds) \
  --add-maintenance-exclusion-end-time $(date -d "+30 days" -Iseconds) \
  --add-maintenance-exclusion-scope no_upgrades
```

### MEDIUM PRIORITY: Auto-upgrade Scheduled

**Sample notification:** *"Auto-upgrade scheduled for cluster 'prod-cluster-1' on Saturday, January 20th at 02:00 UTC. Control plane will be upgraded to 1.29.8-gke.1031000."*

**Response checklist:**
- [ ] Check if timing conflicts with critical business periods (BFCM, quarter-end, etc.)
- [ ] Verify maintenance window aligns with your off-peak hours
- [ ] If timing is problematic: apply "no upgrades" exclusion (30-day max)
- [ ] If timing is acceptable: monitor during the window
- [ ] Ensure on-call rotation is aware
- [ ] Pre-stage rollback plan if needed

**Commands:**
```bash
# Check current maintenance window
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(maintenancePolicy)"

# Apply temporary "no upgrades" exclusion if timing conflicts
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "business-critical-period" \
  --add-maintenance-exclusion-start-time START_TIME \
  --add-maintenance-exclusion-end-time END_TIME \
  --add-maintenance-exclusion-scope no_upgrades
```

### CRITICAL PRIORITY: Upgrade Failed

**Sample notification:** *"Upgrade operation for cluster 'prod-cluster-1' has failed. Node pool 'default-pool' is experiencing issues during version transition."*

**Immediate response:**
- [ ] Check cluster health: `kubectl get nodes`
- [ ] Identify stuck/failed operations: `gcloud container operations list --cluster CLUSTER_NAME --zone ZONE`
- [ ] Follow troubleshooting runbook (check PDBs, resource constraints, bare pods)
- [ ] Escalate to GKE support if no clear resolution within 2 hours
- [ ] Notify stakeholders of potential service impact

### LOW PRIORITY: Version Available

**Sample notification:** *"GKE version 1.29.9-gke.1234000 is now available in the Regular release channel."*

**Response:**
- [ ] File in team knowledge base or changelog
- [ ] Review release notes if planning near-term upgrades
- [ ] No immediate action required

## Notification Management Setup

### Email filters and labels

Set up filters in your email system:

| Filter Criteria | Label | Action |
|----------------|-------|---------|
| Subject contains "end-of-life" OR "EoL" | `GKE-EoL-WARNING` | Mark important, forward to team |
| Subject contains "failed" OR "stuck" | `GKE-CRITICAL` | Mark urgent, send SMS/Slack alert |
| Subject contains "scheduled" AND date | `GKE-AUTO-UPGRADE` | Calendar reminder 24h before |
| Subject contains "available" | `GKE-INFO` | Archive, low priority |
| Subject contains "security" OR "patch" | `GKE-SECURITY` | Monitor for 48h post-notification |

### Team notification routing

```
┌─ GKE Notifications (service account email)
│
├─ EoL warnings → Platform team + Engineering leads
├─ Failed upgrades → On-call engineer + Platform team  
├─ Scheduled upgrades → Platform team only
├─ Security patches → Platform team + Security team
└─ Version available → Platform team (automated filing)
```

### Automation opportunities

**Slack integration example:**
```bash
# Webhook for critical notifications
curl -X POST -H 'Content-type: application/json' \
  --data '{"text":"🚨 GKE Upgrade Failed: CLUSTER_NAME in ZONE"}' \
  YOUR_SLACK_WEBHOOK_URL
```

**Calendar integration:**
- Parse "scheduled" notifications to auto-create calendar events
- Set reminders 24h and 2h before scheduled maintenance
- Include runbook links and on-call rotation in event description

## Documentation Templates

### For EoL Planning

```markdown
# EoL Response: GKE Version X.Y

**Timeline:** EoL date: DATE
**Affected clusters:** LIST
**Response chosen:** [ ] Proactive upgrade [ ] Wait for auto-upgrade [ ] Apply exclusion

## Upgrade plan
- Pre-upgrade testing in dev: DATE  
- Staging upgrade: DATE
- Production upgrade: DATE
- Rollback plan: LINK

## Dependencies
- Application compatibility verified: Y/N
- Database migration needed: Y/N
- Third-party integrations tested: Y/N
```

### For Post-Incident (Failed Upgrade)

```markdown  
# Upgrade Incident: CLUSTER_NAME

**Timeline:** Started: TIME | Resolved: TIME
**Root cause:** PDB blocking drain / Resource constraints / Other
**Resolution:** DESCRIPTION
**Impact:** Service degradation Y/N, Duration: X hours

## Lessons learned
- Monitoring gap: DESCRIPTION
- Process improvement: DESCRIPTION  
- Prevention: DESCRIPTION
```

## Monitoring and Metrics

Track these metrics to improve your upgrade process:

- **Time to respond** to EoL notifications (target: <48h)
- **Upgrade success rate** (target: >95%)
- **Mean time to resolution** for failed upgrades (target: <4h)
- **Proactive vs reactive** upgrades (shift toward proactive)

Use this triage system to convert notification noise into actionable workflows. The key is distinguishing between "act now" (EoL, failures) and "monitor" (scheduled, available) notifications.