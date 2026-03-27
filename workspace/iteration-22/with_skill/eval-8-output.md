For your Cassandra ring with local SSDs, **blue-green upgrade is strongly recommended**. Here's why and how to configure it:

## Why Blue-Green for Cassandra + Local SSDs

**Critical issue with surge upgrades:** Surge upgrades drain nodes, which **destroys local SSD data**. For Cassandra, this means:
- Data loss on each node as it's drained
- Massive rebalancing storms as the ring rebuilds from replicas
- Potential quorum loss if multiple nodes drain simultaneously
- High risk of cluster instability

**Blue-green advantages:**
- Preserves data integrity during the transition
- Allows proper Cassandra decommissioning workflow
- Fast rollback path if issues arise
- Controlled, gradual transition respecting Cassandra's distributed nature

## Recommended Configuration

```bash
# Configure blue-green upgrade strategy
gcloud container node-pools update CASSANDRA_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --strategy=BLUE_GREEN \
    --node-pool-soak-duration=7200s \
    --standard-rollout-policy=batch-node-count=1,batch-soak-duration=600s
```

**Key parameters explained:**
- `--node-pool-soak-duration=7200s` (2 hours): Extended soak time to validate Cassandra ring health before deleting blue pool
- `batch-node-count=1`: Decommission one Cassandra node at a time (conservative)
- `batch-soak-duration=600s` (10 minutes): Wait between each node to allow ring rebalancing

## Essential PDB Configuration

Configure this **before** upgrading:

```bash
# Create PDB for Cassandra StatefulSet
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-pdb
  namespace: CASSANDRA_NAMESPACE
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: cassandra
EOF
```

This ensures at least 2 Cassandra nodes remain available during the blue-green transition, protecting quorum (majority of 9 = 5 nodes).

## Cassandra-Specific Workflow

Blue-green handles the infrastructure, but you'll need to manage Cassandra decommissioning:

**During the soak period (after blue pool cordoned, before deletion):**

1. **Monitor ring status:**
```bash
kubectl exec -it cassandra-0 -n CASSANDRA_NAMESPACE -- nodetool status
```

2. **For each node on the blue pool, decommission properly:**
```bash
# Identify which pods are on blue pool nodes
kubectl get pods -n CASSANDRA_NAMESPACE -o wide

# Decommission each blue pool Cassandra node
kubectl exec -it CASSANDRA_POD_ON_BLUE_NODE -n CASSANDRA_NAMESPACE -- nodetool decommission

# Verify node shows as "Left" in ring status
kubectl exec -it cassandra-0 -n CASSANDRA_NAMESPACE -- nodetool status
```

3. **Wait for new nodes to join and data to rebalance:**
```bash
# Monitor data streaming
kubectl exec -it cassandra-0 -n CASSANDRA_NAMESPACE -- nodetool netstats

# Verify all nodes are "Up Normal" 
kubectl exec -it cassandra-0 -n CASSANDRA_NAMESPACE -- nodetool status
```

## Capacity Requirements

**Important:** Blue-green requires enough quota to temporarily **double your node pool size**. For 9 Cassandra nodes, you'll need capacity for 18 nodes during the upgrade.

**Before upgrading, verify:**
```bash
# Check current quota usage
gcloud compute project-info describe --project PROJECT_ID

# Ensure you have headroom for 9 additional nodes of your instance type
```

## Pre-Upgrade Checklist

```markdown
Cassandra Blue-Green Upgrade Checklist
- [ ] Blue-green strategy configured with 2-hour soak duration
- [ ] PDB set to minAvailable: 2 (protects quorum)
- [ ] Compute quota verified for 2x node pool size (18 nodes total)
- [ ] Cassandra application-level backup completed (`nodetool snapshot`)
- [ ] Ring status healthy: `nodetool status` shows all nodes "Up Normal"
- [ ] No pending repairs or compactions running
- [ ] Maintenance window spans at least 4-6 hours for full blue-green cycle
- [ ] On-call team aware of decommissioning requirements during soak period
```

## Timeline Expectations

- **Green pool creation:** 10-15 minutes
- **Blue pool cordon + drain:** 30-60 minutes (1 node per batch + 10min soak)
- **Manual decommissioning:** 30-90 minutes per node (depends on data size)
- **Soak period:** 2 hours (configurable)
- **Total duration:** 4-6 hours

This approach protects your Cassandra data while providing the safest upgrade path for your stateful, local-storage workload.