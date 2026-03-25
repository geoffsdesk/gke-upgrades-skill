# GKE Maintenance Configuration for Regulated Financial Services Environment

## Configuration Overview

For SOX compliance and financial services regulations, I'm recommending the **Extended release channel** with **"no minor or node upgrades" exclusions** plus **disruption intervals**. This gives you maximum control while maintaining security compliance through automatic control plane patches.

## Recommended Configuration Commands

### 1. Migrate to Extended Channel (if not already)

```bash
# Check current channel first
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="value(releaseChannel.channel)"

# Migrate each cluster to Extended channel
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel extended
```

**Why Extended:** Up to 24 months support, no auto-minor upgrades (you control when), only patches auto-applied. Cost applies only during extended support period (months 15-24).

### 2. Configure Weekend-Only Maintenance Windows

```bash
# Saturday 2-6 AM maintenance window (4-hour window)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-window-start "2026-01-04T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### 3. Apply Persistent Maintenance Exclusions

```bash
# "No minor or node upgrades" - allows CP security patches, blocks disruptive changes
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "sox-compliance-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

This exclusion:
- ✅ Allows control plane security patches (SOX compliance requirement)
- ❌ Blocks minor version upgrades (you control timing)
- ❌ Blocks node pool upgrades (you control timing)
- 🔄 Auto-renews when you manually upgrade to new minor versions

### 4. Set Disruption Intervals (Upgrade Frequency Control)

```bash
# Patch upgrades: maximum once every 90 days
# Minor upgrades: maximum once every 90 days (when you trigger them)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-patch-version-disruption-interval=7776000s \
  --maintenance-minor-version-disruption-interval=7776000s
```

## Quarterly Code Freeze Configuration

For your quarterly code freezes, add temporary "no upgrades" exclusions:

```bash
# Q4 2024 Code Freeze (example dates)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "q4-2024-code-freeze" \
  --add-maintenance-exclusion-start-time "2024-12-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# Q1 2025 Code Freeze (example dates)  
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "q1-2025-code-freeze" \
  --add-maintenance-exclusion-start-time "2025-03-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-04-14T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**Important:** "No upgrades" exclusions are limited to 30 days each. For longer quarterly freezes, chain multiple exclusions with small gaps.

## November Audit Period

```bash
# November audit freeze (blocks ALL upgrades including patches)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "november-audit-2024" \
  --add-maintenance-exclusion-start-time "2024-11-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-11-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Complete Configuration Template

Apply this to all 3 clusters (replace `CLUSTER_NAME` and `REGION`):

```bash
#!/bin/bash
CLUSTERS=("prod-cluster-1" "prod-cluster-2" "prod-cluster-3")
REGION="us-central1"

for CLUSTER in "${CLUSTERS[@]}"; do
  echo "Configuring $CLUSTER..."
  
  # Extended channel
  gcloud container clusters update $CLUSTER \
    --region $REGION \
    --release-channel extended
  
  # Weekend maintenance window (Saturday 2-6 AM)
  gcloud container clusters update $CLUSTER \
    --region $REGION \
    --maintenance-window-start "2026-01-04T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
  
  # Persistent exclusion for max control
  gcloud container clusters update $CLUSTER \
    --region $REGION \
    --add-maintenance-exclusion-name "sox-compliance-control" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
  
  # Disruption intervals (90-day minimum between upgrades)
  gcloud container clusters update $CLUSTER \
    --region $REGION \
    --maintenance-patch-version-disruption-interval=7776000s \
    --maintenance-minor-version-disruption-interval=7776000s
  
  echo "$CLUSTER configured successfully"
done
```

## Operational Workflow

### Normal State
- **Control plane patches:** Auto-applied within Saturday 2-6 AM window, maximum once per 90 days
- **Minor version upgrades:** Manual only (you trigger when ready)
- **Node pool upgrades:** Manual only (you trigger when ready)

### Quarterly Upgrades (Recommended)
1. Plan minor upgrades during non-freeze periods
2. Test in dev/staging first  
3. Manually trigger production upgrades:
   ```bash
   # Control plane first
   gcloud container clusters upgrade CLUSTER_NAME \
     --region REGION \
     --master \
     --cluster-version TARGET_VERSION
   
   # Then node pools (one at a time)
   gcloud container node-pools upgrade NODE_POOL_NAME \
     --cluster CLUSTER_NAME \
     --region REGION \
     --cluster-version TARGET_VERSION
   ```

## Monitoring and Compliance

### Enable Upgrade Notifications
```bash
# 72-hour advance notifications for control plane upgrades
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --send-scheduled-upgrade-notifications
```

### Monitoring Queries
Monitor exclusions and upgrade events in Cloud Logging:
```
resource.type="gke_cluster"
protoPayload.metadata.operationType=~"(UPDATE_CLUSTER|UPGRADE_MASTER)"
```

## Key Benefits for SOX Compliance

✅ **Predictable timing:** Upgrades only during approved Saturday windows  
✅ **Change control:** Minor upgrades require manual approval/trigger  
✅ **Security compliance:** Control plane patches auto-applied for CVE response  
✅ **Audit trail:** All upgrade events logged to Cloud Logging  
✅ **Extended support:** Up to 24 months on each version reduces upgrade pressure  
✅ **Code freeze protection:** Temporary exclusions during sensitive periods  

This configuration ensures you maintain security posture while having maximum control over disruptive changes, perfect for regulated financial services environments.