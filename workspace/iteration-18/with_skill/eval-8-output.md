For your Cassandra ring with local SSDs, I **strongly recommend blue-green upgrade**. Here's why and how to configure it:

## Why Blue-Green for Cassandra

**Surge upgrade would be problematic:**
- **Local SSD data loss**: Surge drains nodes, destroying local SSD data. Cassandra would need to rebuild/rebalance from other replicas
- **Rebalancing storms**: Each node drain triggers data movement across the ring
- **Quorum risk**: With only 9 nodes, losing multiple nodes during surge batches could impact consistency

**Blue-green advantages:**
- **Data preservation**: Old nodes stay available during transition
- **Controlled decommissioning**: Time to properly decommission Cassandra nodes
- **Quick rollback**: If issues arise, uncordon the blue pool immediately
- **No data rebuilding**: Nodes can be gracefully removed from the ring

## Configuration Commands

```bash
# Configure blue-green upgrade strategy
gcloud container node-pools update CASSANDRA_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --strategy=BLUE_GREEN \
    --node-pool-soak-duration=7200s \
    --standard-rollout-policy=batch-node-count=1,batch-soak-duration=600s

# Set conservative PDB for Cassandra StatefulSet
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-pdb
  namespace: CASSANDRA_NAMESPACE
spec:
  minAvailable: 7  # Allows max 2 nodes down simultaneously
  selector:
    matchLabels:
      app: cassandra
EOF
```

## Blue-Green Parameters Explained

- **`node-pool-soak-duration=7200s`** (2 hours): Time to validate cluster health after all nodes migrate but before deleting the blue pool
- **`batch-node-count=1`**: Drain one node at a time (conservative for stateful workloads)
- **`batch-soak-duration=600s`** (10 minutes): Wait between each node drain to allow Cassandra rebalancing

## Pre-Upgrade Cassandra Preparation

```bash
# 1. Take snapshot before upgrade
kubectl exec -it cassandra-0 -n CASSANDRA_NAMESPACE -- nodetool snapshot

# 2. Verify ring health
kubectl exec -it cassandra-0 -n CASSANDRA_NAMESPACE -- nodetool status

# 3. Check replication factor allows for temporary node loss
kubectl exec -it cassandra-0 -n CASSANDRA_NAMESPACE -- cqlsh -e "DESCRIBE KEYSPACES;"
```

## Upgrade Execution Process

1. **Create green pool**: GKE creates new nodes with target version
2. **Cordon blue pool**: Existing Cassandra nodes marked unschedulable  
3. **Drain in batches**: One Cassandra pod at a time moves to green pool
4. **Soak period**: 2-hour validation window while both pools exist
5. **Delete blue pool**: After validation, old nodes are removed

## During the Soak Period

Monitor Cassandra health:
```bash
# Check ring status
kubectl exec -it cassandra-0 -n CASSANDRA_NAMESPACE -- nodetool status

# Verify no data streaming (rebalancing)
kubectl exec -it cassandra-0 -n CASSANDRA_NAMESPACE -- nodetool netstats

# Monitor repair status
kubectl exec -it cassandra-0 -n CASSANDRA_NAMESPACE -- nodetool compactionstats
```

## Important Cassandra-Specific Notes

- **Decommissioning**: Cassandra pods should have proper shutdown hooks to decommission gracefully when terminated
- **Local SSD binding**: Verify your StatefulSet has `volumeClaimTemplates` that will bind to local SSDs on the new nodes
- **Seed nodes**: Update seed node configuration if using node-specific addressing
- **Resource requests**: Ensure CPU/memory requests match local SSD machine types

## Rollback Plan

If issues arise during the soak period:
```bash
# Cancel the upgrade and return to blue pool
gcloud container node-pools upgrade CASSANDRA_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cancel

# Uncordon the blue pool if needed
kubectl uncordon -l cloud.google.com/gke-nodepool=CASSANDRA_POOL_NAME
```

This approach gives you maximum safety for your stateful Cassandra workload while providing a clear rollback path if any issues arise during the upgrade process.