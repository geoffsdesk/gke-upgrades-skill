For your Cassandra ring with local SSDs, I **strongly recommend blue-green upgrade**. Here's why and how to configure it:

## Why Blue-Green for Cassandra + Local SSDs

**Critical issue with surge:** Surge upgrades drain nodes, which **destroys local SSD data**. For Cassandra, this means:
- Data loss on each node as it's drained
- Massive rebalancing storms as the ring rebuilds data
- Potential consistency issues during the rebuild process

**Blue-green advantages:**
- Old nodes (blue pool) stay online with data intact
- New nodes (green pool) join the ring and rebuild gracefully  
- Controlled decommissioning process respects Cassandra topology
- Fast rollback path if issues arise

## Configuration Commands

```bash
# Configure blue-green upgrade strategy
gcloud container node-pools update cassandra-pool \
    --cluster YOUR_CLUSTER_NAME \
    --zone YOUR_ZONE \
    --strategy=BLUE_GREEN \
    --node-pool-soak-duration=7200s \
    --standard-rollout-policy=batch-node-count=1,batch-soak-duration=300s
```

**Parameter explanation:**
- `--node-pool-soak-duration=7200s` (2 hours): Time to validate Cassandra ring health before deleting blue pool
- `batch-node-count=1`: Drain one node at a time (conservative for stateful workloads)
- `batch-soak-duration=300s` (5 minutes): Wait between each node drain batch

## Pre-Upgrade Cassandra Preparation

```bash
# 1. Take Cassandra snapshots on all nodes
kubectl exec -it cassandra-0 -- nodetool snapshot

# 2. Configure PDB to protect quorum (assuming RF=3)
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: cassandra
EOF

# 3. Verify ring health before starting
kubectl exec -it cassandra-0 -- nodetool status
# Should show all nodes "UN" (Up/Normal)
```

## Blue-Green Upgrade Process

The upgrade will proceed automatically through these phases:

1. **Create green pool** - New 9-node pool with target version
2. **Cordon blue pool** - Prevents new pods from scheduling on old nodes
3. **Drain blue pool** - Moves Cassandra pods to green pool (1 at a time)
   - Each Cassandra pod will restart on a green node
   - Cassandra will rebuild data from other replicas
4. **Soak period** - 2 hours to validate ring health
5. **Delete blue pool** - Removes old nodes after validation

## During Upgrade: Monitor Cassandra Health

```bash
# Monitor ring status during upgrade
kubectl exec -it cassandra-0 -- nodetool status
# Look for: nodes joining (UJ), leaving (UL), normal (UN)

# Check rebuild progress
kubectl exec -it cassandra-0 -- nodetool netstats

# Verify no data streaming errors
kubectl logs cassandra-0 | grep -i "stream\|rebuild\|bootstrap"
```

## Resource Requirements

Blue-green requires **2x capacity** during upgrade:
- 9 existing nodes (blue pool)
- 9 new nodes (green pool)
- Total: 18 nodes temporarily

Ensure you have sufficient:
- Compute quota
- Local SSD quota (if using local SSD provisioning)
- IP addresses in your subnet

## Rollback Process (if needed)

If issues arise during the soak period:

```bash
# Cancel the upgrade and rollback
gcloud container node-pools rollback cassandra-pool \
    --cluster YOUR_CLUSTER_NAME \
    --zone YOUR_ZONE

# This uncordons the blue pool and cordons the green pool
# Pods will migrate back to the original nodes with intact data
```

## Alternative: Manual Blue-Green (if you need more control)

If you need tighter control over Cassandra decommissioning:

```bash
# 1. Create new node pool manually
gcloud container node-pools create cassandra-pool-v2 \
    --cluster YOUR_CLUSTER_NAME \
    --zone YOUR_ZONE \
    --num-nodes 9 \
    --node-version TARGET_VERSION

# 2. Scale StatefulSet to 18 replicas (spans both pools)
kubectl scale statefulset cassandra --replicas=18

# 3. Wait for new pods to join ring and rebuild
# 4. Decommission old nodes one by one
kubectl exec -it cassandra-0 -- nodetool decommission

# 5. Scale back to 9 replicas and delete old pool
```

## Summary

For Cassandra with local SSDs, **blue-green is the only safe option**. Surge would cause data loss and ring instability. The 2x resource cost is worth it for data safety and the ability to rollback quickly if issues arise.

The soak period gives you time to verify ring health before committing to the new nodes. Would you like me to help you prepare any specific monitoring or validation scripts for your Cassandra upgrade?