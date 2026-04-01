For GKE Standard clusters on the Regular channel, **GKE handles upgrades automatically**, and this is actually the **recommended approach** for production environments. Here's what you need to know:

## How GKE Auto-Upgrades Work

### Control Plane Upgrades
- **Automatic**: GKE automatically upgrades your control plane within the Regular channel
- **No downtime**: Control plane upgrades are seamless
- **Regular schedule**: Typically every few weeks as new versions are promoted to Regular

### Node Pool Upgrades
- **Automatic by default**: Node pools auto-upgrade to match the control plane version
- **Configurable**: You can customize the upgrade behavior

## Recommended Production Setup

```yaml
# Example node pool configuration for production
resource "google_container_node_pool" "production_nodes" {
  name       = "production-pool"
  location   = var.region
  cluster    = google_container_cluster.primary.name
  
  # Auto-upgrade settings
  management {
    auto_upgrade = true
    auto_repair  = true
  }
  
  # Upgrade settings for controlled rollouts
  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
    strategy        = "SURGE"
  }
}
```

## Configure Maintenance Windows

Set up maintenance windows to control when upgrades occur:

```yaml
resource "google_container_cluster" "primary" {
  name     = "production-cluster"
  location = var.region

  maintenance_policy {
    recurring_window {
      start_time = "2023-01-01T02:00:00Z"
      end_time   = "2023-01-01T06:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SA"
    }
  }
}
```

## Best Practices for Production

1. **Keep auto-upgrades enabled** but configure maintenance windows
2. **Set up monitoring** for upgrade notifications:
   ```bash
   # Enable upgrade notifications
   gcloud container clusters update CLUSTER_NAME \
     --enable-notification-config \
     --notification-config=pubsub=projects/PROJECT_ID/topics/gke-upgrades
   ```

3. **Use multiple node pools** for safer upgrades:
   ```bash
   # Create additional node pools for zero-downtime upgrades
   gcloud container node-pools create backup-pool \
     --cluster=production-cluster \
     --num-nodes=3
   ```

4. **Test upgrades** in staging first using the Rapid channel

## When to Consider Manual Control

You might want more control if you need to:
- Coordinate upgrades with application deployments
- Perform extensive testing before each upgrade
- Meet strict compliance requirements

In these cases, you can disable auto-upgrade but **you must stay within the supported version skew**.

## Monitoring and Alerting

Set up alerts for upgrade events:
```bash
# Get upgrade status
gcloud container operations list \
  --filter="operationType:UPGRADE_MASTER OR operationType:UPGRADE_NODES"

# Check cluster status
kubectl get nodes -o wide
```

**Bottom line**: Stick with auto-upgrades on the Regular channel with proper maintenance windows configured. This gives you the security and stability benefits while maintaining operational simplicity. Manual upgrades add operational overhead without significant benefits for most production workloads.