For GKE Standard clusters on the Regular channel, **GKE handles upgrades automatically**, and this is actually the **recommended approach** for production environments. Here's what you need to know:

## How GKE Auto-Upgrades Work

**Control Plane:**
- Automatically upgraded by Google within the Regular channel's maintenance window
- You receive advance notifications before upgrades
- Upgrades happen during your configured maintenance window

**Node Pools:**
- Auto-upgrade is enabled by default on new clusters
- Nodes are upgraded after the control plane upgrade completes
- Rolling upgrade ensures minimal disruption

## Recommended Configuration

```bash
# Verify auto-upgrade is enabled (should be by default)
gcloud container clusters describe CLUSTER_NAME \
  --zone=ZONE \
  --format="value(nodeConfig.upgradeSettings.maxSurge,nodeConfig.upgradeSettings.maxUnavailable)"

# Set maintenance window for predictable upgrade timing
gcloud container clusters update CLUSTER_NAME \
  --zone=ZONE \
  --maintenance-window-start="2024-01-15T02:00:00Z" \
  --maintenance-window-end="2024-01-15T06:00:00Z" \
  --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SU"
```

## Best Practices for Production

1. **Configure Maintenance Windows:**
   ```bash
   # Set maintenance windows during low-traffic periods
   gcloud container clusters update CLUSTER_NAME \
     --maintenance-window-start="YYYY-MM-DDTHH:MM:SSZ" \
     --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SU"
   ```

2. **Configure Node Pool Upgrade Settings:**
   ```bash
   # Control upgrade speed and disruption
   gcloud container node-pools update NODEPOOL_NAME \
     --cluster=CLUSTER_NAME \
     --zone=ZONE \
     --max-surge=1 \
     --max-unavailable=0
   ```

3. **Set Up Monitoring:**
   ```bash
   # Enable cluster notifications
   gcloud container clusters update CLUSTER_NAME \
     --zone=ZONE \
     --enable-notification-config \
     --notification-config=pubsub=TOPIC_NAME
   ```

## When to Consider Manual Upgrades

- **Highly sensitive workloads** requiring extensive testing
- **Regulatory requirements** for change control
- **Complex applications** needing coordination with app deployments

For manual control:
```bash
# Disable auto-upgrade if needed
gcloud container node-pools update NODEPOOL_NAME \
  --cluster=CLUSTER_NAME \
  --zone=ZONE \
  --no-enable-autoupgrade
```

## Monitoring Upgrade Status

```bash
# Check cluster status
gcloud container clusters describe CLUSTER_NAME --zone=ZONE \
  --format="value(status,currentMasterVersion,currentNodeVersion)"

# View upgrade history
gcloud container operations list \
  --filter="operationType:upgradeCluster"
```

**Recommendation:** Stick with auto-upgrades for production, but ensure you have proper maintenance windows, monitoring, and testing procedures in place. This gives you the security benefits of timely updates while maintaining production stability.