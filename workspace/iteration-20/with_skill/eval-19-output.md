# GKE Upgrade Notification Triage System

Here's a prioritization framework for GKE upgrade notifications to help you determine which require immediate action versus informational tracking.

## Notification Types & Response Matrix

| Notification Type | Urgency | Action Required | Timeline |
|------------------|---------|-----------------|----------|
| **Security patch available** | 🔴 HIGH | Plan upgrade within maintenance window | 7-14 days |
| **End-of-Support (EoS) warning** | 🔴 HIGH | Upgrade before EoS date | Varies by warning type |
| **Auto-upgrade scheduled** | 🟡 MEDIUM | Review/defer if needed | 72 hours before |
| **New version available** | 🟢 LOW | Informational - no action | None |
| **Deprecated API usage** | 🔴 HIGH | Fix before next minor upgrade | Before target version |
| **Auto-upgrade paused** | 🔴 HIGH | Fix blocking issue | Immediate |

## Detailed Triage Guide

### 🔴 HIGH Priority - Immediate Action Required

**1. Security patch notifications**
```
Subject: "Security patch available for GKE cluster..."
Content mentions: CVE numbers, security fixes
```
**Actions:**
- [ ] Review CVE details and impact to your workloads
- [ ] Schedule upgrade during next maintenance window
- [ ] For critical CVEs: consider emergency upgrade outside window
- [ ] If on Extended channel with accelerated patches: expect faster rollout

**2. End-of-Support (EoS) warnings**
```
Subject: "GKE version X.Y reaching end of support..."
Types: 30-day, 14-day, 7-day, final warnings
```
**Actions by warning type:**
- **30-day warning:** Plan upgrade path, test in staging
- **14-day warning:** Begin upgrade execution
- **7-day warning:** Complete upgrade or apply 30-day "no upgrades" exclusion
- **Final warning:** Forced upgrade imminent - complete within 48 hours

**3. Deprecated API usage detected**
```
Subject: "Deprecated API usage detected..."
Content: Lists deprecated APIs, target removal version
```
**Actions:**
- [ ] Run full API audit: `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated`
- [ ] Check GKE deprecation insights dashboard
- [ ] Update manifests/operators before next minor upgrade
- [ ] Note: Auto-upgrades are automatically paused until fixed

**4. Auto-upgrade paused**
```
Subject: "Auto-upgrade paused for cluster..."
Reasons: Deprecated APIs, resource constraints, validation failures
```
**Actions:**
- [ ] Fix root cause (usually deprecated API usage)
- [ ] Verify fix: deprecated API metrics should show zero usage
- [ ] Auto-upgrades resume automatically once issue resolved

### 🟡 MEDIUM Priority - Review & Plan

**5. Auto-upgrade scheduled**
```
Subject: "Scheduled upgrade for cluster X on DATE"
Contains: Specific date/time, target version
```
**Actions:**
- [ ] Review upgrade timing - does it conflict with critical business periods?
- [ ] Apply temporary "no upgrades" exclusion if deferral needed (max 30 days)
- [ ] Verify maintenance window aligns with preferences
- [ ] Ensure on-call coverage during upgrade window

**6. Version skew warnings**
```
Subject: "Node version significantly behind control plane"
Content: Control plane vs node version gap
```
**Actions:**
- [ ] Plan node pool upgrades - nodes can't be >2 minor versions behind CP
- [ ] Use skip-level upgrades where possible (e.g., 1.28→1.30) to reduce cycles
- [ ] For severely skewed pools (N+3): create new pools and migrate workloads

### 🟢 LOW Priority - Informational Only

**7. New version available**
```
Subject: "New GKE version X.Y.Z available in [channel]"
```
**Actions:**
- [ ] Note for planning purposes
- [ ] Review release notes for features/fixes of interest  
- [ ] No immediate action - auto-upgrade will occur per your channel/window settings

**8. Maintenance window reminders**
```
Subject: "Maintenance window active/upcoming"
```
**Actions:**
- [ ] Informational - confirms your settings are active
- [ ] Adjust if needed for upcoming critical periods

## Automated Triage Setup

### Email filters for prioritization

**High Priority Inbox Rule:**
```
Subject contains: "Security patch" OR "End of support" OR "Deprecated API" OR "Auto-upgrade paused"
Action: Mark as important, forward to oncall
```

**Medium Priority Rule:**
```
Subject contains: "Scheduled upgrade" OR "Version skew"
Action: Label "GKE-Review", add to planning backlog
```

**Low Priority Rule:**
```
Subject contains: "New version available" OR "Maintenance window"
Action: Label "GKE-Info", archive after reading
```

### Cloud Logging alerts

Set up log-based alerts for critical notifications:

```bash
# Alert on auto-upgrade pause
resource.type="gke_cluster"
protoPayload.metadata.operationType="UPGRADE_CLUSTER"
severity="ERROR"

# Alert on EoS enforcement
resource.type="gke_cluster" 
jsonPayload.message=~"end.of.support"
```

## Response Playbooks

### For Security Patches (HIGH)
1. **Assess impact:** Review CVE details vs your workload exposure
2. **Check staging:** Verify patch version works in dev/staging clusters
3. **Schedule upgrade:** Within 7-14 days via maintenance window
4. **Emergency process:** If critical CVE, use manual upgrade to bypass window

### For EoS Warnings (HIGH)
1. **30-day warning:** Plan upgrade path, update staging environment
2. **14-day warning:** Begin production upgrades, test rollback procedures  
3. **7-day warning:** Complete upgrade OR apply emergency exclusion
4. **Final warning:** Forced upgrade within 48 hours - all hands

### For Scheduled Auto-Upgrades (MEDIUM)
1. **Business impact check:** Any critical launches, BFCM, code freezes?
2. **Defer if needed:** Apply "no upgrades" exclusion (max 30 days)
3. **Confirm coverage:** Ensure on-call engineer available during window
4. **Validate timing:** Maintenance window aligns with off-peak hours

## Channel Strategy for Notification Management

**Recommended notification load per channel:**

| Channel | Notification Frequency | Best For |
|---------|----------------------|----------|
| **Stable** | Lowest - fewest notifications | Production, minimal interruption |
| **Regular** | Medium - balanced cadence | Most production workloads |
| **Rapid** | Highest - weekly notifications | Dev/test environments |
| **Extended** | Low patches + manual minor | Compliance environments |

**Multi-environment strategy:**
- Dev: Rapid (higher notification volume, earlier testing)
- Staging: Regular (production parity)  
- Production: Stable or Regular (controlled notification cadence)

## Notification Sources to Configure

Enable these GKE notification mechanisms:

1. **Cluster notifications** (essential):
   ```bash
   gcloud container clusters update CLUSTER_NAME \
     --enable-notification-config \
     --notification-config=pubsub=projects/PROJECT_ID/topics/TOPIC_NAME
   ```

2. **Scheduled upgrade notifications** (72h advance warning):
   ```bash
   gcloud container clusters update CLUSTER_NAME \
     --send-scheduled-upgrade-notifications
   ```

3. **Cloud Logging integration** for programmatic alerts
4. **GKE release schedule** bookmark for proactive planning

## Escalation Matrix

| Scenario | Primary Response | Escalation Path |
|----------|------------------|-----------------|
| Security patch available | Platform team plans upgrade | If critical CVE: immediate leadership notification |
| EoS final warning | Platform team executes emergency upgrade | If upgrade blocked: GKE support case |
| Auto-upgrade paused | Platform team fixes deprecated APIs | If unclear cause: GKE support case |
| Upgrade failure | Platform team troubleshoots via runbook | If >2 hours stuck: GKE support case |

This triage system helps you focus on notifications requiring immediate action while avoiding alert fatigue from informational updates. Adjust the urgency levels based on your organization's risk tolerance and operational maturity.