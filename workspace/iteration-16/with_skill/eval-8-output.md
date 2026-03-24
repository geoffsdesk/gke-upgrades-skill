Based on your stateful Cassandra workload with local SSDs, **I strongly recommend blue-green upgrade** over surge. Here's why and how to configure it:

## Why Blue-Green for Cassandra + Local SSDs

**Local SSD data loss with surge:** Surge upgrades drain nodes, which **destroys all local SSD data**. For Cassandra, this means:
- Each node loses its data during drain
- Cassandra must rebuild/restream data from other replicas
- With a 9-node ring, losing nodes sequentially creates sustained rebuild pressure
- Risk of cascading failures if multiple nodes rebuild simultaneously

**Blue-green preserves stability:** 
- Old nodes remain available during the entire upgrade
- Cassandra ring stays fully intact until cutover
- Quick rollback path if issues arise
- More predictable for distributed databases

## Configuration Commands

```bash
# Configure blue-green upgrade strategy
gcloud container node-pools update CASSANDRA_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --strategy=BLUE_GREEN \
    --node-pool-soak-duration=3600s \
    --standard-rollout-policy=batch-node-count=1,batch-soak-duration=300s

# Verify configuration
gcloud container node-pools describe CASSANDRA_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --format="yaml(upgradeSettings)"
```

## Blue-Green Parameters Explained

- **`--node-pool-soak-duration=3600s`**: 1 hour soak time after all nodes drain to validate Cassandra ring health before deleting old nodes
- **`batch-node-count=1`**: Drain one node at a time (conservative for Cassandra)
- **`batch-soak-duration=300s`**: 5 minutes between each node drain to let Cassandra rebalance

## Pre-Upgrade: Configure PDBs for Cassandra

```bash
# Create PDB to protect Cassandra quorum (allows max 3 nodes down in 9-node ring)
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-pdb
  namespace: cassandra-namespace
spec:
  minAvailable: 6
  selector:
    matchLabels:
      app: cassandra
EOF
```

## Cost Consideration

Blue-green **temporarily doubles your node pool size** during upgrade. For a 9-node Cassandra pool, you'll run 18 nodes during the upgrade window. Budget for this extra cost (typically 2-4 hours total).

If cost is prohibitive, consider **autoscaled blue-green** instead:

```bash
# Alternative: Autoscaled blue-green (cost-efficient)
gcloud container node-pools update CASSANDRA_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --enable-autoscaling \
    --total-min-nodes 9 \
    --total-max-nodes 18 \
    --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.33,blue-green-full-batch-timeout=3600s
```

This scales the green pool gradually while scaling down the blue pool, avoiding 2x cost.

## Upgrade Execution Runbook

```bash
# 1. Pre-flight checks
kubectl get pods -n cassandra-namespace -o wide
nodetool status  # Verify all nodes UN (Up/Normal)

# 2. Trigger upgrade
gcloud container node-pools upgrade CASSANDRA_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version TARGET_VERSION

# 3. Monitor progress (blue-green phases)
# - Create green pool (new nodes)
# - Cordon blue pool (old nodes)
# - Drain blue pool in batches
# - Soak period
# - Delete blue pool

# 4. During soak period, validate Cassandra
kubectl exec -it cassandra-pod-name -n cassandra-namespace -- nodetool status
kubectl exec -it cassandra-pod-name -n cassandra-namespace -- nodetool repair

# 5. Complete upgrade (skip remaining soak if healthy)
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE
# If validation passes, complete early:
# gcloud container node-pools complete-upgrade CASSANDRA_POOL_NAME --cluster CLUSTER_NAME --zone ZONE
```

## Rollback Plan

If issues arise during soak period:

```bash
# Rollback to blue pool (uncordon old nodes)
gcloud container node-pools rollback-upgrade CASSANDRA_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE

# Verify Cassandra ring health
kubectl exec -it cassandra-pod-name -n cassandra-namespace -- nodetool status
```

**Bottom line:** For Cassandra with local SSDs, blue-green is the only safe upgrade strategy. The temporary cost increase is worth avoiding data loss and ring instability.