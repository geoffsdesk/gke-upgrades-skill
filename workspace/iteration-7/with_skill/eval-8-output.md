# Node Pool Upgrade Strategy: Cassandra with Local SSDs

## Recommendation: Auto-Scale Blue-Green Upgrade

For your Cassandra ring with local SSDs, I **strongly recommend the auto-scale blue-green upgrade strategy**. Here's why:

### Why Blue-Green is Better for Cassandra + Local SSDs

| Factor | Surge Upgrade | Blue-Green Upgrade |
|--------|---------------|-------------------|
| **Data preservation** | ❌ Local SSD data lost on each node replacement | ✅ Clean migration, predictable data movement |
| **Cassandra consistency** | ❌ Rolling disruption can cause quorum issues | ✅ Controlled migration preserves ring topology |
| **Rollback capability** | ❌ Can't roll back after nodes are replaced | ✅ Instant rollback by switching back to old pool |
| **Capacity during upgrade** | ❌ Temporary capacity reduction during rolling replacement | ✅ Full capacity maintained throughout |
| **Upgrade predictability** | ❌ Unpredictable timing per node | ✅ Orchestrated migration with full control |

### The Local SSD Challenge

Local SSDs are **ephemeral storage** — when a node is replaced during surge upgrade, all local SSD data is permanently lost. For Cassandra:

- Each node replacement triggers data rebuilding from other replicas
- Multiple simultaneous rebuilds can overwhelm the cluster
- Network and CPU spike during rebuild affects application performance
- Risk of data loss if multiple nodes in same replication group fail

Blue-green eliminates this by allowing **controlled migration** where you can:
1. Bootstrap new Cassandra nodes in the new pool
2. Use `nodetool decommission` for graceful data handoff
3. Preserve ring topology and replication guarantees

## Configuration: Auto-Scale Blue-Green

Here's the step-by-step configuration and execution:

### Step 1: Pre-flight Preparation

```bash
# Document current pool configuration
gcloud container node-pools describe cassandra-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE > current-pool-config.yaml

# Verify Cassandra ring health
kubectl exec -it cassandra-0 -- nodetool status
kubectl exec -it cassandra-0 -- nodetool ring

# Backup Cassandra schema (recommended)
kubectl exec -it cassandra-0 -- cqlsh -e "DESCRIBE KEYSPACES;"
```

### Step 2: Configure Blue-Green Strategy

```bash
# Enable auto-scale blue-green upgrade on the node pool
gcloud container node-pools update cassandra-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --node-pool-soak-duration 300s \
  --blue-green-settings node-pool-soak-duration=300s
```

### Step 3: Execute the Upgrade

```bash
# Start the blue-green upgrade
gcloud container node-pools upgrade cassandra-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION \
  --upgrade-strategy BLUE_GREEN

# Monitor progress
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --filter="operationType=UPGRADE_NODES" \
  --format="table(name,operationType,status,startTime)"
```

### Step 4: Migration Process (Automated by GKE)

GKE will automatically:

1. **Create replacement pool** with 9 new nodes at target version
2. **Cordon old pool** (prevents new pod scheduling)
3. **Wait for soak duration** (5 minutes) - use this time to validate new nodes
4. **Migrate workloads** using standard Kubernetes eviction
5. **Delete old pool** after successful migration

### Step 5: Cassandra-Specific Validation During Migration

While GKE handles the orchestration, monitor Cassandra health:

```bash
# Watch pod migration
kubectl get pods -l app=cassandra -o wide --watch

# Monitor Cassandra ring during migration
kubectl exec -it cassandra-0 -- nodetool status
# Look for nodes joining/leaving the ring

# Check replication health
kubectl exec -it cassandra-0 -- nodetool describering KEYSPACE_NAME
```

### Step 6: Post-Upgrade Validation

```bash
# Verify all nodes on new pool
kubectl get nodes -l cloud.google.com/gke-nodepool=cassandra-pool

# Confirm Cassandra ring health
kubectl exec -it cassandra-0 -- nodetool status
# All nodes should show "UN" (Up Normal)

# Test application connectivity
kubectl exec -it cassandra-0 -- cqlsh -e "SELECT * FROM system.local;"
```

## Rollback Plan (Blue-Green Advantage)

If issues arise during migration:

```bash
# Cancel the blue-green operation (if still in progress)
gcloud container operations cancel OPERATION_ID \
  --zone ZONE

# The old pool remains available for immediate rollback
# Pods will automatically reschedule back to old nodes
```

## Alternative: Manual Blue-Green (If You Need More Control)

If you need granular control over Cassandra decommissioning:

```bash
# Create replacement pool manually
gcloud container node-pools create cassandra-pool-v2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION \
  --machine-type n1-standard-4 \
  --local-ssd-count 2 \
  --num-nodes 9

# Cordon old pool
kubectl cordon -l cloud.google.com/gke-nodepool=cassandra-pool

# Scale StatefulSet to new pool (with anti-affinity to spread across new nodes)
# Use rolling update to migrate pods one-by-one
# Run `nodetool decommission` on each old node before deleting
```

## Key Configuration Notes

- **Soak duration**: Set to 300s (5 minutes) to validate new nodes before migration
- **Local SSD preservation**: Blue-green is the only strategy that gives you control over data migration
- **Capacity planning**: Blue-green temporarily doubles your node count (18 nodes during migration)
- **Network policies**: Ensure new nodes can reach existing Cassandra nodes for bootstrapping

The auto-scale blue-green upgrade gives you the best of both worlds: GKE's automated orchestration with the safety and predictability that stateful workloads like Cassandra require.