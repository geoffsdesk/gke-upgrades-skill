For your Cassandra ring with local SSDs, I **strongly recommend blue-green upgrade** over surge. Here's why and how to configure it:

## Why Blue-Green for Cassandra

**Cassandra + local SSDs = high risk with surge:**
- **Data locality**: Cassandra stores data on local SSDs. When surge upgrade drains a node, that data is temporarily unavailable until replicas can handle the load
- **Rebalancing overhead**: Each node drain triggers cluster rebalancing, which is expensive with a 9-node ring
- **Cascade risk**: If multiple nodes drain simultaneously (even with conservative surge settings), you could lose quorum
- **Local SSD recreation**: New nodes get fresh local SSDs - no data migration, relying entirely on Cassandra's replication

**Blue-green advantages:**
- **Zero capacity loss**: Old nodes stay available while new nodes join
- **Controlled data migration**: New Cassandra nodes can join the ring and receive data before old nodes leave
- **Easy rollback**: If issues arise, old nodes are still there and can quickly rejoin
- **Validation period**: Soak time to verify the new nodes are healthy before committing

## Blue-Green Configuration

```bash
# Configure the node pool for blue-green upgrade
gcloud container node-pools update cassandra-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-blue-green-upgrade \
  --blue-green-upgrade-policy-batch-soak-duration=600s \
  --blue-green-upgrade-policy-batch-node-count=3 \
  --blue-green-upgrade-policy-batch-percent=33

# Initiate the upgrade
gcloud container node-pools upgrade cassandra-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

## Configuration Explanation

- **Batch size**: `batch-node-count=3` upgrades 3 nodes at a time (33% of your ring)
- **Soak duration**: `600s` (10 minutes) between batches - enough time to verify Cassandra health
- **Process**: Creates 3 new nodes → waits 10min → creates 3 more → waits 10min → creates final 3

## Cassandra-Specific Preparation

**Before the upgrade:**

```bash
# 1. Verify Cassandra cluster health
kubectl exec -it cassandra-0 -n NAMESPACE -- nodetool status
# Ensure all nodes are UP and NORMAL

# 2. Check replication factor (should be ≥3 for fault tolerance)
kubectl exec -it cassandra-0 -n NAMESPACE -- cqlsh -e "DESCRIBE KEYSPACE your_keyspace;"

# 3. Reduce batch size if needed for extra safety
gcloud container node-pools update cassandra-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --blue-green-upgrade-policy-batch-node-count=1
# This would upgrade one node at a time (safest but slowest)
```

## Quota Requirement

Blue-green temporarily doubles your node pool size. For 9 nodes, you'll need capacity for 18 nodes during upgrade. Verify quota:

```bash
# Check current quota usage
gcloud compute regions describe REGION --format="table(quotas[].metric,quotas[].usage,quotas[].limit)"

# Look for CPUS, SSD_LOCAL_GB quotas
```

## Alternative: Conservative Surge (if quota is limited)

If you can't get quota for blue-green, use **very conservative surge settings**:

```bash
gcloud container node-pools update cassandra-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# This creates one new node, migrates one old node's pods, deletes old node
# Repeat for all 9 nodes sequentially - safest surge approach
```

## Monitoring During Upgrade

```bash
# Watch node status
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=cassandra-pool'

# Monitor Cassandra ring health
watch 'kubectl exec cassandra-0 -n NAMESPACE -- nodetool status'

# Check for any stuck pods
kubectl get pods -n NAMESPACE | grep -v Running
```

## Rollback Plan

If issues arise during blue-green:
1. **Cancel upgrade**: The operation can be stopped, keeping both old and new nodes
2. **Drain new nodes**: Cordon new nodes and let Cassandra rebalance back to old nodes
3. **Remove new pool**: Delete the new nodes once data is back on old nodes

**Recommendation**: Go with blue-green upgrade for your Cassandra workload. The temporary quota cost is worth the safety and control it provides for stateful workloads with local storage.