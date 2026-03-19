# GKE Maintenance Windows & Exclusions for SOX Compliance

For regulated financial services environments, here's a comprehensive maintenance configuration that respects your compliance requirements while keeping clusters secure.

## Current Setup Summary
- **3 GKE Standard clusters** (please provide cluster names/zones)
- **SOX compliance** requirements
- **Quarterly code freezes** + November audit period
- **Weekend-only auto-upgrades** preferred

## Maintenance Window Configuration

### 1. Weekend Maintenance Windows

Configure each cluster for Saturday night maintenance (low business impact):

```bash
# Apply to each cluster - replace CLUSTER_NAME and ZONE
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-end "2024-01-06T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Verify configuration
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy)"
```

**Window Details:**
- **Start:** Saturday 2:00 AM UTC (adjust for your timezone)
- **Duration:** 4-hour window
- **Frequency:** Every Saturday
- **Business Impact:** Minimal (weekend)

### 2. Maintenance Exclusions for Compliance Periods

#### Quarterly Code Freeze Exclusions (example dates - adjust to your schedule)

```bash
# Q1 Code Freeze (March)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "Q1-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-03-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-04-01T00:00:00Z"

# Q2 Code Freeze (June)  
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "Q2-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-07-01T00:00:00Z"

# Q3 Code Freeze (September)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "Q3-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-09-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-10-01T00:00:00Z"

# Q4 Code Freeze + Annual Audit (November-December)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "Q4-freeze-audit-2024" \
  --add-maintenance-exclusion-start-time "2024-11-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-15T00:00:00Z"
```

#### Additional Compliance Exclusions

```bash
# Year-end freeze (common in financial services)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "year-end-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-12-20T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-01-03T00:00:00Z"

# SOX audit preparation period (if different from Q4)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "sox-audit-prep-2024" \
  --add-maintenance-exclusion-start-time "2024-10-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-11-30T00:00:00Z"
```

### 3. Release Channel Strategy for Compliance

For SOX environments, recommend this progression:

```bash
# Dev/Test cluster - get early visibility
gcloud container clusters update DEV_CLUSTER \
  --zone ZONE \
  --release-channel regular

# Staging cluster - validation environment  
gcloud container clusters update STAGING_CLUSTER \
  --zone ZONE \
  --release-channel regular

# Production cluster - maximum stability
gcloud container clusters update PROD_CLUSTER \
  --zone ZONE \
  --release-channel stable
```

**Channel Benefits for Compliance:**
- **Stable channel**: 8-12 week delay from Regular → better tested
- **Predictable timing**: Plan maintenance around freeze periods
- **Extended support**: Consider Extended channel (24 months) for critical systems

## SOX-Specific Considerations

### 4. Change Management Integration

Create a script to document all maintenance activities:

```bash
#!/bin/bash
# maintenance-log.sh - SOX change documentation

CLUSTER=$1
ZONE=$2
CHANGE_ID=$3

echo "=== GKE Maintenance Log - $(date) ===" >> maintenance-log.txt
echo "Cluster: $CLUSTER" >> maintenance-log.txt
echo "Zone: $ZONE" >> maintenance-log.txt  
echo "Change ID: $CHANGE_ID" >> maintenance-log.txt
echo "Authorized by: [APPROVER_NAME]" >> maintenance-log.txt

# Capture before state
gcloud container clusters describe $CLUSTER --zone $ZONE \
  --format="value(currentMasterVersion)" >> maintenance-log.txt

echo "--- Maintenance window status ---" >> maintenance-log.txt
gcloud container clusters describe $CLUSTER --zone $ZONE \
  --format="yaml(maintenancePolicy)" >> maintenance-log.txt
```

### 5. Monitoring & Alerting for Compliance

```bash
# Set up alerting for unexpected maintenance
gcloud alpha monitoring policies create --policy-from-file=- <<EOF
{
  "displayName": "GKE Unexpected Maintenance - SOX Alert",
  "conditions": [{
    "displayName": "GKE maintenance outside window",
    "conditionThreshold": {
      "filter": "resource.type=\"gke_cluster\"",
      "comparison": "COMPARISON_EQUAL",
      "thresholdValue": 1
    }
  }],
  "notificationChannels": ["NOTIFICATION_CHANNEL_ID"],
  "alertStrategy": {
    "autoClose": "1800s"
  }
}
EOF
```

## Emergency Override Process

For security patches that can't wait for maintenance windows:

```bash
# Manual upgrade with change control documentation
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION \
  --quiet  # Bypasses maintenance window

# Document in audit trail
echo "Emergency security patch - Change ID: CHG-XXXX - $(date)" >> emergency-maintenance.log
```

## Verification Commands

```bash
# Check all maintenance policies across clusters
for cluster in CLUSTER1 CLUSTER2 CLUSTER3; do
  echo "=== $cluster ==="
  gcloud container clusters describe $cluster \
    --zone ZONE \
    --format="yaml(maintenancePolicy)"
  echo ""
done

# List all active exclusions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(maintenancePolicy.window.maintenanceExclusions[].exclusionName,maintenancePolicy.window.maintenanceExclusions[].startTime,maintenancePolicy.window.maintenanceExclusions[].endTime)"
```

## Annual Maintenance Planning

Create a yearly schedule aligned with your compliance calendar:

| Period | Activity | Clusters Affected |
|--------|----------|-------------------|
| **Jan-Feb** | Planned upgrades post-freeze | All |
| **March** | Q1 freeze - no changes | Production |
| **April-May** | Upgrades, testing | All |
| **June** | Q2 freeze | Production |
| **July-August** | Major version planning | All |
| **September** | Q3 freeze | Production |
| **October** | Pre-audit upgrades complete | All |
| **November** | SOX audit - no changes | All |
| **December** | Year-end freeze | All |

**Next Steps:**
1. Provide your actual cluster names and zones
2. Confirm your quarterly freeze dates
3. Adjust timezone for maintenance windows
4. Set up change management integration
5. Test emergency override procedures

This configuration ensures GKE auto-upgrades respect your SOX compliance requirements while maintaining security patch currency.