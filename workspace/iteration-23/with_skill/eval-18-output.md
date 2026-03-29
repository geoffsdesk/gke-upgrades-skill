# GKE Maintenance Configuration for Financial Services SOX Environment

Given your regulatory requirements, I'll configure maximum upgrade control while maintaining security compliance. Here's the recommended approach:

## Overall Strategy

**Release Channel:** Extended channel for maximum control and 24-month support
**Exclusion Type:** "No minor or node upgrades" - allows critical security patches but blocks disruptive changes
**Windows:** Saturday nights only for predictable timing
**Disruption Intervals:** 90-day minimums to control upgrade frequency

## Configuration Commands

### 1. Configure Each Cluster with Extended Channel + Persistent Exclusions

```bash
# Cluster 1
gcloud container clusters update CLUSTER-1-NAME \
    --zone ZONE-1 \
    --release-channel extended \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support \
    --maintenance-patch-version-disruption-interval=7776000s \
    --maintenance-window-start "2024-12-07T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Cluster 2  
gcloud container clusters update CLUSTER-2-NAME \
    --zone ZONE-2 \
    --release-channel extended \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support \
    --maintenance-patch-version-disruption-interval=7776000s \
    --maintenance-window-start "2024-12-07T04:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Cluster 3
gcloud container clusters update CLUSTER-3-NAME \
    --zone ZONE-3 \
    --release-channel extended \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support \
    --maintenance-patch-version-disruption-interval=7776000s \
    --maintenance-window-start "2024-12-07T06:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### 2. Quarterly Code Freeze Exclusions

For your quarterly code freezes, add temporary "no upgrades" exclusions:

```bash
# Q1 2025 Code Freeze (example dates - adjust to your schedule)
gcloud container clusters update CLUSTER-NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "Q1-2025-code-freeze" \
    --add-maintenance-exclusion-start-time "2025-03-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2025-04-15T00:00:00Z" \
    --add-maintenance-exclusion-scope no_upgrades
```

### 3. Annual November Audit Exclusion

```bash
# November 2024 Audit Period
gcloud container clusters update CLUSTER-NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "SOX-audit-2024" \
    --add-maintenance-exclusion-start-time "2024-11-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-12-01T00:00:00Z" \
    --add-maintenance-exclusion-scope no_upgrades
```

## What This Configuration Provides

### ✅ Compliance Benefits
- **Extended channel**: 24-month support lifecycle, delays EoS enforcement
- **"No minor or node" exclusion**: Prevents disruptive changes while allowing security patches
- **90-day patch intervals**: Control plane patches limited to once every 90 days maximum
- **Saturday-only windows**: Predictable timing aligned with maintenance schedules
- **Manual minor upgrades**: You control when Kubernetes minor versions are adopted

### ✅ Security Posture
- **Control plane security patches continue**: Critical vulnerabilities are still patched automatically
- **No indefinite freezing**: Persistent exclusions track EoS to prevent snowflaking
- **Regulated environment optimized**: Balances control with security requirements

### ✅ Operational Control
- **Staggered windows**: 2-hour gaps between clusters for sequential validation
- **Override capability**: Manual upgrades bypass all restrictions when needed
- **Audit trail**: All maintenance activities logged to Cloud Logging

## Managing Your Environment

### For Minor Version Upgrades (Your Control)
When you're ready to upgrade Kubernetes minor versions (e.g., 1.29 → 1.30):

1. **Test in non-production first**
2. **Manually trigger** during planned maintenance:
```bash
# Control plane first
gcloud container clusters upgrade CLUSTER-NAME \
    --zone ZONE \
    --master \
    --cluster-version 1.30.x-gke.xxxx

# Then node pools (exclusion doesn't block manual upgrades)
gcloud container node-pools upgrade POOL-NAME \
    --cluster CLUSTER-NAME \
    --zone ZONE \
    --cluster-version 1.30.x-gke.xxxx
```

### Monitoring and Alerts
Set up these monitoring queries in Cloud Logging:

```
# Scheduled upgrade notifications (72h advance notice)
resource.type="gke_cluster"
jsonPayload.eventType="ScheduledUpgrade"

# PDB violations during upgrades
resource.type="gke_cluster" 
jsonPayload.reason="POD_PDB_VIOLATION"

# Maintenance exclusion events
resource.type="gke_cluster"
protoPayload.metadata.operationType="UPDATE_CLUSTER"
protoPayload.request.update.desiredMaintenancePolicy:*
```

### Quarterly Planning Checklist

```markdown
- [ ] Review GKE release schedule for upcoming versions
- [ ] Plan minor version upgrades during approved change windows
- [ ] Update code freeze exclusions 30 days in advance
- [ ] Coordinate with audit team for November restrictions
- [ ] Test target versions in dev environment first
- [ ] Document all changes in SOX change management system
```

## Key Regulatory Considerations

**This configuration ensures:**
- ✅ **Change Control**: Manual approval required for disruptive upgrades
- ✅ **Audit Trail**: All activities logged and trackable
- ✅ **Security Compliance**: Critical patches still applied automatically
- ✅ **Predictable Timing**: Weekend-only maintenance windows
- ✅ **Extended Support**: 24-month lifecycle reduces upgrade pressure

**Important:** Extended channel incurs additional costs only during the extended support period (after standard 14-month support expires). There's no extra charge during the standard support period.

This setup gives you maximum control while maintaining Google's security patching. You'll manually control when major changes happen, but critical security fixes continue automatically within your defined windows and frequency limits.