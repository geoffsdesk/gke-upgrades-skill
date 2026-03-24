# GKE Notification Triage System

## Notification Types & Required Actions

### 🚨 **URGENT - Immediate Action Required**

| Notification | Timeline | Action Required |
|-------------|----------|-----------------|
| **End of Support (EoS) Warning - 30 days** | Next 30 days | Plan manual upgrade or apply maintenance exclusion |
| **End of Support (EoS) Warning - 7 days** | Next 7 days | Execute upgrade immediately or apply emergency exclusion |
| **Security Advisory - Critical CVE** | 24-48 hours | Review patch availability, plan emergency upgrade |
| **Deprecated API Usage Blocking Auto-upgrade** | ASAP | Fix deprecated APIs or upgrade will fail |

### ⚠️ **HIGH PRIORITY - Action in 1-2 weeks**

| Notification | Timeline | Action Required |
|-------------|----------|-----------------|
| **Auto-upgrade Scheduled (72h notice)** | 3 days | Review readiness, apply exclusion if needed |
| **Version Skew Warning (nodes 2+ minor behind)** | 1-2 weeks | Plan node pool upgrades |
| **Extended Support Ending** | 1 month | Migrate to supported version or renew Extended |

### 📋 **MEDIUM PRIORITY - Plan & Schedule**

| Notification | Timeline | Action Required |
|-------------|----------|-----------------|
| **New Minor Version Available** | 1-2 months | Evaluate for staging → prod rollout |
| **Release Channel Version Promotion** | 1-3 months | Plan upgrade path if ahead of channel |
| **Maintenance Window Recommendations** | Next quarter | Review and optimize maintenance windows |

### ℹ️ **INFORMATIONAL - No Immediate Action**

| Notification | Action |
|-------------|--------|
| **Auto-upgrade Completed Successfully** | Log for audit trail |
| **Patch Version Available** | Monitor - auto-upgrades will handle |
| **Beta Feature Announcements** | Evaluate for future adoption |
| **Regional Rollout Progress** | Awareness only |

## Triage Decision Tree

```
📧 GKE Notification Received
    ↓
❓ Contains "End of Support" or "EoS"?
    YES → 🚨 URGENT
    NO ↓
    
❓ Contains "scheduled" + specific date ≤ 7 days?
    YES → ⚠️ HIGH PRIORITY  
    NO ↓
    
❓ Contains "deprecated API" or "upgrade blocked"?
    YES → 🚨 URGENT
    NO ↓
    
❓ Contains "security" + "critical" or "CVE"?
    YES → 🚨 URGENT
    NO ↓
    
❓ Contains "available" or "recommended"?
    YES → 📋 MEDIUM PRIORITY
    NO ↓
    
❓ Contains "completed" or "successful"?
    YES → ℹ️ INFORMATIONAL
```

## Action Playbooks

### 🚨 URGENT: EoS Warning (30/7 days)

**Immediate assessment:**
```bash
# Check current version and EoS timeline
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

**Options (choose one):**

**Option A - Manual upgrade (recommended):**
```bash
# Plan upgrade to next minor version
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --cluster-version TARGET_VERSION
```

**Option B - Emergency exclusion (buys 30 days):**
```bash
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "emergency-eos-$(date +%Y%m%d)" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades
```

### ⚠️ HIGH PRIORITY: Auto-upgrade Scheduled (72h)

**Quick readiness check:**
```bash
# Verify no deprecated APIs
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Check PDBs aren't overly restrictive
kubectl get pdb -A -o wide

# Confirm no bare pods
kubectl get pods -A -o json | jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

**If NOT ready, apply exclusion:**
```bash
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "prep-needed-$(date +%Y%m%d)" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades
```

### 🚨 URGENT: Deprecated API Usage

**Identify specific deprecated APIs:**
```bash
# Get detailed breakdown
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=REGION \
  --project=PROJECT_ID \
  --filter="category=SECURITY"
```

**Fix deprecated APIs before next auto-upgrade attempt:**
- Update Helm charts to non-deprecated API versions
- Migrate custom resources to current API versions
- Update CI/CD pipelines using deprecated `kubectl apply` calls

## Notification Configuration

### Enable Proactive Notifications

```bash
# Enable scheduled upgrade notifications (72h advance notice)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --notification-config-mode=ENABLED

# Set up Pub/Sub topic for cluster events
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --enable-notification \
  --notification-topic=projects/PROJECT_ID/topics/gke-notifications
```

### Cloud Logging Queries for Monitoring

**Auto-upgrade events:**
```
resource.type="gke_cluster"
protoPayload.methodName="google.container.v1.ClusterManager.UpdateCluster"
protoPayload.metadata.operationType=~"(UPDATE_CLUSTER|UPGRADE_MASTER)"
```

**EoS enforcement events:**
```
resource.type="gke_cluster"
protoPayload.request.update.desiredMasterVersion!=""
protoPayload.metadata.reason="VERSION_END_OF_LIFE"
```

## Team Responsibilities Matrix

| Role | Urgent | High Priority | Medium Priority | Informational |
|------|--------|---------------|-----------------|---------------|
| **Platform Team** | Immediate response | Primary owner | Plan & schedule | Archive |
| **Dev Teams** | Provide app context | Test readiness | Evaluate features | Monitor |
| **SRE/Ops** | Execute fixes | Monitor progress | Review patterns | Audit trail |
| **Security Team** | CVE assessment | Patch validation | Policy updates | Compliance |

## Automation Recommendations

### Slack/Email Routing Rules

```yaml
# Example routing logic for alert management
if notification.contains("End of Support"):
  route_to: ["platform-team", "sre-oncall"]
  priority: "P0"
elif notification.contains("scheduled") and days_until <= 3:
  route_to: ["platform-team"]  
  priority: "P1"
elif notification.contains("deprecated API"):
  route_to: ["dev-teams", "platform-team"]
  priority: "P0"
elif notification.contains("completed"):
  route_to: ["audit-channel"]
  priority: "P4"
```

### Dashboard Metrics to Track

- Days until next EoS across all clusters
- Clusters with deprecated API usage
- Scheduled auto-upgrades in next 7 days
- Version skew violations (nodes >2 minor versions behind)
- Clusters on legacy "No channel" (migration candidates)

This triage system ensures your team focuses on notifications requiring immediate action while staying informed about the broader GKE upgrade lifecycle. The key insight: **most GKE notifications are informational** — your release channels + maintenance windows handle routine upgrades automatically.