# GKE Fleet Health Recovery Plan

You've inherited a classic "snowflake fleet" — clusters with frozen versions that have drifted from automated lifecycle management. Here's how to systematically restore them to a healthy, well-managed state using GKE's self-service assessment tools.

## Phase 1: Fleet Assessment & Discovery

### Inventory your fleet using GKE's built-in tools

```bash
# Get all clusters with versions and channels across your org
for project in $(gcloud projects list --format="value(projectId)"); do
  echo "=== Project: $project ==="
  gcloud container clusters list \
    --project=$project \
    --format="table(name,location,currentMasterVersion,releaseChannel.channel,status)" 2>/dev/null || true
done
```

**GKE Fleet Console Dashboard** — Your primary assessment tool:
- Navigate to GKE → Overview → Fleet view in the Cloud Console
- Shows all clusters across projects with health indicators
- Filters for version skew, deprecated APIs, EoS warnings
- Export to CSV for spreadsheet analysis

### Use GKE Deprecation Insights (critical for upgrade planning)

```bash
# Check deprecated API usage across all clusters
for project in $(gcloud projects list --format="value(projectId)"); do
  echo "=== Deprecation insights for $project ==="
  gcloud recommender insights list \
    --project=$project \
    --insight-type=google.container.DiagnosisInsight \
    --location=- \
    --format="table(name,category,description)" 2>/dev/null || true
done
```

**What this catches:** Deprecated APIs that will BREAK on upgrade. GKE automatically pauses auto-upgrades when it detects deprecated API usage, so this is your #1 blocker list.

### Check End of Support status

```bash
# Get EoS timestamps and auto-upgrade targets for each cluster
gcloud container clusters get-upgrade-info CLUSTER_NAME \
  --region REGION \
  --format="yaml(endOfStandardSupportTimestamp,endOfExtendedSupportTimestamp,autoUpgradeStatus)"
```

**GKE Release Schedule** — Your planning bible: https://cloud.google.com/kubernetes-engine/docs/release-schedule
- Shows current supported versions per channel
- EoS dates for all versions
- Estimated auto-upgrade timeline

## Phase 2: Categorize & Prioritize

Group your clusters by risk level:

### **🚨 Critical (upgrade immediately)**
- Versions at or past End of Support
- Active deprecated API usage blocking auto-upgrades
- "No channel" clusters on unsupported versions

### **⚠️ High Risk (upgrade within 30 days)**
- "No channel" clusters approaching EoS
- Version skew >1 minor version between control plane and nodes
- Clusters without maintenance windows or exclusions

### **📋 Medium Risk (standardize within 90 days)**
- Inconsistent release channels across environments
- Missing PDBs on critical workloads
- Ad hoc upgrade strategies

### **✅ Low Risk (optimize over time)**
- Supported versions but suboptimal channels
- Missing monitoring/alerting on upgrades

## Phase 3: Emergency Fixes (Week 1-2)

### Fix deprecated API usage FIRST

This is your #1 blocker. For each cluster with deprecation insights:

```bash
# Get specific deprecated API calls
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Common fixes:
kubectl get deployments -o yaml | grep -i "extensions/v1beta1\|apps/v1beta1"
kubectl get ingress -o yaml | grep -i "extensions/v1beta1"
kubectl get psp -o yaml  # PodSecurityPolicy removed in 1.25+
```

**Fix workflow:**
1. Identify deprecated resources: `kubectl api-resources --verbs=list --namespaced -o name | xargs -n 1 kubectl get --show-kind --ignore-not-found`
2. Update YAML files to supported API versions
3. Apply changes: `kubectl apply -f fixed-manifests/`
4. Verify: Check GKE deprecation insights clear within 24 hours

### Migrate "No channel" clusters to release channels

**For production clusters:**
```bash
# Move to Regular channel (balanced, full SLA)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel regular
```

**For maximum control environments (financial services, compliance):**
```bash
# Move to Extended channel + "no minor or node" exclusion
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel extended \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Migration warning:** If your current version isn't available in the target channel yet, the cluster will be "ahead of channel" and won't receive auto-upgrades until the channel catches up. Check version availability first: https://cloud.google.com/kubernetes-engine/docs/release-schedule

### Apply maintenance windows immediately

```bash
# Add predictable upgrade timing (example: Saturday 2-6 AM)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-window-start "2026-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Phase 4: Systematic Fleet Recovery (Month 1-3)

### Establish environment topology standards

**Recommended pattern:**
- **Dev/Test:** Regular channel (gets versions faster for testing)
- **Staging:** Regular channel (same as production)  
- **Production:** Regular or Stable channel (your choice based on risk tolerance)

**Anti-pattern to avoid:** Different channels per environment (dev=Rapid, prod=Stable) makes version drift inevitable and rollout sequencing impossible.

### Configure upgrade controls per environment

**Development clusters:**
```bash
gcloud container clusters update DEV_CLUSTER \
  --release-channel regular
  # Let auto-upgrades flow freely
```

**Production clusters (standard approach):**
```bash
gcloud container clusters update PROD_CLUSTER \
  --release-channel regular \
  --maintenance-window-start "2026-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Production clusters (maximum control approach):**
```bash
gcloud container clusters update PROD_CLUSTER \
  --release-channel regular \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --maintenance-patch-version-disruption-interval=7776000s \  # 90 days between patches
  --maintenance-window-start "2026-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### Set up fleet monitoring & alerting

**Cloud Logging queries for upgrade events:**
```bash
# EoS warnings and forced upgrades
resource.type="gke_cluster"
protoPayload.metadata.operationType=~"(UPDATE_CLUSTER|UPGRADE_MASTER)"
severity>=WARNING

# PDB violations during upgrades
resource.type="gke_cluster"
jsonPayload.reason="EvictionBlocked"
```

**Subscribe to upgrade notifications:**
```bash
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --send-scheduled-upgrade-notifications  # 72h advance notice
```

## Phase 5: Workload Hardening (Month 2-4)

### Add PDBs to critical workloads

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: app-pdb
spec:
  minAvailable: 2  # or 50%
  selector:
    matchLabels:
      app: critical-app
```

### Fix common upgrade blockers

**Eliminate bare pods:**
```bash
# Find bare pods (no owner references)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Wrap in Deployments or delete
```

**Resource requests for Autopilot:**
```bash
# All containers MUST have CPU/memory requests on Autopilot
kubectl get pods -A -o json | \
  jq '.items[] | select(.spec.containers[].resources.requests | not)'
```

## GKE Self-Service Assessment Tools Summary

| Tool | What it shows | How to access |
|------|---------------|---------------|
| **Fleet Console Dashboard** | Multi-cluster health, version skew, EoS status | GKE → Overview → Fleet view |
| **Deprecation Insights** | Deprecated API usage blocking upgrades | `gcloud recommender insights list --insight-type=google.container.DiagnosisInsight` |
| **Upgrade Info API** | Auto-upgrade targets, EoS dates, rollback status | `gcloud container clusters get-upgrade-info` |
| **Release Schedule** | Version availability, upgrade timeline per channel | https://cloud.google.com/kubernetes-engine/docs/release-schedule |
| **Server Config** | Available versions per channel in your region | `gcloud container get-server-config --format="yaml(channels)"` |
| **Scheduled Notifications** | 72h advance upgrade warnings | Cloud Logging (opt-in per cluster) |

## Success Metrics

Track your fleet health recovery with these KPIs:

- **% clusters on supported versions** (target: 100%)
- **% clusters on release channels** (target: 100%, eliminate "No channel")
- **Mean version age** (target: <3 months behind latest)
- **Deprecated API violations** (target: 0)
- **Clusters with maintenance windows** (target: 100%)
- **Failed auto-upgrades per month** (target: <5%)

## Long-term Fleet Management Best Practices

Once you've restored health:

1. **Establish upgrade SLOs:** Dev gets new versions within 2 weeks, prod within 4 weeks
2. **Automate deprecated API scanning** in CI/CD pipelines
3. **Use rollout sequencing** for large fleets (5+ clusters): dev → staging → prod with soak times
4. **Regular fleet reviews:** Monthly check of version spread, quarterly channel strategy review
5. **Break-glass procedures:** Document how to apply "no upgrades" exclusions for emergencies (BFCM, etc.)

**Key insight:** Moving to automated upgrade lifecycle with appropriate controls (channels + windows + exclusions) is SAFER than manual version management. The self-service tools above help you maintain visibility while letting GKE handle the operational complexity of Kubernetes lifecycle management.

Your goal isn't to control every upgrade manually — it's to set the right policies and let GKE's automation work reliably within your constraints.