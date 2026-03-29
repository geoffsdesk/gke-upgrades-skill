# GKE Maintenance Configuration for Regulated Environment

Based on your financial services/SOX compliance requirements, I'll configure a conservative maintenance strategy with maximum control while maintaining security posture.

## Recommended Configuration Strategy

For regulated environments, I recommend the **Extended channel + "no minor or node upgrades" exclusion** approach:
- Extended channel provides up to 24 months of support (cost only during extended period)
- Auto-applies control plane security patches (critical for compliance)
- Blocks disruptive minor version and node upgrades (maximum stability)
- Manual control over when major changes happen

## Configuration Commands

### 1. Set Weekend Maintenance Windows (All Clusters)

```bash
# Cluster 1
gcloud container clusters update CLUSTER_1_NAME \
    --zone ZONE_1 \
    --maintenance-window-start "2024-01-06T02:00:00Z" \
    --maintenance-window-end "2024-01-06T06:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Cluster 2  
gcloud container clusters update CLUSTER_2_NAME \
    --zone ZONE_2 \
    --maintenance-window-start "2024-01-06T03:00:00Z" \
    --maintenance-window-end "2024-01-06T07:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Cluster 3
gcloud container clusters update CLUSTER_3_NAME \
    --zone ZONE_3 \
    --maintenance-window-start "2024-01-06T04:00:00Z" \
    --maintenance-window-end "2024-01-06T08:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Note:** Staggered 1-hour intervals provide natural rollout sequencing if issues arise.

### 2. Migrate to Extended Channel (Maximum Control)

```bash
# All clusters - Extended channel for regulated environments
gcloud container clusters update CLUSTER_1_NAME \
    --zone ZONE_1 \
    --release-channel extended

gcloud container clusters update CLUSTER_2_NAME \
    --zone ZONE_2 \
    --release-channel extended

gcloud container clusters update CLUSTER_3_NAME \
    --zone ZONE_3 \
    --release-channel extended
```

### 3. Configure Persistent Maintenance Exclusions

```bash
# Maximum control: blocks minor versions AND node upgrades, allows CP patches
# Tracks End of Support automatically - no need to renew exclusions

gcloud container clusters update CLUSTER_1_NAME \
    --zone ZONE_1 \
    --add-maintenance-exclusion-name "sox-compliance-control" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support

gcloud container clusters update CLUSTER_2_NAME \
    --zone ZONE_2 \
    --add-maintenance-exclusion-name "sox-compliance-control" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support

gcloud container clusters update CLUSTER_3_NAME \
    --zone ZONE_3 \
    --add-maintenance-exclusion-name "sox-compliance-control" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

### 4. Set Disruption Intervals (Control Upgrade Frequency)

```bash
# Limit patches to maximum once every 90 days (regulatory-friendly)
gcloud container clusters update CLUSTER_1_NAME \
    --zone ZONE_1 \
    --maintenance-patch-version-disruption-interval=7776000s

gcloud container clusters update CLUSTER_2_NAME \
    --zone ZONE_2 \
    --maintenance-patch-version-disruption-interval=7776000s

gcloud container clusters update CLUSTER_3_NAME \
    --zone ZONE_3 \
    --maintenance-patch-version-disruption-interval=7776000s
```

## Handling Quarterly Code Freezes

For quarterly code freezes, add temporary "no upgrades" exclusions:

```bash
# Example: Q4 code freeze (blocks ALL upgrades including patches)
# Apply 2-3 weeks before freeze, remove after

gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "q4-code-freeze" \
    --add-maintenance-exclusion-start-time "2024-12-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-12-31T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades

# Remove after freeze ends
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --remove-maintenance-exclusion-name "q4-code-freeze"
```

## Annual November Audit Exclusion

```bash
# Block all upgrades during audit period (30-day maximum per exclusion)
# Chain exclusions if audit period exceeds 30 days

gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "annual-audit-nov" \
    --add-maintenance-exclusion-start-time "2024-11-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-11-30T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
```

## Complete Regulated Environment Template

Here's the full configuration for maximum compliance control:

```bash
#!/bin/bash
# Complete regulated environment setup

CLUSTERS=("cluster-prod-1" "cluster-prod-2" "cluster-prod-3")
ZONES=("us-central1-a" "us-central1-b" "us-central1-c")

for i in "${!CLUSTERS[@]}"; do
    CLUSTER=${CLUSTERS[i]}
    ZONE=${ZONES[i]}
    HOUR=$((2 + i))  # Staggered windows: 2AM, 3AM, 4AM UTC
    
    echo "Configuring $CLUSTER in $ZONE..."
    
    # Extended channel + weekend windows + disruption control + persistent exclusions
    gcloud container clusters update $CLUSTER \
        --zone $ZONE \
        --release-channel extended \
        --maintenance-window-start "2024-01-06T0${HOUR}:00:00Z" \
        --maintenance-window-end "2024-01-06T0$((HOUR + 4)):00:00Z" \
        --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA" \
        --maintenance-patch-version-disruption-interval=7776000s \
        --add-maintenance-exclusion-name "sox-compliance-control" \
        --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
        --add-maintenance-exclusion-until-end-of-support
    
    echo "$CLUSTER configured for regulated environment"
done
```

## What This Configuration Provides

✅ **Auto-upgrades ONLY on weekend mornings (Saturday 2-6 AM UTC)**  
✅ **Security patches auto-applied** (critical for SOX compliance)  
✅ **No minor version or node upgrades** without manual approval  
✅ **Maximum 90-day patch frequency** (controlled disruption)  
✅ **Extended support** (up to 24 months, cost during extended period only)  
✅ **Persistent exclusions** that track End of Support automatically  
✅ **Easy code freeze and audit exclusions** with 30-day "no upgrades" blocks  

## Manual Upgrade Process (When Ready)

When you want to perform minor version or node upgrades (quarterly/annually):

```bash
# 1. Remove temporary exclusion if active
gcloud container clusters update CLUSTER_NAME --zone ZONE \
    --remove-maintenance-exclusion-name "EXCLUSION_NAME"

# 2. Trigger manual upgrade (bypasses all maintenance controls)
gcloud container clusters upgrade CLUSTER_NAME \
    --zone ZONE \
    --master \
    --cluster-version TARGET_VERSION

# 3. Upgrade node pools
gcloud container node-pools upgrade NODE_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version TARGET_VERSION

# Note: Persistent "sox-compliance-control" exclusion stays active throughout
```

## Monitoring and Compliance

Enable scheduled upgrade notifications for advance warning:
```bash
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --send-scheduled-upgrade-notifications
```

Monitor via Cloud Logging:
```bash
# Query for upgrade events
resource.type="gke_cluster" 
protoPayload.metadata.operationType=~"(UPDATE_CLUSTER|UPGRADE_MASTER)"
```

This configuration provides maximum control while maintaining security patch compliance - ideal for SOX and financial services regulations.