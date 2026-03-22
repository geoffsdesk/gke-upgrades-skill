# GKE Maintenance Configuration for SOX-Compliant Financial Services Environment

## Current Setup Analysis
- **Environment**: Financial services (SOX compliance)
- **Clusters**: 3 GKE Standard clusters
- **Requirements**: 
  - Auto-upgrades only on weekends
  - Quarterly code freezes
  - Annual November audit freeze
  - Regulatory compliance considerations

## Recommended Configuration Strategy

### 1. Maintenance Windows (Weekend-Only Upgrades)

Configure recurring weekend maintenance windows for all clusters:

```bash
# Apply to each cluster
for CLUSTER in cluster-prod cluster-staging cluster-dev; do
  gcloud container clusters update $CLUSTER \
    --zone YOUR_ZONE \
    --maintenance-window-start "2024-01-06T02:00:00Z" \
    --maintenance-window-end "2024-01-06T06:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
done
```

**Rationale**: Saturday 2-6 AM UTC provides a 4-hour window during off-peak hours. Adjust timezone as needed for your operations.

### 2. Channel Strategy for Regulated Environment

**Recommended**: Use **Stable** or **Extended** channel for maximum predictability:

```bash
# For production (maximum stability)
gcloud container clusters update cluster-prod \
  --zone YOUR_ZONE \
  --release-channel stable

# For staging (slightly faster for testing)
gcloud container clusters update cluster-staging \
  --zone YOUR_ZONE \
  --release-channel regular

# For dev (can use Regular or Stable)
gcloud container clusters update cluster-dev \
  --zone YOUR_ZONE \
  --release-channel regular
```

**Extended Channel Consideration**: For ultimate control around EoS enforcement, consider Extended channel for production:
```bash
gcloud container clusters update cluster-prod \
  --zone YOUR_ZONE \
  --release-channel extended
```

### 3. Quarterly Code Freeze Exclusions

Use "no minor or node upgrades" exclusions during code freezes (allows security patches on control plane):

```bash
# Q1 Code Freeze Example (adjust dates for your quarters)
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "Q1-2024-code-freeze" \
  --add-maintenance-exclusion-start-time "2024-03-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-03-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Q2 Code Freeze
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "Q2-2024-code-freeze" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Q3 Code Freeze  
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "Q3-2024-code-freeze" \
  --add-maintenance-exclusion-start-time "2024-09-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-09-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Q4 Code Freeze
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "Q4-2024-code-freeze" \
  --add-maintenance-exclusion-start-time "2024-12-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### 4. Annual November Audit Freeze

Use the stronger "no upgrades" exclusion during audit to block ALL changes:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "SOX-audit-2024" \
  --add-maintenance-exclusion-start-time "2024-11-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-11-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**Note**: "no_upgrades" can only be applied for 30 days maximum, so this covers the full November audit period.

## SOX Compliance Considerations

### 5. Enhanced Upgrade Controls for Financial Services

```bash
# Set conservative disruption intervals to reduce upgrade frequency
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --maintenance-patch-version-disruption-interval 30 \
  --maintenance-minor-version-disruption-interval 90
```

### 6. Accelerated Patch Updates for Security

Financial services may need faster security patch compliance:

```bash
# Enable accelerated patches (for FedRAMP/security requirements)
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --patch-update accelerated
```

### 7. Monitoring and Notifications

Enable scheduled upgrade notifications for advance planning:

```bash
# This will be available March 2026 - opt-in for 72h advance notifications
# Configure Cloud Logging filters to capture GKE upgrade notifications
```

## Complete Configuration Script

```bash
#!/bin/bash

CLUSTERS=("cluster-prod" "cluster-staging" "cluster-dev")
ZONE="us-central1-a"  # Adjust for your zone

echo "Configuring GKE maintenance for SOX-compliant environment..."

for CLUSTER in "${CLUSTERS[@]}"; do
  echo "Configuring $CLUSTER..."
  
  # 1. Set weekend maintenance windows (Saturday 2-6 AM UTC)
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --maintenance-window-start "2024-01-06T02:00:00Z" \
    --maintenance-window-end "2024-01-06T06:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
  
  # 2. Set conservative disruption intervals
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --maintenance-patch-version-disruption-interval 30 \
    --maintenance-minor-version-disruption-interval 90
  
  # 3. Enable accelerated patches for security compliance
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --patch-update accelerated
  
  # 4. Add quarterly code freeze exclusions
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --add-maintenance-exclusion-name "Q1-2024-code-freeze" \
    --add-maintenance-exclusion-start-time "2024-03-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-03-31T23:59:59Z" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades
  
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --add-maintenance-exclusion-name "Q2-2024-code-freeze" \
    --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades
  
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --add-maintenance-exclusion-name "Q3-2024-code-freeze" \
    --add-maintenance-exclusion-start-time "2024-09-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-09-30T23:59:59Z" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades
  
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --add-maintenance-exclusion-name "Q4-2024-code-freeze" \
    --add-maintenance-exclusion-start-time "2024-12-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-12-31T23:59:59Z" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades
  
  # 5. Add November audit freeze (blocks ALL upgrades)
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --add-maintenance-exclusion-name "SOX-audit-2024" \
    --add-maintenance-exclusion-start-time "2024-11-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-11-30T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
  
  echo "$CLUSTER configured successfully"
done

echo "All clusters configured for SOX compliance"
```

## Validation Commands

```bash
# Verify maintenance windows
gcloud container clusters describe CLUSTER_NAME \
  --zone YOUR_ZONE \
  --format="yaml(maintenancePolicy)"

# Check scheduled exclusions
gcloud container clusters describe CLUSTER_NAME \
  --zone YOUR_ZONE \
  --format="yaml(maintenancePolicy.window.maintenanceExclusions)"

# Monitor auto-upgrade status
gcloud container clusters get-upgrade-info CLUSTER_NAME --zone YOUR_ZONE
```

## Key Benefits for Financial Services

1. **Predictable Timing**: Weekend-only upgrades during defined maintenance windows
2. **Security Compliance**: Accelerated patches for faster security updates while blocking disruptive changes during freezes
3. **Audit Trail**: All exclusions are named and logged for compliance documentation
4. **Gradual Control**: Control plane patches allowed during code freezes (for security) while blocking disruptive node/minor upgrades
5. **Complete Freeze**: November audit gets full "no upgrades" protection
6. **Conservative Cadence**: 30/90-day disruption intervals reduce upgrade frequency

This configuration balances SOX compliance requirements with GKE's automated lifecycle management, ensuring you get security patches while maintaining strict change control during critical business periods.