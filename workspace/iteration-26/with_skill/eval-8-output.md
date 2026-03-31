For your Cassandra ring with local SSDs, I **strongly recommend blue-green upgrade**. Here's why:

## Why Blue-Green is Critical for Cassandra + Local SSDs

**Local SSD data loss with surge:** Surge upgrades drain nodes, which **destroys all local SSD data**. For Cassandra, this means:
- Data stored on local SSDs is permanently lost during node drain
- Cassandra must rebuild data from other replicas (massive network traffic)
- Risk of multiple nodes rebuilding simultaneously if surge drains multiple Cassandra nodes

**Blue-green advantages for Cassandra:**
- Old nodes (blue pool) stay available with intact local SSD data during upgrade
- New nodes (green pool) join as fresh Cassandra nodes
- You control when to decommission old nodes **after** new nodes are fully integrated
- Proper Cassandra decommissioning redistributes data gracefully (no rebuild storms)

## Recommended Configuration

```bash
# Configure blue-green upgrade for your Cassandra node pool
gcloud container node-pools update CASSANDRA_NODE_POOL \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --strategy=BLUE_GREEN \
    --node-pool-soak-duration=7200s \
    --standard-rollout-policy=batch-node-count=1,batch-soak-duration=300s
```

**Key parameters explained:**
- `--node-pool-soak-duration=7200s` (2 hours): Time to validate new Cassandra nodes are healthy before deleting old nodes
- `batch-node-count=1`: Drain one node at a time (conservative for stateful workloads)  
- `batch-soak-duration=300s` (5 minutes): Wait between each node drain for Cassandra to stabilize

## Pre-Upgrade Cassandra Preparation

```bash
# 1. Configure PDB to protect quorum (adjust for your replication factor)
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-pdb
spec:
  minAvailable: 6  # For RF=3, keep at least 6 of 9 nodes available
  selector:
    matchLabels:
      app: cassandra

# 2. Take application-level backup
kubectl exec -it cassandra-0 -- nodetool snapshot

# 3. Verify cluster health before upgrade
kubectl exec -it cassandra-0 -- nodetool status
kubectl exec -it cassandra-0 -- nodetool ring
```

## Blue-Green Upgrade Workflow

1. **Create green pool** (automatic) - New nodes provision with target GKE version
2. **Cordon blue pool** (automatic) - Old Cassandra nodes marked unschedulable  
3. **Drain blue pool in batches** - One node at a time, 5-minute gaps
4. **Soak period** (2 hours) - Validate new Cassandra ring is healthy
5. **Delete blue pool** (automatic after soak)

## Critical: Cassandra-Specific Steps During Upgrade

**During the soak period, you must:**

```bash
# 1. Verify new nodes joined the ring
kubectl exec -it NEW_CASSANDRA_POD -- nodetool status

# 2. For each old node being replaced, run proper decommission:
kubectl exec -it OLD_CASSANDRA_POD -- nodetool decommission

# 3. Wait for decommission to complete (status shows "Left")
kubectl exec -it OLD_CASSANDRA_POD -- nodetool netstats

# 4. Only after decommission: allow GKE to delete the old node
```

## Cost Consideration

Blue-green temporarily **doubles your node pool size** (18 nodes instead of 9). For a 2-hour soak period with your node size, budget accordingly. This cost is necessary to protect your Cassandra data.

## Alternative (Not Recommended): Custom Manual Process

If blue-green cost is prohibitive, you could:
1. Create new nodes manually, add to Cassandra ring
2. Use `nodetool decommission` on old nodes
3. Delete old nodes after decommission completes

But this is complex, error-prone, and lacks GKE's automated rollback capabilities.

## Why Not Surge for Cassandra

- **Data loss**: Local SSD data destroyed during drain
- **Rebuild storms**: Multiple nodes may rebuild simultaneously  
- **No rollback**: Once old nodes are deleted, data is gone
- **Timing risk**: 1-hour PDB timeout may force-evict during decommission

**Recommendation: Use blue-green for all stateful workloads with local storage.** The temporary cost increase is essential insurance against data loss.