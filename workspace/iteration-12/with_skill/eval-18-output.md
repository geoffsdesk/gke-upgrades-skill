# GKE Maintenance Configuration for Financial Services Compliance

## Configuration Strategy for SOX Environment

Given your regulatory requirements, I'll set up a **conservative auto-upgrade strategy** with tight control over timing and scope. This approach balances security patching with operational stability during critical periods.

## Recommended Configuration

### 1. Maintenance Windows (Weekend-Only Auto-Upgrades)

Configure recurring weekend maintenance windows for all clusters:

```bash
# Apply to all 3 clusters
for CLUSTER in cluster-1 cluster-2 cluster-3; do
  gcloud container clusters update $CLUSTER \
    --zone YOUR_ZONE \
    --maintenance-window-start 2024-01-06T02:00:00Z \
    --maintenance-window-end 2024-01-06T06:00:00Z \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
done
```

**Rationale:** Saturday 2-6 AM UTC provides a 4-hour window during low-activity periods. Auto-upgrades will only occur during these windows.

### 2. Standing Maintenance Exclusion (Maximum Control)

For SOX compliance, I recommend the **"no minor or node upgrades"** exclusion as your baseline:

```bash
# Apply to all clusters - allows security patches, blocks disruptive changes
for CLUSTER in cluster-1 cluster-2 cluster-3; do
  gcloud container clusters update $CLUSTER \
    --zone YOUR_ZONE \
    --add-maintenance-exclusion-name "sox-compliance-control" \
    --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
    --add-maintenance-exclusion-end-time "2025-12-31T23:59:59Z" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades
done
```

**Why this exclusion:**
- ✅ **Security patches** continue automatically on control plane
- ❌ **Minor version upgrades** blocked (prevents Kubernetes API changes)
- ❌ **Node pool upgrades** blocked (prevents workload disruption)
- 📅 **Duration** tracks until version End of Support

### 3. Quarterly Code Freeze Protection

During quarterly code freezes, apply the strictest "no upgrades" exclusion:

```bash
# Example: Q1 2024 code freeze (blocks ALL upgrades including security patches)
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "q1-2024-code-freeze" \
  --add-maintenance-exclusion-start-time "2024-03-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-04-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**Template for all quarters:**
- Q1: March 15 - April 5
- Q2: June 15 - July 5  
- Q3: September 15 - October 5
- Q4: December 15 - January 5

### 4. Annual Audit Protection (November)

```bash
# November audit period - complete upgrade freeze
for CLUSTER in cluster-1 cluster-2 cluster-3; do
  gcloud container clusters update $CLUSTER \
    --zone YOUR_ZONE \
    --add-maintenance-exclusion-name "annual-sox-audit-2024" \
    --add-maintenance-exclusion-start-time "2024-11-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-11-30T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
done
```

## Release Channel Strategy

For SOX compliance, use the **Stable** channel:

```bash
# Migrate clusters to Stable channel (most validated versions)
for CLUSTER in cluster-1 cluster-2 cluster-3; do
  gcloud container clusters update $CLUSTER \
    --zone YOUR_ZONE \
    --release-channel stable
done
```

**Stable Channel Benefits:**
- Versions are thoroughly tested before reaching Stable
- Full SLA coverage for upgrade stability
- Slower release cadence reduces change frequency
- Better for compliance environments requiring stability

## Disruption Interval Configuration

Add disruption intervals to prevent back-to-back upgrades:

```bash
# Increase disruption intervals for more predictable upgrade cadence
for CLUSTER in cluster-1 cluster-2 cluster-3; do
  gcloud container clusters update $CLUSTER \
    --zone YOUR_ZONE \
    --maintenance-patch-version-disruption-interval 30 \
    --maintenance-minor-version-disruption-interval 90
done
```

**Effect:**
- Control plane patches: minimum 30 days between upgrades
- Minor versions: minimum 90 days between upgrades

## Node Pool Upgrade Strategy (Conservative)

For financial services, use conservative surge settings:

```bash
# Configure conservative surge settings per node pool
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone YOUR_ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Rationale:** `maxSurge=1, maxUnavailable=0` ensures:
- Only one additional node at a time
- Zero capacity reduction during upgrades
- Minimal blast radius if issues occur

## Compliance Monitoring Setup

### 1. Upgrade Notifications

Enable scheduled upgrade notifications for 72-hour advance notice:

```bash
# Configure Cloud Logging to capture GKE upgrade notifications
# (This is a logging filter - configure in Cloud Console → Logging → Create Sink)
```

**Filter:**
```
resource.type="gke_cluster"
protoPayload.methodName="google.container.v1.ClusterManager.UpdateCluster"
```

### 2. Version Tracking Commands

Regular compliance checks:

```bash
# Check current versions across all clusters
gcloud container clusters list --format="table(name,currentMasterVersion,status,location)"

# Check auto-upgrade status and EoS timeline
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Verify maintenance exclusions are active
gcloud container clusters describe CLUSTER_NAME --zone ZONE --format="yaml(maintenancePolicy)"
```

### 3. Audit Trail Documentation

Create a tracking spreadsheet with:
- **Planned maintenance windows**
- **Active exclusions and their business justification**
- **Version change log with approval timestamps**
- **Emergency patch procedures for critical vulnerabilities**

## Manual Upgrade Process for Controlled Updates

When you DO need to upgrade (between code freezes):

### Pre-Approval Checklist
```
SOX Upgrade Pre-Approval Checklist
- [ ] Change advisory board approval obtained
- [ ] Version tested in non-production environment
- [ ] Security team sign-off on new version
- [ ] Rollback plan documented and approved
- [ ] Maintenance window scheduled with stakeholders
- [ ] Audit documentation prepared
```

### Controlled Upgrade Commands
```bash
# 1. Remove standing exclusion temporarily
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --remove-maintenance-exclusion "sox-compliance-control"

# 2. Apply time-limited "no upgrades" exclusion to prevent auto-upgrade
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "manual-upgrade-window" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d "+2 hours" +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades

# 3. Perform manual upgrade during approved window
gcloud container clusters upgrade CLUSTER_NAME \
  --zone YOUR_ZONE \
  --cluster-version TARGET_VERSION

# 4. Re-apply standing exclusion after completion
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --remove-maintenance-exclusion "manual-upgrade-window" \
  --add-maintenance-exclusion-name "sox-compliance-control" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time "2025-12-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

## Summary Configuration

| Setting | Value | Justification |
|---------|--------|---------------|
| **Release Channel** | Stable | Most validated, compliance-friendly |
| **Maintenance Window** | Saturday 2-6 AM UTC | Weekend-only, low-impact hours |
| **Standing Exclusion** | "no minor or node upgrades" | Allows security patches, blocks disruption |
| **Code Freeze Exclusion** | "no upgrades" (30 days) | Complete freeze during critical periods |
| **Patch Disruption Interval** | 30 days | Reduces patch frequency |
| **Minor Disruption Interval** | 90 days | Conservative minor version cadence |
| **Surge Strategy** | maxSurge=1, maxUnavailable=0 | Risk-averse, maintains capacity |

This configuration ensures:
- ✅ **Security patches** continue automatically during non-freeze periods
- ✅ **Predictable timing** with weekend-only maintenance windows  
- ✅ **Complete control** during code freezes and audits
- ✅ **Audit compliance** with documented exclusions and approval processes
- ✅ **Emergency flexibility** with manual upgrade procedures

Would you like me to adjust any of these settings for your specific cluster names, time zones, or additional compliance requirements?