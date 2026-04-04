Based on your Cassandra ring with local SSDs, I **strongly recommend blue-green upgrade**. Here's why and how to configure it:

## Why Blue-Green for Cassandra + Local SSDs

**Surge upgrade would be problematic because:**
- **Data loss risk**: Surge drains nodes, destroying local SSD data. Even with proper decommissioning, the drain process doesn't wait for Cassandra's `nodetool decommission` to complete
- **Rebalancing storms**: Without proper decommissioning, remaining nodes experience heavy rebalancing as data redistributes
- **Extended disruption**: Each node replacement triggers cluster-wide rebalancing

**Blue-green advantages for your use case:**
- **Preserves existing ring**: Old nodes stay running while new nodes provision
- **Graceful decommissioning**: Soak period allows proper `nodetool decommission` workflow
- **Fast rollback**: If issues arise, uncordon the blue pool immediately
- **Controlled transition**: Move one node at a time with validation between each

## Configuration Commands

```bash
# Configure blue-green strategy with extended soak time for Cassandra decommissioning
gcloud container node-pools update CASSANDRA_POOL_NAME \
    --cluster CLUSTER_NAME \
    --region REGION \
    --strategy=BLUE_GREEN \
    --node-pool-soak-duration=7200s \
    --standard-rollout-policy=batch-node-count=1,batch-soak-duration=300s
```

**Parameters explained:**
- `--node-pool-soak-duration=7200s` (2 hours): Enough time to validate the new ring and complete decommissioning
- `batch-node-count=1`: Process one node at a time to minimize cluster disruption
- `batch-soak-duration=300s` (5 min): Wait between each node to monitor cluster health

## Cassandra-Specific Blue-Green Workflow

### Phase 1: Preparation
```bash
# Ensure PDB allows single node disruption
kubectl get pdb -n cassandra-namespace
# Should have minAvailable: 8 (or 89% if using percentage)

# Backup before upgrade
kubectl exec -n NAMESPACE cassandra-0 -- nodetool snapshot
```

### Phase 2: During Blue-Green Upgrade
The blue-green upgrade will automatically:
1. Create green pool with target version
2. Cordon blue pool (existing Cassandra nodes)
3. Begin draining blue pool one node at a time

**Manual intervention during soak period:**
```bash
# After green pool is ready, before blue pool deletion:
# SSH into each blue pool node being drained and decommission properly

# For each node being drained:
kubectl exec -n NAMESPACE cassandra-pod-on-draining-node -- nodetool decommission
# Wait for node status to show "Left" before allowing drain to continue

# Monitor ring status throughout
kubectl exec -n NAMESPACE cassandra-0 -- nodetool status
```

### Phase 3: Validation During Soak
```bash
# Verify new nodes joined the ring
kubectl exec -n NAMESPACE cassandra-0 -- nodetool status
# All nodes should show "UN" (Up/Normal)

# Check data consistency
kubectl exec -n NAMESPACE cassandra-0 -- nodetool repair -pr

# Monitor cluster health
kubectl get pods -n NAMESPACE -l app=cassandra
```

## Resource Requirements

**Critical**: Blue-green temporarily doubles your node pool size. Ensure you have:
- Quota for 18 nodes (9 blue + 9 green) during upgrade
- Local SSD quota for double the current usage
- Budget for ~2 hours of 2x compute cost

If quota is insufficient, you'll need to either:
1. Request quota increase before upgrade
2. Use manual blue-green with smaller batches (3-node rolling groups)

## PDB Configuration for Cassandra

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-pdb
  namespace: cassandra-namespace
spec:
  minAvailable: 8  # Allows 1 node disruption, preserves quorum
  selector:
    matchLabels:
      app: cassandra
```

## Alternative if Blue-Green Isn't Feasible

If quota constraints prevent blue-green, use **manual controlled upgrade**:

```bash
# Create new 3-node pool at target version
gcloud container node-pools create cassandra-new \
    --cluster CLUSTER_NAME \
    --region REGION \
    --node-version TARGET_VERSION \
    --num-nodes 3 \
    --local-ssd-count 1

# Migrate 3 nodes at a time, decommission properly, then repeat
# This reduces the quota requirement to 12 nodes max (9 + 3)
```

**Bottom line**: Blue-green is the safest approach for Cassandra with local SSDs, provided you have the quota. The extended soak period gives you time to properly decommission nodes and validate the ring before the old nodes are deleted.