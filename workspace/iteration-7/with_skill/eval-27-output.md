# GKE Upgrade Control Strategy for Financial Services

Based on your need for maximum control with security compliance, here's the recommended configuration:

## Primary Strategy: Extended Channel + Maintenance Exclusions

```bash
# Migrate to Extended release channel (provides up to 24 months support)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended

# Configure strict maintenance windows (example: Saturday 2-6 AM EST)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T07:00:00Z" \
  --maintenance-window-end "2024-01-06T11:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Key Control Mechanism: "No minor or node upgrades" Exclusions

This is your primary control tool - it allows critical security patches on the control plane while blocking all disruptive changes:

```bash
# Block minor version + node upgrades, allow control plane patches
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "quarterly-freeze-Q1" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-03-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**Critical advantage:** This exclusion type is ONLY available on release channels, not legacy "No channel" clusters. It gives you the granular control you need.

## Upgrade Control Timeline

| Activity | Timing | What happens |
|----------|--------|-------------|
| **Security patches** | Automatic (respects windows) | Control plane gets patches immediately, nodes unchanged |
| **Minor version planning** | Quarterly | Plan and test minor upgrades during business review cycles |
| **Minor execution** | Controlled windows | Remove exclusion temporarily, execute upgrade, restore exclusion |
| **Emergency patches** | Override windows | Manual upgrade can bypass windows if critical CVE |

## Multi-Environment Strategy

```bash
# Development: Regular channel (faster patches)
gcloud container clusters update dev-cluster \
  --zone ZONE \
  --release-channel regular

# Staging: Regular channel (same as dev for testing)
gcloud container clusters update staging-cluster \
  --zone ZONE \
  --release-channel regular

# Production: Extended channel (maximum control + long-term support)
gcloud container clusters update prod-cluster \
  --zone ZONE \
  --release-channel extended
```

## Quarterly Upgrade Workflow

### Phase 1: Planning (Week 1-2 of quarter)
```bash
# Check available versions in Extended channel
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels.EXTENDED)"

# Review deprecation insights for breaking changes
# Access via GKE console → Cluster → Observability → Deprecation insights
```

### Phase 2: Testing (Week 3-4)
```bash
# Test in dev/staging first
gcloud container clusters upgrade dev-cluster \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION
```

### Phase 3: Production (Scheduled change window)
```bash
# Remove exclusion temporarily
gcloud container clusters update prod-cluster \
  --zone ZONE \
  --remove-maintenance-exclusion "quarterly-freeze-Q1"

# Execute upgrade during approved window
# (Auto-upgrade will trigger within maintenance window)

# Restore exclusion after upgrade completes
gcloud container clusters update prod-cluster \
  --zone ZONE \
  --add-maintenance-exclusion-name "quarterly-freeze-Q2" \
  --add-maintenance-exclusion-start-time "2024-04-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

## Emergency Security Response

For critical CVEs requiring immediate patching:

```bash
# Manual upgrade bypasses maintenance windows
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version PATCH_VERSION

# Node pools (if needed)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version PATCH_VERSION
```

## Why NOT "No Channel"

Many financial services teams assume "No channel" provides maximum control, but it actually provides LESS control:

| Feature | Extended Channel | No Channel |
|---------|-----------------|------------|
| "No minor or node upgrades" exclusion | ✅ Yes | ❌ No |
| Extended support (24 months) | ✅ Yes | ❌ No |
| Granular patch vs minor control | ✅ Yes | ❌ Limited |
| EoS flexibility | ✅ Extended timeline | ❌ Forced upgrades |

**Bottom line:** Extended channel + maintenance exclusions gives you MORE control than "No channel."

## Compliance & Audit Trail

```bash
# Track upgrade history
gcloud logging read "resource.type=gke_cluster AND protoPayload.methodName=google.container.v1.ClusterManager.UpdateCluster" \
  --limit=50 \
  --format="table(timestamp, protoPayload.resourceName, protoPayload.request.update.desiredMasterVersion)"

# Monitor security patch status
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion, status)"
```

## Recommended Configuration Summary

```bash
# Production clusters
--release-channel extended
--maintenance-window (Saturday 2-6 AM)
--add-maintenance-exclusion-scope no_minor_or_node_upgrades
# Duration: Up to version EoS (can chain exclusions)

# Staging/dev clusters  
--release-channel regular
--maintenance-window (Friday 6-10 PM)
# No exclusions (stay current for testing)
```

This configuration ensures you receive critical security patches automatically while maintaining complete control over disruptive changes through your change management process.