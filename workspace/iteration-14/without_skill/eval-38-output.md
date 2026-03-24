For GKE Standard clusters on the Regular channel, **GKE handles upgrades automatically**, and this is actually the **recommended approach** for production environments. Here's what you need to know:

## How GKE Auto-Upgrades Work

**Control Plane:**
- Upgrades automatically within your maintenance window
- No downtime for the API server
- You can configure maintenance windows and exclusions

**Node Pools:**
- Auto-upgrade enabled by default on Standard clusters
- Upgrades follow the control plane (usually within a few days)
- Uses rolling updates to minimize disruption

## Recommended Configuration

```bash
# Set maintenance windows (example: weekends)
gcloud container clusters update CLUSTER_NAME \
    --maintenance-window-start "2023-01-07T09:00:00Z" \
    --maintenance-window-end "2023-01-07T17:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Configure maintenance exclusions for critical periods
gcloud container clusters update CLUSTER_NAME \
    --add-maintenance-exclusion-end "2023-12-31T23:59:59Z" \
    --add-maintenance-exclusion-name "holiday-freeze" \
    --add-maintenance-exclusion-start "2023-12-20T00:00:00Z"
```

## Best Practices for Production

1. **Keep Auto-Upgrades Enabled**
   ```bash
   # Verify auto-upgrade is enabled
   gcloud container clusters describe CLUSTER_NAME \
       --format="value(nodeConfig.autoUpgrade)"
   ```

2. **Configure Surge Upgrades** for faster, less disruptive updates:
   ```bash
   gcloud container node-pools update POOL_NAME \
       --cluster=CLUSTER_NAME \
       --max-surge=2 \
       --max-unavailable=1
   ```

3. **Set up Monitoring**:
   - Monitor cluster events during maintenance windows
   - Set up alerts for upgrade failures
   - Track application health during upgrades

4. **Use Blue/Green or Multi-Cluster Strategy** for zero-downtime requirements

## When to Consider Manual Upgrades

Only consider manual upgrades if you:
- Need to test specific versions in staging first
- Have very strict change control processes
- Want to batch upgrades across multiple clusters

However, **manual upgrades require more operational overhead** and you'll miss out on automatic security patches.

## Action Items for Your Setup

1. Configure maintenance windows for each cluster
2. Set up maintenance exclusions for critical business periods
3. Verify surge upgrade settings match your capacity requirements
4. Enable monitoring for upgrade events
5. Document your upgrade process for the team

The Regular channel with auto-upgrades gives you a good balance of stability and security updates, making it ideal for production workloads.