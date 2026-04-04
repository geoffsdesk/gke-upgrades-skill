For your Cassandra ring with local SSDs, I **strongly recommend blue-green upgrade**. Here's why surge would be problematic and how to configure blue-green properly.

## Why Blue-Green for Cassandra + Local SSDs

**Surge upgrade risks:**
- **Data loss**: Surge drains the old node, destroying local SSD data. Even with proper decommissioning, the rapid drain→delete cycle increases risk
- **Rebalancing storms**: If nodes are drained faster than Cassandra can gracefully redistribute data, you'll get cascading rebalancing that impacts cluster performance
- **Quorum disruption**: With only 9 nodes, losing multiple nodes simultaneously during surge batches could break quorum

**Blue-green advantages:**
- **Data safety**: Old nodes stay available during the soak period - local SSD data is preserved until you're confident the new ring is healthy
- **Graceful decommissioning**: Gives you time to properly `nodetool decommission` nodes instead of force-draining
- **Fast rollback**: If the new nodes have issues, just uncordon the old pool
- **Validation time**: Soak period lets you verify the new Cassandra ring is healthy before committing

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

**Key parameters explained:**
- `--node-pool-soak-duration=7200s`: 2-hour soak after all batches complete. Use this time to verify Cassandra ring health
- `batch-node-count=1`: Drain one node at a time (conservative for Cassandra)
- `batch-soak-duration=300s`: 5-minute wait between each node - gives Cassandra time to rebalance

## Pre-Upgrade Cassandra Preparation

```bash
# 1. Configure PDB to protect quorum (allow max 1 disruption)
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-pdb
  namespace: YOUR_NAMESPACE
spec:
  selector:
    matchLabels:
      app: cassandra
  minAvailable: 6  # Keeps majority of 9-node ring available
EOF

# 2. Take snapshot before upgrade
kubectl exec -it cassandra-0 -n YOUR_NAMESPACE -- nodetool snapshot

# 3. Verify cluster health
kubectl exec -it cassandra-0 -n YOUR_NAMESPACE -- nodetool status
```

## Blue-Green Upgrade Workflow

**Phase 1 - Green pool creation:** New nodes are created and join the Cassandra ring

**Phase 2 - Blue pool cordon:** Old nodes are cordoned but remain in the ring

**Phase 3 - Drain with decommissioning:** This is where you'll need to intervene:

```bash
# During drain phase, properly decommission each Cassandra node
# (Do this for each node being drained)

# 1. Identify the Cassandra pod on the draining node
kubectl get pods -o wide | grep cassandra | grep NODE_NAME

# 2. Decommission the Cassandra node BEFORE GKE drains it
kubectl exec -it CASSANDRA_POD_NAME -n YOUR_NAMESPACE -- nodetool decommission

# 3. Wait for decommission to complete
kubectl exec -it CASSANDRA_POD_NAME -n YOUR_NAMESPACE -- nodetool netstats

# 4. Verify the node shows as "Left" in the ring
kubectl exec -it cassandra-0 -n YOUR_NAMESPACE -- nodetool status
```

**Phase 4 - Soak period validation:**
```bash
# Verify new ring health during the 2-hour soak
kubectl exec -it cassandra-0 -n YOUR_NAMESPACE -- nodetool status
kubectl exec -it cassandra-0 -n YOUR_NAMESPACE -- nodetool describecluster
kubectl exec -it cassandra-0 -n YOUR_NAMESPACE -- nodetool tpstats

# Check for any errors or warnings
kubectl logs -l app=cassandra -n YOUR_NAMESPACE --tail=100
```

**Phase 5 - Completion:** If validation passes, old pool is deleted. If issues arise, rollback by uncordoning the blue pool.

## Alternative: Manual Blue-Green (If You Need More Control)

If you need even more control over the decommissioning process:

```bash
# 1. Create new node pool manually
gcloud container node-pools create cassandra-pool-new \
    --cluster YOUR_CLUSTER_NAME \
    --zone YOUR_ZONE \
    --machine-type YOUR_MACHINE_TYPE \
    --local-ssd-count=YOUR_SSD_COUNT \
    --num-nodes=9 \
    --node-version=TARGET_VERSION

# 2. Scale Cassandra StatefulSet to 18 replicas (both pools)
kubectl scale statefulset cassandra -n YOUR_NAMESPACE --replicas=18

# 3. Wait for new pods to join ring, then decommission old nodes one by one
# 4. Scale back to 9 replicas on new pool only
# 5. Delete old pool
```

## Recommendation

**Use GKE's native blue-green strategy** with the configuration above. It handles the infrastructure orchestration while giving you the soak period needed for proper Cassandra decommissioning. The 2-hour soak window is sufficient to validate ring health and performance.

The key is to **actively monitor the drain phase** and ensure each Cassandra node is properly decommissioned rather than just drained. This prevents data rebalancing issues and maintains cluster stability throughout the upgrade.