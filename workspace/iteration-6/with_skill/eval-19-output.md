# GKE Upgrade Notification Triage System

## Notification categorization and response matrix

| Notification Type | Urgency | Action Required | Response Timeline |
|------------------|---------|-----------------|-------------------|
| **Auto-upgrade scheduled (72h notice)** | Medium | Review/defer if needed | Within 24h |
| **Security patch available** | High | Plan immediate upgrade | Within 48h |
| **Version End-of-Life (EoS) warning** | High | Plan upgrade before EoS | Days to weeks |
| **New version available** | Low | Informational | No immediate action |
| **Maintenance window notification** | Medium | Verify timing acceptable | Within 12h |
| **Upgrade failed/stuck** | Critical | Immediate troubleshooting | Within 1h |

## Triage decision tree

### 1. Auto-upgrade scheduled notifications
**Example:** "Cluster 'prod-cluster' will be upgraded to 1.29.5-gke.1091002 in 72 hours"

**Response:**
- [ ] Check if upgrade timing conflicts with deployments, releases, or critical business periods
- [ ] If timing is bad: Apply 30-day "no upgrades" maintenance exclusion immediately
- [ ] If timing is acceptable: Let auto-upgrade proceed, monitor during maintenance window
- [ ] Verify target version has no known issues in GKE release notes

**Commands:**
```bash
# Defer upgrade with maintenance exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "defer-$(date +%Y%m%d)" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -d '+30 days' -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades
```

### 2. Security patch notifications
**Example:** "Security update available for Kubernetes 1.28 - CVE-2024-XXXX"

**Response:**
- [ ] **Always prioritize security patches** - these address vulnerabilities
- [ ] Review CVE details and assess impact to your workloads
- [ ] Plan upgrade within 48 hours for production clusters
- [ ] Test in dev/staging first if possible

**Commands:**
```bash
# Check available versions with security fixes
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels)" | grep -A 10 "channel: REGULAR"

# Immediate manual upgrade if urgent
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION
```

### 3. End-of-Life (EoS) warnings
**Example:** "Kubernetes version 1.27 will reach End of Support on X date"

**Response:**
- [ ] Note the EoS enforcement date - clusters will be force-upgraded after this
- [ ] Plan upgrade well before EoS (not at the last minute)
- [ ] Consider Extended release channel for 24-month support (versions 1.27+)
- [ ] If you need more time: use "no minor or node upgrades" exclusion up to EoS date

**Timeline planning:**
- 90+ days before EoS: Plan upgrade sequence
- 60 days before EoS: Start upgrade in dev/staging
- 30 days before EoS: Complete production upgrade
- 7 days before EoS: Emergency window if not complete

### 4. New version available notifications
**Example:** "Kubernetes 1.30 is now available in Regular channel"

**Response:**
- [ ] **No immediate action required** - this is informational
- [ ] Add to your upgrade roadmap for next planned maintenance cycle
- [ ] Review new features and changes when convenient
- [ ] Let auto-upgrade handle it during your maintenance window

### 5. Maintenance window notifications
**Example:** "Maintenance window starts in 2 hours for cluster X"

**Response:**
- [ ] Verify no critical deployments or releases scheduled during window
- [ ] Ensure on-call team is aware
- [ ] If timing is bad and you missed the 72h notice: apply emergency exclusion
- [ ] Monitor cluster health during window

## Notification routing and team responsibilities

### Email filtering rules

Set up email filters to route notifications appropriately:

```
Subject contains "auto-upgrade scheduled" → Platform team, Medium priority
Subject contains "security" OR "CVE" → Security + Platform team, High priority  
Subject contains "end-of-life" OR "end of support" → Platform team, High priority
Subject contains "version available" → Platform team, Low priority (weekly digest)
Subject contains "maintenance window" → Platform + On-call, Medium priority
Subject contains "failed" OR "stuck" → On-call team, Critical priority
```

### Response team assignments

| Notification Type | Primary Owner | Backup | Escalation |
|-------------------|---------------|--------|------------|
| Auto-upgrade scheduled | Platform team | DevOps lead | Engineering manager |
| Security patches | Security team | Platform team | CISO |
| EoS warnings | Platform team | DevOps lead | Engineering manager |
| Upgrade failures | On-call engineer | Platform team | Site reliability |
| New versions | Platform team | N/A | N/A |

## Proactive monitoring setup

Instead of reactive email triage, set up monitoring:

### Cloud Monitoring alerts
```yaml
# Alert on clusters approaching EoS
displayName: "GKE Version Approaching EoS"
conditions:
  - displayName: "Version EoS in 30 days"
    conditionThreshold:
      filter: 'resource.type="k8s_cluster"'
      comparison: COMPARISON_LESS_THAN
      thresholdValue: 30  # days until EoS
```

### Weekly cluster health report
```bash
#!/bin/bash
# Weekly cluster version report
echo "=== GKE Cluster Version Report ==="
for cluster in $(gcloud container clusters list --format="value(name,zone)"); do
  name=$(echo $cluster | cut -d' ' -f1)
  zone=$(echo $cluster | cut -d' ' -f2)
  
  echo "Cluster: $name"
  gcloud container clusters describe $name --zone $zone \
    --format="table(currentMasterVersion,releaseChannel.channel,nodePool[].version)"
  echo ""
done
```

## Maintenance exclusion strategy

Use maintenance exclusions strategically, not reactively:

### Standard exclusion periods
```bash
# Major release seasons (adjust for your calendar)
# Black Friday/Cyber Monday
--add-maintenance-exclusion-start-time 2024-11-20T00:00:00Z
--add-maintenance-exclusion-end-time 2024-12-05T00:00:00Z
--add-maintenance-exclusion-scope no_upgrades

# Year-end code freeze
--add-maintenance-exclusion-start-time 2024-12-15T00:00:00Z
--add-maintenance-exclusion-end-time 2025-01-15T00:00:00Z
--add-maintenance-exclusion-scope no_minor_or_node_upgrades  # Allow security patches
```

### Conservative approach for production
Use "no minor or node upgrades" exclusion to allow security patches while blocking disruptive changes:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "conservative-production" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time "2025-06-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

## Environment-specific responses

### Development clusters
- Auto-upgrades: Always allow (use for testing upcoming versions)
- Release channel: Rapid
- Security patches: Immediate, no testing needed
- New versions: Upgrade immediately for validation

### Staging clusters  
- Auto-upgrades: Allow with 1-week delay after dev
- Release channel: Regular
- Security patches: Within 24h after dev validation
- New versions: Upgrade 1-2 weeks after dev

### Production clusters
- Auto-upgrades: Allow only during maintenance windows
- Release channel: Stable or Regular  
- Security patches: Within 48h after staging validation
- New versions: Planned upgrades only, never reactive
- EoS: Upgrade completed 30+ days before enforcement

## Notification audit and tuning

### Monthly review questions
- [ ] Are we getting too many low-priority notifications?
- [ ] Did we miss any critical security patches?
- [ ] Are maintenance windows aligned with our actual low-traffic periods?
- [ ] Should any clusters move to Extended channel for slower upgrades?
- [ ] Are maintenance exclusions being used appropriately (not as permanent blocks)?

### Tuning recommendations
- **Too many notifications:** Move dev clusters to Rapid channel and reduce alerting
- **Missing critical updates:** Add security team to high-priority routing
- **Wrong timing:** Adjust maintenance windows to match actual traffic patterns
- **Upgrade anxiety:** Consider Extended channel for risk-averse production workloads

This triage system transforms reactive email panic into proactive cluster lifecycle management. The key is distinguishing between "needs immediate action" (security patches, EoS warnings, upgrade failures) and "plan for later" (new versions, scheduled auto-upgrades).