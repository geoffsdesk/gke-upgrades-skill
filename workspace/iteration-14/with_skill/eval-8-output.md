For your Cassandra ring with local SSDs, I **strongly recommend blue-green upgrade**. Here's why and how to configure it:

## Why Blue-Green for Cassandra + Local SSDs

**Surge upgrade risks for your setup:**
- **Data loss**: Surge upgrades drain the old node first, which **destroys local SSD data**. Your Cassandra ring would lose data on each node as it's upgraded.
- **Ring instability**: Cassandra rings are sensitive to node changes. Surge's rolling replacement could cause multiple nodes to leave/rejoin the ring sequentially, potentially triggering cascading failures.
- **No graceful handoff**: Local SSD data can't be migrated between nodes during surge.

**Blue-green advantages:**
- **Data preservation**: Old nodes stay available during upgrade, keeping local SSD data intact until workloads naturally migrate
- **Ring stability**: Cassandra nodes remain in the ring longer, allowing for controlled data replication before decommissioning
- **Quick rollback**: If upgrade issues arise, you can immediately redirect traffic back to the blue (old) pool

## Configuration Commands

### 1. Pre-upgrade preparation
```bash
# Verify current setup
kubectl get nodes -l cloud.google.com/gke-nodepool=YOUR_CASSANDRA_POOL -o wide
kubectl get pods -n YOUR_CASSANDRA_NAMESPACE -o wide

# Check local SSD mounts
kubectl get pods -n YOUR_CASSANDRA_NAMESPACE -o jsonpath='{.items[*].spec.volumes[*].hostPath.path}' | tr ' ' '\n' | sort -u

# Verify Cassandra ring health before upgrade
kubectl exec -n YOUR_CASSANDRA_NAMESPACE cassandra-0 -- nodetool status
```

### 2. Configure blue-green upgrade
```bash
# Enable blue-green strategy for your Cassandra node pool
gcloud container node-pools update YOUR_CASSANDRA_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --node-pool-soak-duration=10m \
  --blue-green-settings node-pool-soak-duration=10m

# Note: Do NOT set maxSurge/maxUnavailable - these don't apply to blue-green
```

### 3. Execute the upgrade
```bash
# Start blue-green upgrade
gcloud container node-pools upgrade YOUR_CASSANDRA_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

## What happens during blue-green upgrade:

1. **Green pool creation**: GKE creates new nodes with the target version
2. **Gradual migration**: Pods are slowly drained from blue (old) to green (new) nodes
3. **Soak period**: 10-minute validation window with both pools running
4. **Automatic cutover**: Old blue pool is deleted after successful migration

## Cassandra-specific considerations:

### Monitor ring health during upgrade:
```bash
# Watch Cassandra ring status
watch 'kubectl exec -n YOUR_CASSANDRA_NAMESPACE cassandra-0 -- nodetool status'

# Monitor pod distribution
watch 'kubectl get pods -n YOUR_CASSANDRA_NAMESPACE -o wide'
```

### Expected behavior:
- Cassandra pods will be rescheduled to new nodes
- **Local SSD data will be lost** on the old nodes (this is unavoidable with any upgrade strategy)
- Cassandra should rebuild data through its normal replication process
- With proper replication factor (RF=3 recommended), no data should be permanently lost

### Prerequisites for success:
- **Replication factor ≥ 3** (essential for data safety during node transitions)
- **Consistent snapshots** taken before upgrade as backup
- **Monitor disk space** on remaining nodes during data rebuilding

## Alternative approach (if blue-green isn't suitable):

If you can't accommodate 2x node pool size temporarily, consider:

1. **Manual cordon-and-wait**:
   ```bash
   # Cordon 1/3 of nodes
   kubectl cordon node-1 node-2 node-3
   
   # Wait for Cassandra to redistribute data naturally
   # This can take hours depending on data size
   
   # Delete cordoned nodes and let cluster autoscaler replace them
   ```

2. **Dedicated maintenance windows** with full cluster downtime for atomic replacement

## Capacity requirements:

Blue-green temporarily needs **2x your Cassandra node pool size**. For your 9-node ring, you'll need capacity for 18 nodes during the upgrade window.

Would you like me to help you verify your quota limits or adjust the configuration for your specific Cassandra setup?