For your Cassandra ring with local SSDs, **blue-green upgrade is the clear choice**. Here's why surge won't work and how to configure blue-green properly.

## Why Blue-Green for Cassandra + Local SSDs

**Surge upgrade problems:**
- **Data loss risk**: Surge drains nodes, destroying local SSD data. Cassandra data stored on local SSDs cannot survive node replacement.
- **Rebalancing storms**: Direct node drain without proper decommissioning causes Cassandra to detect node failure and trigger emergency rebalancing across the ring.
- **Quorum disruption**: PDBs only protect for 1 hour before GKE force-evicts. Cassandra decommissioning can take longer.

**Blue-green advantages:**
- **Zero data loss**: Old nodes remain available during the transition, preserving local SSD data until Cassandra naturally rebalances.
- **Controlled decommissioning**: Soak period allows time to properly decommission Cassandra nodes before deletion.
- **Rollback safety**: Can quickly revert by uncordoning the blue pool if issues arise.

## Configuration Commands

```bash
# Configure blue-green upgrade strategy
gcloud container node-pools update CASSANDRA_NODE_POOL \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --strategy=BLUE_GREEN \
    --node-pool-soak-duration=7200s \
    --standard-rollout-policy=batch-node-count=1,batch-soak-duration=300s
```

**Parameter explanation:**
- `--node-pool-soak-duration=7200s` (2 hours): Time to validate Cassandra ring health after all nodes drain but before deleting blue pool
- `batch-node-count=1`: Drain one Cassandra node at a time (conservative for ring stability)
- `batch-soak-duration=300s` (5 minutes): Wait between each node drain for ring to stabilize

## Pre-Upgrade Cassandra Preparation

```bash
# 1. Take application-level backup
nodetool snapshot keyspace_name

# 2. Configure PDB for ring protection (allows 1 node down, protects quorum)
cat <<EOF | kubectl apply -f -
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-pdb
  namespace: cassandra-namespace
spec:
  minAvailable: 8  # 9 nodes - 1 = maintains quorum
  selector:
    matchLabels:
      app: cassandra
EOF

# 3. Verify ring health before upgrade
nodetool status
nodetool describering
```

## Upgrade Workflow with Cassandra Integration

```bash
# 1. Start blue-green upgrade
gcloud container node-pools upgrade CASSANDRA_NODE_POOL \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version TARGET_VERSION

# 2. During the soak period (while blue pool is cordoned but not deleted):
#    Monitor Cassandra ring status
nodetool status
# Look for nodes showing as "Down" - these are on the blue pool

# 3. Optionally decommission blue pool nodes during soak (recommended):
kubectl exec -it cassandra-pod-on-blue-node -- nodetool decommission
# Repeat for each blue pool node, wait for status "Left"

# 4. Complete upgrade after ring rebalances
gcloud container node-pools complete-upgrade CASSANDRA_NODE_POOL \
    --cluster CLUSTER_NAME \
    --zone ZONE
```

## Important Considerations

**Capacity requirements:**
- Blue-green temporarily **doubles your node pool size** (18 nodes during upgrade)
- Verify you have sufficient compute quota: 9 additional nodes × machine-type
- Budget for 2x cost during the 2+ hour upgrade window

**Network topology:**
- Cassandra seed nodes may need updating if they point to specific IP addresses
- Verify Cassandra can discover new nodes in the green pool
- Consider using headless services for seed discovery instead of hardcoded IPs

**Ring rebalancing timeline:**
- New nodes (green pool) will start as empty and gradually receive data
- Full rebalancing can take hours depending on data size
- Monitor with `nodetool netstats` during the soak period

## Alternative: Manual Blue-Green (if automated blue-green doesn't fit)

If the 2-hour soak period isn't sufficient for your ring size, consider manual blue-green:

```bash
# 1. Create new node pool at target version
gcloud container node-pools create cassandra-v2 \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version TARGET_VERSION \
    --num-nodes 9 \
    --machine-type MACHINE_TYPE \
    --local-ssd-count LOCAL_SSD_COUNT

# 2. Let Cassandra discover new nodes and rebalance naturally
# 3. Once rebalanced, decommission old pool nodes one by one
# 4. Delete old pool when empty
```

**Recommendation**: Start with GKE's native blue-green strategy. It handles the coordination automatically and provides rollback options. Only use manual blue-green if the automated soak period proves insufficient for your specific ring size and rebalancing time.

The key is giving Cassandra time to rebalance properly rather than forcing immediate node replacement that surge upgrades require.