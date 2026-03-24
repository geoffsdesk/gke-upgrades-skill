# GKE Maintenance Configuration for SOX Compliance Environment

## Recommended Configuration Strategy

For SOX compliance with quarterly freezes and annual audit requirements, I recommend the **Extended channel + persistent "no minor or node" exclusion** approach. This gives you maximum control while maintaining security compliance.

## Configuration Commands

### 1. Migrate to Extended Channel (if not already)

```bash
# For each cluster
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

**Why Extended Channel for Financial Services:**
- Up to 24 months version support (extra cost only during extended period)
- Minor versions are NOT auto-upgraded (except at end of extended support)
- Only patches are auto-applied for security compliance
- Maximum flexibility around EoS enforcement

### 2. Configure Weekend Maintenance Windows

```bash
# Saturday 2-6 AM maintenance window (4-hour window)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-end "2024-01-06T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Alternative: Sunday 1-5 AM if Saturday conflicts with batch processing
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-07T01:00:00Z" \
  --maintenance-window-end "2024-01-07T05:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```

### 3. Set Up Persistent Control Plane Patch-Only Mode

```bash
# This allows security patches but blocks minor version + node upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "sox-compliance-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Key Benefits:**
- Security patches automatically applied (SOX requirement)
- Minor version upgrades require manual approval
- Node pool upgrades under your control
- Automatically renews when versions change

### 4. Configure Disruption Intervals for Regulated Environment

```bash
# Limit patches to once every 90 days maximum
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-patch-version-disruption-interval=90d \
  --maintenance-minor-version-disruption-interval=90d
```

### 5. Quarterly Code Freeze Exclusions

For your quarterly freezes, chain "no upgrades" exclusions (30-day limit each):

```bash
# Q1 Code Freeze (example: March 1-31)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "q1-code-freeze" \
  --add-maintenance-exclusion-start-time "2024-03-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-03-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# For longer freezes, chain exclusions with 48-hour gaps
# Q4 Code Freeze Part 1 (Nov 1-30)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "annual-audit-freeze-1" \
  --add-maintenance-exclusion-start-time "2024-11-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-11-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# Q4 Code Freeze Part 2 (Dec 3-31, with 48h gap)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "annual-audit-freeze-2" \
  --add-maintenance-exclusion-start-time "2024-12-03T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Complete SOX-Compliant Configuration Script

```bash
#!/bin/bash

CLUSTERS=("prod-cluster-1" "prod-cluster-2" "prod-cluster-3")
ZONES=("us-central1-a" "us-central1-b" "us-central1-c")

for i in "${!CLUSTERS[@]}"; do
  CLUSTER=${CLUSTERS[$i]}
  ZONE=${ZONES[$i]}
  
  echo "Configuring $CLUSTER in $ZONE for SOX compliance..."
  
  # 1. Extended channel for maximum control
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --release-channel extended
  
  # 2. Weekend maintenance window (Saturday 2-6 AM)
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --maintenance-window-start "2024-01-06T02:00:00Z" \
    --maintenance-window-end "2024-01-06T06:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
  
  # 3. Patch-only auto-upgrades (no minor or node auto-upgrades)
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --add-maintenance-exclusion-name "sox-patch-only-control" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
  
  # 4. 90-day disruption interval
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --maintenance-patch-version-disruption-interval=90d \
    --maintenance-minor-version-disruption-interval=90d
  
  echo "✓ $CLUSTER configured"
done
```

## Operational Workflow

### Quarterly Minor Version Upgrades (Manual Process)

1. **During maintenance windows between quarters:**
   ```bash
   # Remove the persistent exclusion temporarily
   gcloud container clusters update CLUSTER_NAME \
     --zone ZONE \
     --remove-maintenance-exclusion-name "sox-patch-only-control"
   
   # Manual minor version upgrade
   gcloud container clusters upgrade CLUSTER_NAME \
     --zone ZONE \
     --master \
     --cluster-version TARGET_VERSION
   
   # Restore the exclusion
   gcloud container clusters update CLUSTER_NAME \
     --zone ZONE \
     --add-maintenance-exclusion-name "sox-patch-only-control" \
     --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
     --add-maintenance-exclusion-until-end-of-support
   ```

### Emergency Patch Override

For critical security patches during code freezes:
```bash
# Remove freeze exclusion temporarily
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "q1-code-freeze"

# Patch will apply in next maintenance window
# Re-apply freeze exclusion if still needed
```

## Compliance Features Summary

| Requirement | Solution |
|-------------|----------|
| **Auto-upgrades only on weekends** | Saturday 2-6 AM maintenance window |
| **Quarterly code freezes** | "No upgrades" exclusions (30-day max, chained) |
| **Annual audit freeze** | Extended "no upgrades" exclusions |
| **Security patches required** | Extended channel + patch-only exclusion |
| **Change control for minor versions** | Manual minor upgrades only |
| **Minimal disruption frequency** | 90-day disruption interval |
| **Audit trail** | All changes via gcloud (logged in Cloud Audit Logs) |

## Monitoring & Notifications

Enable scheduled upgrade notifications for advance warning:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --send-scheduled-upgrade-notifications
```

Monitor exclusions and maintenance windows:
```bash
# Check current configuration
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy)"
```

This configuration ensures SOX compliance while maintaining security patching and provides full control over when disruptive changes occur.