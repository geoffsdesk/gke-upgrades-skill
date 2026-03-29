For GKE Standard clusters on the Regular channel, **GKE handles upgrades automatically**, and this is actually the **recommended approach** for production environments. Here's what you need to know:

## How GKE Auto-Upgrades Work

**Control Plane:**
- Automatically upgraded by Google within the release channel's schedule
- Regular channel typically gets updates 2-3 months after Rapid channel
- You receive advance notifications before upgrades

**Node Pools:**
- Auto-upgrade is enabled by default on new clusters
- Upgrades are rolled out gradually using surge upgrades (adds new nodes, drains old ones)
- Maintains availability during the process

## Recommended Production Strategy

```bash
# Verify auto-upgrade is enabled (should be by default)
gcloud container clusters describe CLUSTER_NAME \
    --zone=ZONE \
    --format="value(nodePools[].management.autoUpgrade)"
```

**Best practices for production:**

1. **Keep auto-upgrade enabled** but add controls:
```bash
# Set maintenance windows to control when upgrades occur
gcloud container clusters update CLUSTER_NAME \
    --zone=ZONE \
    --maintenance-window-start="2024-01-15T09:00:00Z" \
    --maintenance-window-end="2024-01-15T17:00:00Z" \
    --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SU"
```

2. **Set up monitoring and notifications:**
```bash
# Enable cluster notifications
gcloud container clusters update CLUSTER_NAME \
    --zone=ZONE \
    --enable-notification-config \
    --notification-config-topic=projects/PROJECT_ID/topics/gke-upgrades
```

3. **Use multiple clusters with staggered upgrades:**
```bash
# Different maintenance windows for each cluster
# Cluster 1: Sunday 2-6 AM
# Cluster 2: Sunday 6-10 AM  
# Cluster 3: Sunday 10 AM-2 PM
```

## When to Consider Manual Control

Only disable auto-upgrade if you have:
- Strict compliance requirements requiring change approval
- Applications that need extensive testing with new Kubernetes versions
- Complex deployment pipelines that need coordination

```bash
# If you must disable auto-upgrade
gcloud container clusters update CLUSTER_NAME \
    --zone=ZONE \
    --no-enable-autoupgrade
```

## Monitoring Upgrade Health

Set up alerts for upgrade events:
```yaml
# Example monitoring query
resource.type="gke_cluster"
protoPayload.methodName="google.container.v1.ClusterManager.UpdateCluster"
```

**Bottom line:** Stick with auto-upgrades but use maintenance windows and monitoring to maintain control. This gives you security patches and bug fixes automatically while minimizing operational overhead.