# GKE Maintenance Configuration for Financial Services Environment

Given your regulated environment with SOX compliance requirements, I'll configure a conservative maintenance strategy that provides maximum control while maintaining security posture.

## Recommended Configuration: Extended Channel + Controlled Patch Schedule

For financial services with quarterly freezes and annual audits, use this approach:

```bash
# Configure each cluster with Extended channel + persistent exclusions
for CLUSTER in cluster-1 cluster-2 cluster-3; do
  gcloud container clusters update $CLUSTER \
    --zone YOUR_ZONE \
    --release-channel extended \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support \
    --maintenance-patch-version-disruption-interval=7776000s \
    --maintenance-window-start "2026-01-04T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
done
```

**This configuration provides:**
- **Extended channel**: 24 months support, no auto minor version upgrades (you control when)
- **Persistent "no minor or node" exclusion**: Blocks disruptive changes, allows security patches
- **Patch disruption interval**: Limits control plane patches to once every 90 days maximum
- **Weekend maintenance window**: Saturday 2-6 AM for predictable timing

## Quarterly Code Freeze Management

For your quarterly freezes, layer on temporary "no upgrades" exclusions:

```bash
# Q4 2025 Code Freeze (example dates)
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "Q4-2025-freeze" \
  --add-maintenance-exclusion-start-time "2025-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-12-15T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# Q1 2026 Code Freeze 
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "Q1-2026-freeze" \
  --add-maintenance-exclusion-start-time "2026-02-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2026-03-15T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Annual Audit Period (November)

```bash
# Annual audit freeze - November 2025
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "audit-2025" \
  --add-maintenance-exclusion-start-time "2025-11-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-11-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Configuration Explanation

### Extended Channel Benefits for Compliance
- **Manual control over minor versions**: GKE doesn't auto-upgrade minor versions (except at end of extended support)
- **24-month support**: Reduces forced upgrade frequency
- **Security patches still apply**: Control plane gets patches automatically within your maintenance window
- **Cost**: Extra charges only apply during extended support period (months 15-24)

### Exclusion Strategy
- **Persistent "no minor or node" exclusion**: Your baseline - prevents disruptive upgrades while allowing security patches
- **Temporary "no upgrades" exclusions**: Additional layer during code freezes - blocks even patches for up to 30 days

### Patch Control
- **90-day disruption interval**: Limits control plane patches to quarterly maximum
- **Saturday 2-6 AM window**: Predictable timing, low business impact
- **4-hour duration**: Sufficient for patch application and validation

## Monitoring and Compliance

Set up these monitoring alerts for audit trails:

```bash
# Enable cluster notifications
gcloud pubsub topics create gke-cluster-notifications
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --enable-network-policy \
  --notification-config=pubsub=projects/PROJECT_ID/topics/gke-cluster-notifications
```

**Cloud Logging queries for audit reports:**
```
# All maintenance events
resource.type="gke_cluster"
protoPayload.methodName=~"google.container.v1.ClusterManager.(Update|Upgrade)"

# Version changes
resource.type="gke_cluster"
protoPayload.metadata.operationType=~"(UPDATE_CLUSTER|UPGRADE_MASTER)"
```

## Manual Minor Version Upgrade Process

When you need to upgrade minor versions (quarterly or annually):

1. **Remove temporary exclusions first:**
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --remove-maintenance-exclusion-name "Q4-2025-freeze"
```

2. **Upgrade control plane:**
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone YOUR_ZONE \
  --master \
  --cluster-version 1.33.x-gke.xxxx
```

3. **Upgrade node pools (if needed):**
```bash
gcloud container node-pools upgrade POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone YOUR_ZONE \
  --cluster-version 1.33.x-gke.xxxx
```

The persistent "no minor or node" exclusion stays in place - it only blocks **auto**-upgrades, not manual ones.

## Validation Commands

```bash
# Verify configuration
gcloud container clusters describe CLUSTER_NAME \
  --zone YOUR_ZONE \
  --format="table(releaseChannel.channel, maintenancePolicy.window, maintenancePolicy.exclusions[].name)"

# Check auto-upgrade status
gcloud container clusters get-upgrade-info CLUSTER_NAME --region YOUR_REGION

# Monitor patch compliance
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion
```

## Key Benefits for SOX Compliance

✅ **Change control**: All minor version upgrades require manual approval and execution
✅ **Predictable timing**: Maintenance only occurs in defined Saturday windows  
✅ **Audit trail**: All upgrade events logged to Cloud Logging with timestamps
✅ **Security posture**: Control plane receives security patches automatically
✅ **Freeze periods**: Complete upgrade blocks during code freezes and audits
✅ **Extended support**: 24-month lifecycle reduces upgrade frequency

This configuration balances regulatory requirements with operational security - you maintain tight control over disruptive changes while ensuring clusters receive critical security updates.