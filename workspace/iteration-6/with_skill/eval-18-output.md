# GKE Maintenance Configuration for SOX Compliance

I'll help you configure maintenance windows and exclusions for your regulated environment. This setup will ensure auto-upgrades only occur on weekends and respect your quarterly freezes and audit periods.

## Configuration Overview

For SOX compliance, I recommend:
- **Release Channel**: Regular or Stable (avoid Rapid for production)
- **Maintenance Windows**: Weekend-only auto-upgrades
- **Exclusion Strategy**: "No minor or node upgrades" for code freezes (allows security patches on control plane)
- **Documentation**: Audit trail of all maintenance activities

## Maintenance Windows Configuration

Configure recurring weekend maintenance windows for each cluster:

```bash
# Cluster 1 - Saturday 2AM-6AM UTC
gcloud container clusters update CLUSTER_1_NAME \
  --zone ZONE_1 \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-end "2024-01-06T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Cluster 2 - Saturday 6AM-10AM UTC (staggered)
gcloud container clusters update CLUSTER_2_NAME \
  --zone ZONE_2 \
  --maintenance-window-start "2024-01-06T06:00:00Z" \
  --maintenance-window-end "2024-01-06T10:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Cluster 3 - Sunday 2AM-6AM UTC (separate day for prod)
gcloud container clusters update CLUSTER_3_NAME \
  --zone ZONE_3 \
  --maintenance-window-start "2024-01-07T02:00:00Z" \
  --maintenance-window-end "2024-01-07T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```

## Quarterly Code Freeze Exclusions

Use **"No minor or node upgrades"** exclusions - this allows critical security patches on the control plane while blocking disruptive changes:

### Q1 2024 Code Freeze (Example)
```bash
# Apply to all clusters
for CLUSTER in CLUSTER_1_NAME CLUSTER_2_NAME CLUSTER_3_NAME; do
  gcloud container clusters update $CLUSTER \
    --zone ZONE \
    --add-maintenance-exclusion-name "Q1-2024-code-freeze" \
    --add-maintenance-exclusion-start-time "2024-03-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-04-05T23:59:59Z" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades
done
```

### Annual November Audit Exclusion
For your audit period, use **"No upgrades"** to block ALL changes:

```bash
# November audit - complete freeze
for CLUSTER in CLUSTER_1_NAME CLUSTER_2_NAME CLUSTER_3_NAME; do
  gcloud container clusters update $CLUSTER \
    --zone ZONE \
    --add-maintenance-exclusion-name "SOX-audit-2024" \
    --add-maintenance-exclusion-start-time "2024-11-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-11-30T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
done
```

## Maintenance Exclusion Types for Compliance

| Exclusion Type | What It Blocks | Duration | SOX Use Case |
|---------------|---------------|----------|--------------|
| **"No upgrades"** | ALL upgrades (patches, minor, nodes) | 30 days max | Complete audit freezes, critical business periods |
| **"No minor or node upgrades"** | Minor versions + node pool upgrades | Up to version EoS | Quarterly code freezes (still gets CP security patches) |
| **"No minor upgrades"** | Minor version upgrades only | Up to version EoS | Conservative approach (allows node maintenance) |

**Recommendation for SOX**: Use "no minor or node upgrades" for code freezes - this maintains security posture while preventing disruptive changes.

## Annual Maintenance Calendar Template

```bash
# Q1 Code Freeze (March 15 - April 5)
EXCLUSION_NAME="Q1-2024-code-freeze"
START_TIME="2024-03-15T00:00:00Z"
END_TIME="2024-04-05T23:59:59Z"
SCOPE="no_minor_or_node_upgrades"

# Q2 Code Freeze (June 15 - July 5)  
EXCLUSION_NAME="Q2-2024-code-freeze"
START_TIME="2024-06-15T00:00:00Z"
END_TIME="2024-07-05T23:59:59Z"
SCOPE="no_minor_or_node_upgrades"

# Q3 Code Freeze (September 15 - October 5)
EXCLUSION_NAME="Q3-2024-code-freeze"
START_TIME="2024-09-15T00:00:00Z"
END_TIME="2024-10-05T23:59:59Z"
SCOPE="no_minor_or_node_upgrades"

# SOX Audit (November 1-30)
EXCLUSION_NAME="SOX-audit-2024"
START_TIME="2024-11-01T00:00:00Z"
END_TIME="2024-11-30T23:59:59Z"
SCOPE="no_upgrades"

# Q4 Code Freeze (December 15 - January 5)
EXCLUSION_NAME="Q4-2024-code-freeze"
START_TIME="2024-12-15T00:00:00Z"
END_TIME="2025-01-05T23:59:59Z"
SCOPE="no_minor_or_node_upgrades"
```

## SOX Compliance Monitoring

Set up monitoring and alerting for maintenance activities:

```bash
# Enable audit logging for cluster changes
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --enable-cloud-logging \
  --logging=SYSTEM,WORKLOAD,API_SERVER

# Set up scheduled upgrade notifications (72h advance notice)
# Configure in Cloud Logging to capture upgrade events
```

## Verification Commands

```bash
# Check current maintenance windows
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy)"

# List active maintenance exclusions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy.window.maintenanceExclusions)"

# Check auto-upgrade status and next target
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name,currentMasterVersion,nodePools[].version)"
```

## Release Channel Recommendation

For SOX compliance, consider:

- **Regular Channel**: Good balance of stability and security patches (recommended)
- **Stable Channel**: Maximum stability, longer validation period
- **Extended Channel**: If you need >14 months support for slow upgrade cycles (extra cost)

```bash
# Set to Regular channel (if not already configured)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular
```

## Documentation for Auditors

Create an audit trail document including:

1. **Maintenance Window Schedule**: Weekend-only upgrades
2. **Exclusion Calendar**: All planned freeze periods
3. **Change Log**: Record of all maintenance exclusions applied/removed
4. **Version History**: Track of cluster versions over time
5. **Emergency Override Process**: Documented procedure for urgent security patches during freezes

## Emergency Security Patch Process

During "no upgrades" exclusions, you can still apply emergency patches:

```bash
# Remove exclusion temporarily for urgent security patch
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "EXCLUSION_NAME"

# Apply urgent patch
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version SECURITY_PATCH_VERSION

# Re-apply exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "EXCLUSION_NAME" \
  --add-maintenance-exclusion-start-time "START_TIME" \
  --add-maintenance-exclusion-end-time "END_TIME" \
  --add-maintenance-exclusion-scope SCOPE
```

This configuration ensures your GKE clusters receive security updates while respecting SOX compliance requirements for change control during sensitive periods.