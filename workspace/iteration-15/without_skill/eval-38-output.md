For GKE Standard clusters on the Regular channel, **GKE handles upgrades automatically**, and this is actually the **recommended approach** for production environments. Here's what you need to know:

## How GKE Auto-Upgrades Work

**Control Plane:**
- Automatically upgraded by Google within the channel's version window
- You cannot disable control plane auto-upgrades
- Upgrades happen during your defined maintenance window

**Node Pools:**
- Auto-upgrade is **enabled by default** and recommended
- Upgrades triggered after control plane upgrades
- Respects maintenance windows and upgrade policies

## Recommended Production Setup

```bash
# Verify auto-upgrade is enabled (should be by default)
gcloud container clusters describe CLUSTER_NAME \
  --zone=ZONE \
  --format="value(nodeConfig.upgradeSettings.autoUpgrade)"

# Configure maintenance windows
gcloud container clusters update CLUSTER_NAME \
  --maintenance-window-start="2023-01-01T09:00:00Z" \
  --maintenance-window-end="2023-01-01T17:00:00Z" \
  --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SA"
```

## Configure Upgrade Policies for Production

```yaml
# Example: Conservative upgrade policy
apiVersion: v1
kind: ConfigMap
metadata:
  name: cluster-upgrade-policy
data:
  max-surge: "1"
  max-unavailable: "0"  # Zero downtime upgrades
```

```bash
# Apply surge upgrade settings
gcloud container clusters update CLUSTER_NAME \
  --zone=ZONE \
  --max-surge=1 \
  --max-unavailable=0
```

## Best Practices for Production

1. **Keep Auto-Upgrade Enabled**
   ```bash
   gcloud container node-pools update POOL_NAME \
     --cluster=CLUSTER_NAME \
     --zone=ZONE \
     --enable-autoupgrade
   ```

2. **Set Appropriate Maintenance Windows**
   ```bash
   # Weekend maintenance window
   gcloud container clusters update CLUSTER_NAME \
     --maintenance-window="2023-01-07T02:00:00-08:00" \
     --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SA"
   ```

3. **Monitor Upgrade Status**
   ```bash
   # Check cluster status
   gcloud container operations list \
     --filter="operationType:UPGRADE_MASTER OR operationType:UPGRADE_NODES"
   ```

## When to Consider Manual Upgrades

Manual upgrades might be appropriate if you need:
- Specific timing control beyond maintenance windows
- Coordination with application deployments
- Testing in staging before production upgrades

## Monitoring and Alerting

Set up monitoring for upgrade events:
```bash
# Create notification channel for upgrade alerts
gcloud alpha monitoring channels create \
  --display-name="GKE Upgrades" \
  --type=email \
  --channel-labels=email_address=your-team@company.com
```

## Summary

**Stick with auto-upgrades** for your production GKE clusters. The Regular channel provides a good balance of stability and timely security updates. Focus your efforts on:

1. Configuring appropriate maintenance windows
2. Setting conservative surge upgrade policies
3. Monitoring upgrade events
4. Testing your applications' compatibility with new versions in staging

This approach ensures you get timely security patches while maintaining production stability with minimal operational overhead.