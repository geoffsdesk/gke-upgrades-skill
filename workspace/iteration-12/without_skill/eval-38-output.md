For GKE Standard clusters on the Regular channel, **GKE handles upgrades automatically**, and this is generally the **recommended approach** for production environments. Here's what you need to know:

## How GKE Auto-Upgrades Work

### Control Plane
- **Automatic**: GKE automatically upgrades your control plane
- **Timing**: Usually within 2-3 weeks after a version becomes available on Regular channel
- **Maintenance Windows**: Upgrades occur during your configured maintenance window
- **Zero Downtime**: Control plane upgrades don't affect running workloads

### Node Pools
- **Automatic by Default**: Node pools auto-upgrade unless explicitly disabled
- **Rolling Updates**: Nodes are upgraded in a rolling fashion to maintain availability
- **Surge Settings**: Configure `max-surge` and `max-unavailable` to control upgrade speed vs. availability

## Recommended Configuration

```bash
# Set maintenance window (example: weekends)
gcloud container clusters update CLUSTER_NAME \
    --maintenance-window-start "2023-01-07T02:00:00Z" \
    --maintenance-window-end "2023-01-07T06:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Configure node pool surge settings for controlled upgrades
gcloud container node-pools update NODE_POOL_NAME \
    --cluster=CLUSTER_NAME \
    --max-surge=1 \
    --max-unavailable=0
```

## Best Practices for Production

### 1. **Enable Auto-Upgrades (Default)**
```bash
# Verify auto-upgrade is enabled
gcloud container node-pools describe NODE_POOL_NAME \
    --cluster=CLUSTER_NAME \
    --format="value(management.autoUpgrade)"
```

### 2. **Set Appropriate Maintenance Windows**
- Schedule during low-traffic periods
- Ensure your team can monitor during upgrades
- Consider multiple windows for global deployments

### 3. **Configure Surge Settings Conservatively**
```bash
# For critical production workloads
--max-surge=1 --max-unavailable=0

# For less critical workloads (faster upgrades)
--max-surge=2 --max-unavailable=1
```

### 4. **Use Exclusion Windows for Critical Periods**
```bash
# Block upgrades during critical business periods
gcloud container clusters update CLUSTER_NAME \
    --add-maintenance-exclusion-name="black-friday" \
    --add-maintenance-exclusion-start="2023-11-20T00:00:00Z" \
    --add-maintenance-exclusion-end="2023-11-27T23:59:59Z"
```

## When to Consider Manual Upgrades

### Scenarios for Manual Control:
- **Highly regulated environments** requiring change approval processes
- **Critical applications** where you need to test specific versions first
- **Complex workloads** that require extensive validation

### If choosing manual upgrades:
```bash
# Disable auto-upgrade
gcloud container node-pools update NODE_POOL_NAME \
    --cluster=CLUSTER_NAME \
    --no-enable-autoupgrade

# Manually upgrade when ready
gcloud container clusters upgrade CLUSTER_NAME \
    --cluster-version=VERSION
```

## Monitoring and Alerts

Set up monitoring for upgrade events:

```yaml
# Example alerting policy for upgrade failures
displayName: "GKE Upgrade Failures"
conditions:
  - displayName: "Upgrade operation failed"
    conditionThreshold:
      filter: 'resource.type="gke_cluster" AND protoPayload.methodName="google.container.v1.ClusterManager.UpdateCluster"'
      comparison: COMPARISON_GREATER_THAN
      thresholdValue: 0
```

## Recommended Approach for Your Setup

For your 3 production clusters on Regular channel:

1. **Keep auto-upgrades enabled** (default and recommended)
2. **Configure maintenance windows** for your preferred upgrade times
3. **Set conservative surge settings** (`max-surge=1, max-unavailable=0`)
4. **Set up monitoring** for upgrade events and cluster health
5. **Use exclusion windows** for critical business periods
6. **Test application compatibility** in staging clusters first

This approach provides the security benefits of timely updates while maintaining production stability and giving you control over timing.