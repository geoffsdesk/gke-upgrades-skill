# GKE Maintenance Configuration for SOX-Compliant Environment

Based on your regulatory requirements, I'll configure maintenance windows and exclusions that provide predictable upgrade timing while maintaining compliance with quarterly freezes and annual audit requirements.

## Configuration Strategy

For financial services with SOX compliance:
- **Release channel**: Regular (recommended for production) - provides stability with full SLA
- **Weekend-only upgrades**: Saturday maintenance windows
- **Quarterly code freeze protection**: 30-day "no upgrades" exclusions
- **November audit protection**: Extended "no upgrades" exclusion
- **Conservative disruption intervals**: Extended time between upgrades

## 1. Release Channel Migration (if needed)

First, verify and set appropriate release channels:

```bash
# Check current channels
for cluster in cluster-prod-1 cluster-prod-2 cluster-prod-3; do
  echo "=== $cluster ==="
  gcloud container clusters describe $cluster \
    --zone us-central1-a \
    --format="value(name,releaseChannel.channel)"
done

# Migrate to Regular channel (if currently on "No channel" or Rapid)
gcloud container clusters update cluster-prod-1 \
  --zone us-central1-a \
  --release-channel regular

gcloud container clusters update cluster-prod-2 \
  --zone us-central1-a \
  --release-channel regular

gcloud container clusters update cluster-prod-3 \
  --zone us-central1-a \
  --release-channel regular
```

## 2. Weekend Maintenance Windows

Configure Saturday 2 AM - 6 AM maintenance windows (4-hour window provides buffer for large upgrades):

```bash
# Cluster 1: Saturday 2:00-6:00 AM EST
gcloud container clusters update cluster-prod-1 \
  --zone us-central1-a \
  --maintenance-window-start "2024-01-06T07:00:00Z" \
  --maintenance-window-end "2024-01-06T11:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Cluster 2: Saturday 3:00-7:00 AM EST (staggered 1 hour)
gcloud container clusters update cluster-prod-2 \
  --zone us-central1-a \
  --maintenance-window-start "2024-01-06T08:00:00Z" \
  --maintenance-window-end "2024-01-06T12:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Cluster 3: Saturday 4:00-8:00 AM EST (staggered 2 hours)
gcloud container clusters update cluster-prod-3 \
  --zone us-central1-a \
  --maintenance-window-start "2024-01-06T09:00:00Z" \
  --maintenance-window-end "2024-01-06T13:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## 3. Conservative Disruption Intervals

Extend time between upgrades for stability:

```bash
# Apply to all clusters - 14 days between patches, 60 days between minors
for cluster in cluster-prod-1 cluster-prod-2 cluster-prod-3; do
  gcloud container clusters update $cluster \
    --zone us-central1-a \
    --maintenance-patch-version-disruption-interval=14d \
    --maintenance-minor-version-disruption-interval=60d
done
```

## 4. Quarterly Code Freeze Exclusions

Use "no upgrades" exclusions for quarterly freezes (blocks ALL upgrades including patches):

### Q1 2024 Code Freeze (March 15 - April 15)
```bash
for cluster in cluster-prod-1 cluster-prod-2 cluster-prod-3; do
  gcloud container clusters update $cluster \
    --zone us-central1-a \
    --add-maintenance-exclusion-name "q1-2024-freeze" \
    --add-maintenance-exclusion-start-time "2024-03-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-04-15T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
done
```

### Q2 2024 Code Freeze (June 15 - July 15)
```bash
for cluster in cluster-prod-1 cluster-prod-2 cluster-prod-3; do
  gcloud container clusters update $cluster \
    --zone us-central1-a \
    --add-maintenance-exclusion-name "q2-2024-freeze" \
    --add-maintenance-exclusion-start-time "2024-06-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-07-15T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
done
```

### Q3 2024 Code Freeze (September 15 - October 15)
```bash
for cluster in cluster-prod-1 cluster-prod-2 cluster-prod-3; do
  gcloud container clusters update $cluster \
    --zone us-central1-a \
    --add-maintenance-exclusion-name "q3-2024-freeze" \
    --add-maintenance-exclusion-start-time "2024-09-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-10-15T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
done
```

### Q4 2024 Code Freeze + November Audit (October 15 - December 15)
```bash
for cluster in cluster-prod-1 cluster-prod-2 cluster-prod-3; do
  gcloud container clusters update $cluster \
    --zone us-central1-a \
    --add-maintenance-exclusion-name "q4-2024-freeze-audit" \
    --add-maintenance-exclusion-start-time "2024-10-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-12-15T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
done
```

## 5. Emergency Override Capability

For critical security patches during freezes, you can manually trigger upgrades (bypasses exclusions):

```bash
# Emergency control plane patch (bypasses maintenance exclusions)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_PATCH_VERSION

# Emergency node pool patch (bypasses maintenance exclusions)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_PATCH_VERSION
```

## 6. Monitoring and Alerting

Set up Cloud Logging alerts for upgrade events:

```bash
# Create alert policy for upgrade start notifications
cat > upgrade-alert.yaml << EOF
displayName: "GKE Upgrade Started"
conditions:
  - displayName: "GKE cluster upgrade initiated"
    conditionThreshold:
      filter: 'resource.type="gke_cluster" AND protoPayload.methodName="google.container.v1.ClusterManager.UpdateCluster"'
      comparison: COMPARISON_EQUAL
      thresholdValue: 1
EOF
```

## 7. Verification Commands

Verify your configuration:

```bash
# Check maintenance windows
for cluster in cluster-prod-1 cluster-prod-2 cluster-prod-3; do
  echo "=== $cluster Maintenance Window ==="
  gcloud container clusters describe $cluster \
    --zone us-central1-a \
    --format="value(maintenancePolicy.window)"
done

# Check maintenance exclusions
for cluster in cluster-prod-1 cluster-prod-2 cluster-prod-3; do
  echo "=== $cluster Exclusions ==="
  gcloud container clusters describe $cluster \
    --zone us-central1-a \
    --format="table(maintenancePolicy.exclusions[].name,maintenancePolicy.exclusions[].startTime,maintenancePolicy.exclusions[].endTime,maintenancePolicy.exclusions[].exclusionOptions.scope)"
done

# Check auto-upgrade targets and EoS dates
for cluster in cluster-prod-1 cluster-prod-2 cluster-prod-3; do
  echo "=== $cluster Upgrade Info ==="
  gcloud container clusters get-upgrade-info $cluster --zone us-central1-a
done
```

## SOX Compliance Considerations

✅ **Auditability**: All maintenance windows and exclusions are logged in Cloud Audit Logs  
✅ **Predictability**: Upgrades only occur during defined Saturday maintenance windows  
✅ **Change Control**: 30-day "no upgrades" exclusions prevent any changes during code freezes  
✅ **Separation of Duties**: Manual override capability preserved for emergency security patches  
✅ **Documentation**: All configurations are version-controlled and traceable  

## Annual Maintenance Calendar Template

Create a recurring process to set next year's exclusions in December:

```bash
#!/bin/bash
# run-december.sh - Set next year's quarterly exclusions
YEAR=2025

# Q1 freeze
for cluster in cluster-prod-1 cluster-prod-2 cluster-prod-3; do
  gcloud container clusters update $cluster \
    --zone us-central1-a \
    --add-maintenance-exclusion-name "q1-${YEAR}-freeze" \
    --add-maintenance-exclusion-start-time "${YEAR}-03-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "${YEAR}-04-15T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
done
# ... repeat for Q2, Q3, Q4
```

This configuration ensures your GKE clusters receive security updates through auto-upgrades while respecting SOX compliance requirements for change control during critical business periods.