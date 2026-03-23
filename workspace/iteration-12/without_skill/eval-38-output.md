For GKE Standard clusters on the Regular release channel, **GKE handles upgrades automatically**, and this is actually the **recommended approach** for most production environments. Here's what you need to know:

## How GKE Auto-Upgrades Work

### Control Plane Upgrades
- **Fully automatic** - GKE upgrades the control plane during maintenance windows
- **Zero downtime** - Control plane remains available during upgrades
- **Regular channel timing** - Upgrades typically roll out 2-3 months after initial release

### Node Pool Upgrades
- **Automatic by default** - Node pools auto-upgrade to match control plane versions
- **Configurable** - You can disable auto-upgrade for node pools if needed
- **Surge upgrades** - Uses blue-green deployment strategy for minimal disruption

## Recommended Production Setup

```bash
# Verify your current auto-upgrade settings
gcloud container clusters describe CLUSTER_NAME \
    --zone=ZONE \
    --format="value(nodeConfig.autoUpgrade,maintenancePolicy)"

# Configure maintenance windows (recommended)
gcloud container clusters update CLUSTER_NAME \
    --zone=ZONE \
    --maintenance-window-start "2024-01-01T02:00:00Z" \
    --maintenance-window-end "2024-01-01T06:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```

## Best Practices for Production

### 1. **Keep Auto-Upgrades Enabled** (Recommended)
```bash
# Ensure auto-upgrade is enabled for node pools
gcloud container node-pools update POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=ZONE \
    --enable-autoupgrade
```

### 2. **Set Maintenance Windows**
- Schedule during low-traffic periods
- Allow 4-6 hour windows for safety
- Avoid business-critical hours

### 3. **Configure Surge Settings**
```bash
# Optimize surge settings for faster, safer upgrades
gcloud container node-pools update POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=ZONE \
    --max-surge=2 \
    --max-unavailable=0
```

### 4. **Monitor and Test**
```bash
# Set up notifications for upgrade events
gcloud container clusters update CLUSTER_NAME \
    --zone=ZONE \
    --enable-network-policy \
    --notification-config=pubsub=projects/PROJECT_ID/topics/TOPIC_NAME
```

## When to Consider Manual Upgrades

Manual upgrades might be appropriate if you:
- Need to coordinate upgrades across multiple environments
- Have strict change management processes
- Want to test upgrades in staging first
- Need upgrades during specific time windows

```bash
# Disable auto-upgrade for manual control
gcloud container node-pools update POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=ZONE \
    --no-enable-autoupgrade

# Manual upgrade process
gcloud container clusters upgrade CLUSTER_NAME \
    --zone=ZONE \
    --cluster-version=VERSION
```

## Hybrid Approach (Often Best for Production)

1. **Keep control plane auto-upgrades enabled**
2. **Disable node pool auto-upgrades**
3. **Manually upgrade node pools** after testing

This gives you the security benefits of automatic control plane updates while maintaining control over when workloads are affected.

**For your current setup**: I recommend keeping the default auto-upgrade settings but configuring appropriate maintenance windows. The Regular channel provides a good balance of stability and security for production workloads.