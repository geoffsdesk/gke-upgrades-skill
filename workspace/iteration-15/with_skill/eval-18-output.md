# GKE Maintenance Configuration for SOX Compliance

I'll help you set up a comprehensive maintenance strategy that balances automated security patching with regulatory compliance requirements.

## Recommended Configuration Strategy

### Maintenance Windows (Weekend Auto-upgrades)
Configure recurring weekend maintenance windows for all clusters:

```bash
# Apply to all 3 clusters
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-end "2024-01-07T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Window details:**
- **Start**: Saturday 2:00 AM UTC (adjust timezone as needed)
- **Duration**: 28 hours (Saturday 2 AM → Sunday 6 AM)
- **Recurrence**: Every Saturday
- **Rationale**: Long window accommodates multi-hour upgrades on large clusters

### Maintenance Exclusions for Compliance Periods

#### 1. Quarterly Code Freezes (Recommended: "No minor or node upgrades")

```bash
# Q1 Code Freeze Example (adjust dates for your quarters)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "Q1-code-freeze" \
  --add-maintenance-exclusion-start-time "2024-03-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-03-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Q2, Q3, Q4 - repeat with appropriate dates
```

**Why "no minor or node upgrades"?**
- Allows critical security patches on control plane (SOX compliance requirement)
- Blocks disruptive changes (node pool upgrades, Kubernetes minor versions)
- Available until version End of Support (no artificial 30-day limit)

#### 2. Annual November Audit ("No upgrades" - strictest control)

```bash
# November audit period - complete freeze
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "november-sox-audit" \
  --add-maintenance-exclusion-start-time "2024-11-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-11-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**Important**: "No upgrades" exclusions have a 30-day maximum and can only be used 3 times per cluster annually. Plan carefully.

### Complete Configuration Script

```bash
#!/bin/bash
# Configure all 3 clusters for SOX compliance

CLUSTERS=("prod-cluster" "staging-cluster" "dev-cluster")
ZONES=("us-central1-a" "us-central1-b" "us-central1-c")  # Adjust as needed

for i in "${!CLUSTERS[@]}"; do
  CLUSTER="${CLUSTERS[$i]}"
  ZONE="${ZONES[$i]}"
  
  echo "Configuring $CLUSTER in $ZONE..."
  
  # Weekend maintenance window
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --maintenance-window-start "2024-01-06T02:00:00Z" \
    --maintenance-window-end "2024-01-07T06:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
  
  # Q1 Code Freeze (adjust dates for your quarters)
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --add-maintenance-exclusion-name "Q1-code-freeze" \
    --add-maintenance-exclusion-start-time "2024-03-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-03-31T23:59:59Z" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades
  
  # November SOX Audit
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --add-maintenance-exclusion-name "november-sox-audit" \
    --add-maintenance-exclusion-start-time "2024-11-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-11-30T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
  
  echo "$CLUSTER configured successfully"
done
```

## SOX Compliance Considerations

### Security Patch Management
- **Control plane patches**: Always allowed during code freezes (critical for security compliance)
- **Node patches**: Blocked during code freezes but allowed during maintenance windows
- **Emergency patches**: Manual upgrades bypass exclusions if critical vulnerabilities emerge

### Audit Trail Requirements
```bash
# Enable audit logging for cluster changes
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --enable-cloud-logging \
  --logging=SYSTEM,WORKLOAD,API_SERVER

# Query maintenance events
gcloud logging read 'resource.type="gke_cluster" 
  protoPayload.metadata.operationType=~"(UPDATE_CLUSTER|UPGRADE_MASTER|UPGRADE_NODES)"' \
  --limit=50 \
  --format=json
```

### Change Management Integration
Set up notifications for scheduled upgrades:

```bash
# Create Pub/Sub topic for upgrade notifications
gcloud pubsub topics create gke-upgrade-notifications

# Subscribe to cluster notifications
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --notification-config=pubsub=projects/PROJECT_ID/topics/gke-upgrade-notifications
```

## Annual Maintenance Calendar Template

| Quarter | Code Freeze Period | Exclusion Type | Security Patches |
|---------|-------------------|----------------|------------------|
| Q1 | Mar 15-31 | no_minor_or_node_upgrades | ✓ Allowed |
| Q2 | Jun 15-30 | no_minor_or_node_upgrades | ✓ Allowed |
| Q3 | Sep 15-30 | no_minor_or_node_upgrades | ✓ Allowed |
| Q4 | Nov 1-30 (Audit) | no_upgrades | ✗ Blocked |

## Monitoring and Alerting

```bash
# Check current exclusions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(maintenancePolicy.window, maintenancePolicy.resourceVersion)"

# Monitor for approaching EoS versions
gcloud container clusters get-upgrade-info CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, autoUpgradeStatus, endOfStandardSupportTimestamp)"
```

## Emergency Override Procedures

For critical security patches during exclusions:

```bash
# Remove exclusion temporarily
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "EXCLUSION_NAME"

# Apply emergency patch
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION

# Restore exclusion
# (Re-run original exclusion command)
```

## Release Channel Recommendation

For SOX environments, consider **Stable** channel:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel stable
```

**Benefits**:
- Maximum stability testing before upgrades
- Predictable upgrade timing
- Full SLA coverage
- Compatible with maintenance exclusions

This configuration ensures your clusters receive security updates on weekends while respecting code freezes and audit periods, maintaining both security and compliance requirements.