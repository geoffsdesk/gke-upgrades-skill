For your Cassandra ring with local SSDs, **blue-green upgrade is strongly recommended**. Here's why and how to configure it:

## Why Blue-Green for Cassandra + Local SSDs

**Critical issue with surge upgrades:** Surge upgrades drain nodes, which **destroys local SSD data**. For Cassandra, this means:
- Data loss on the drained node
- Cassandra will need to rebuild/repair that node's data from other replicas
- Potential for data inconsistency during the rebuild process
- Extended cluster instability

**Blue-green advantages for your use case:**
- Preserves local SSD data during the transition
- Allows proper Cassandra decommissioning workflow
- Provides fast rollback path if issues arise
- Maintains cluster stability throughout the upgrade

## Recommended Configuration

```bash
# Configure blue-green upgrade strategy
gcloud container node-pools update CASSANDRA_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --strategy=BLUE_GREEN \
    --node-pool-soak-duration=7200s \
    --standard-rollout-policy=batch-node-count=1,batch-soak-duration=300s
```

**Key parameters explained:**
- `--node-pool-soak-duration=7200s` (2 hours): Gives time to validate Cassandra ring health before deleting blue nodes
- `batch-node-count=1`: Processes one node at a time (conservative for stateful workloads)
- `batch-soak-duration=300s` (5 minutes): Wait between each node to allow Cassandra to stabilize

## Pre-Upgrade Cassandra Preparation

```bash
# 1. Configure PDB to protect quorum (assuming RF=3)
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-pdb
  namespace: CASSANDRA_NAMESPACE
spec:
  selector:
    matchLabels:
      app: cassandra
  minAvailable: 2  # Maintains quorum during drain
EOF

# 2. Take application-level backup
kubectl exec -it cassandra-0 -n CASSANDRA_NAMESPACE -- nodetool snapshot

# 3. Verify cluster health before upgrade
kubectl exec -it cassandra-0 -n CASSANDRA_NAMESPACE -- nodetool status
```

## Upgrade Execution

```bash
# Start the blue-green upgrade
gcloud container node-pools upgrade CASSANDRA_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version TARGET_VERSION

# Monitor progress
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=CASSANDRA_POOL_NAME'
```

## Validation During Soak Period

During the 2-hour soak period, validate Cassandra health:

```bash
# Check ring status
kubectl exec -it cassandra-0 -n CASSANDRA_NAMESPACE -- nodetool status

# Verify no nodes in UJ (Up/Joining) or DN (Down/Normal) state
# All nodes should show UN (Up/Normal)

# Check for streaming operations
kubectl exec -it cassandra-0 -n CASSANDRA_NAMESPACE -- nodetool netstats

# Test read/write operations
# Run your application health checks
```

## Important Cassandra-Specific Considerations

**Decommissioning workflow:** With blue-green, you have the luxury of proper decommissioning:
1. Blue pool gets cordoned (no new pods scheduled)
2. Existing Cassandra pods continue running on blue nodes
3. Green pool scales up with new Cassandra pods
4. During the soak period, you can manually decommission blue nodes if needed:
   ```bash
   kubectl exec -it CASSANDRA_POD -- nodetool decommission
   ```

**Ring topology:** Verify that new Cassandra nodes join the ring correctly and that token distribution remains balanced.

**Replication factor consideration:** With RF=3 and 9 nodes, you have good fault tolerance. The PDB setting of `minAvailable: 2` ensures you never lose quorum during the upgrade.

## If Blue-Green Isn't Possible (Quota Constraints)

If you lack quota for 2x node pool size, you'll need a **manual blue-green approach**:

```bash
# 1. Create new pool at target version
gcloud container node-pools create cassandra-new \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --node-version TARGET_VERSION \
    --num-nodes 9 \
    --machine-type MACHINE_TYPE \
    --local-ssd-count 1

# 2. Scale Cassandra StatefulSet to use both pools temporarily
# 3. Validate ring health with 18 nodes
# 4. Decommission old nodes properly
# 5. Delete old pool
```

## Summary

For Cassandra with local SSDs, blue-green is the only safe upgrade strategy. The 2x resource cost is worth it to avoid data loss and cluster instability. The configuration above gives you proper validation time and conservative batching to maintain your ring's health throughout the upgrade process.