For a Cassandra ring with 9 nodes on local SSDs, I **strongly recommend blue-green upgrade**. Here's why and how to configure it:

## Why blue-green for Cassandra

**Surge upgrade risks for Cassandra:**
- **Data locality loss**: Local SSDs are ephemeral - when nodes terminate during surge, all local data is permanently lost
- **Ring disruption**: Cassandra relies on consistent hash ring topology. Rolling node replacement can cause temporary inconsistencies and trigger unnecessary repairs
- **Replication factor stress**: If your RF=3, losing even 1-2 nodes during surge puts replicas at risk during the replacement window

**Blue-green advantages:**
- **Zero data movement**: Original nodes (blue pool) stay running with all data intact during the transition
- **Ring stability**: Cassandra ring remains fully intact on the blue pool while green pool nodes join as new members
- **Controlled migration**: You can gradually shift traffic and validate each step
- **Fast rollback**: If issues arise, simply uncordon the blue pool - all data is still there

## Blue-green configuration

```bash
# Configure the node pool for blue-green strategy
gcloud container node-pools update CASSANDRA_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-blue-green-upgrade \
  --node-pool-soak-duration 300s \
  --standard-rollout-policy-batch-node-count 3 \
  --standard-rollout-policy-batch-soak-duration 180s
```

## Migration approach for Cassandra

Since Cassandra requires special handling during blue-green transitions:

### Option 1: Expand-then-contract (Recommended)
```bash
# 1. Blue-green creates new nodes (green pool)
# 2. Scale Cassandra StatefulSet to 18 replicas (9 blue + 9 green)
kubectl scale statefulset cassandra --replicas=18

# 3. Wait for new nodes to join ring and streaming to complete
# Monitor with: kubectl exec cassandra-0 -- nodetool status

# 4. Once streaming complete, scale back to 9 (keeping green nodes)
kubectl scale statefulset cassandra --replicas=9

# 5. Cassandra will decommission the blue nodes automatically
```

### Option 2: Controlled decommission
```bash
# During blue-green transition, manually decommission blue nodes
for i in {0..8}; do
  kubectl exec cassandra-$i -- nodetool decommission
done
```

## Pre-upgrade preparation

```bash
# 1. Verify current ring health
kubectl exec cassandra-0 -- nodetool status
kubectl exec cassandra-0 -- nodetool describecluster

# 2. Take snapshots (strongly recommended)
kubectl exec cassandra-0 -- nodetool snapshot --tag pre-upgrade

# 3. Check replication factor is appropriate
kubectl exec cassandra-0 -- nodetool getendpoints KEYSPACE TABLE_NAME

# 4. Ensure no repairs running
kubectl exec cassandra-0 -- nodetool compactionstats
```

## Execute the upgrade

```bash
# Initiate blue-green upgrade
gcloud container node-pools upgrade CASSANDRA_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION

# Monitor progress
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=CASSANDRA_POOL_NAME'
```

## Validation checklist

```markdown
- [ ] All 9 green nodes are Ready
- [ ] Cassandra ring shows 9 nodes UP/NORMAL: `kubectl exec cassandra-0 -- nodetool status`
- [ ] No streaming operations: `kubectl exec cassandra-0 -- nodetool netstats`
- [ ] Data consistency check: `kubectl exec cassandra-0 -- nodetool repair -pr`
- [ ] Application connectivity test
- [ ] Local SSD mount points correct on new nodes
```

## Resource requirements

Blue-green will temporarily double your node pool size (18 nodes), so ensure you have:
- **Compute quota**: 18 × your machine type
- **Local SSD quota**: 18 × SSD count per node
- **IP addresses**: 18 additional IPs in your subnet

## Timeline expectations

- **Provisioning new pool**: 5-10 minutes
- **Cassandra streaming**: 15-60 minutes (depends on data size)
- **Soak period**: 5 minutes (configurable)
- **Blue pool cleanup**: 5 minutes
- **Total**: ~30-80 minutes

The blue-green approach gives you the safest path for Cassandra with built-in rollback capability and no risk of data loss from local SSD ephemeral storage.