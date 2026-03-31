# GKE Maintenance Configuration for Regulated Environment

For financial services with SOX compliance, I'll recommend a configuration that provides maximum control while maintaining security posture.

## Recommended Configuration

**Channel Strategy:** Extended channel + "no minor or node upgrades" exclusion
- Extended channel provides up to 24 months of support (cost applies only during extended period)
- Control plane receives security patches automatically (critical for compliance)
- Minor version upgrades are NOT automatic on Extended - you control when they happen
- Node upgrades blocked by exclusion until you manually trigger them

## Configuration Commands

### 1. Migrate to Extended Channel & Configure Exclusions

For each cluster:
```bash
# Set Extended channel and persistent exclusion
gcloud container clusters update CLUSTER_NAME \
    --region REGION \
    --release-channel extended \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support \
    --maintenance-patch-version-disruption-interval=7776000s
```

### 2. Weekend Maintenance Windows

```bash
# Saturday 2-6 AM maintenance window (adjust timezone as needed)
gcloud container clusters update CLUSTER_NAME \
    --region REGION \
    --maintenance-window-start "2024-01-06T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### 3. Quarterly Code Freeze Exclusions

For each quarterly freeze (example for Q4):
```bash
# Q4 code freeze: December 15 - January 15 (30-day maximum)
gcloud container clusters update CLUSTER_NAME \
    --region REGION \
    --add-maintenance-exclusion-name "q4-code-freeze" \
    --add-maintenance-exclusion-start "2024-12-15T00:00:00Z" \
    --add-maintenance-exclusion-end "2025-01-15T00:00:00Z" \
    --add-maintenance-exclusion-scope no_upgrades
```

### 4. November Audit Period

```bash
# Annual audit freeze: November 1-30
gcloud container clusters update CLUSTER_NAME \
    --region REGION \
    --add-maintenance-exclusion-name "annual-audit" \
    --add-maintenance-exclusion-start "2024-11-01T00:00:00Z" \
    --add-maintenance-exclusion-end "2024-12-01T00:00:00Z" \
    --add-maintenance-exclusion-scope no_upgrades
```

## What This Configuration Provides

### Automatic Behavior
- ✅ **Control plane security patches**: Applied automatically during Saturday 2-6 AM windows
- ✅ **Patch frequency control**: Maximum once every 90 days (disruption interval)
- ❌ **Minor version upgrades**: Blocked - you control when these happen
- ❌ **Node pool upgrades**: Blocked - you control when these happen

### Manual Control Points
- **Minor version upgrades**: You initiate when ready after testing
- **Node pool upgrades**: You initiate during planned maintenance windows
- **Emergency patches**: Can be applied immediately (bypasses all controls)

### Compliance Benefits
- **Audit trail**: All changes logged in Cloud Audit Logs
- **Change control**: No surprise version changes during business periods
- **Security compliance**: Still receives critical security patches
- **Predictability**: Upgrades only during defined windows

## Upgrade Workflow for Minor Versions

When a new minor version becomes available:

1. **Test in staging** (create test node pool):
```bash
gcloud container node-pools create staging-test \
    --cluster STAGING_CLUSTER \
    --region REGION \
    --cluster-version NEW_MINOR_VERSION \
    --num-nodes 1
```

2. **Validate applications** on new version

3. **Upgrade control plane** during maintenance window:
```bash
gcloud container clusters upgrade CLUSTER_NAME \
    --region REGION \
    --master \
    --cluster-version NEW_MINOR_VERSION
```

4. **Upgrade node pools** (exclusion stays in place to block auto-upgrades):
```bash
gcloud container node-pools upgrade NODE_POOL_NAME \
    --cluster CLUSTER_NAME \
    --region REGION \
    --cluster-version NEW_MINOR_VERSION
```

## Managing Exclusion Limits

**Important constraints:**
- Maximum 3 "no upgrades" exclusions per cluster
- Each exclusion limited to 30 days maximum
- Must have 48+ hours available for maintenance in any 32-day rolling window

**For consecutive freeze periods**, chain exclusions:
```bash
# Chain Q1 freeze after Q4 ends (if needed)
gcloud container clusters update CLUSTER_NAME \
    --region REGION \
    --add-maintenance-exclusion-name "q1-code-freeze" \
    --add-maintenance-exclusion-start "2025-01-16T00:00:00Z" \
    --add-maintenance-exclusion-end "2025-02-15T00:00:00Z" \
    --add-maintenance-exclusion-scope no_upgrades
```

## Monitoring and Notifications

Enable notifications for compliance tracking:
```bash
# Enable scheduled upgrade notifications (72h advance warning)
gcloud container clusters update CLUSTER_NAME \
    --region REGION \
    --enable-scheduled-upgrades
```

Monitor via Cloud Logging:
```
resource.type="gke_cluster"
protoPayload.metadata.operationType=~"(UPDATE_CLUSTER|UPGRADE_MASTER)"
```

## Verification Commands

```bash
# Check current configuration
gcloud container clusters describe CLUSTER_NAME \
    --region REGION \
    --format="yaml(maintenancePolicy,releaseChannel)"

# Check exclusions
gcloud container clusters describe CLUSTER_NAME \
    --region REGION \
    --format="yaml(maintenancePolicy.window.maintenanceExclusions)"

# Check upgrade status
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

This configuration gives you **maximum control** over disruptive changes while ensuring you don't fall behind on critical security patches - ideal for SOX compliance and regulated environments.