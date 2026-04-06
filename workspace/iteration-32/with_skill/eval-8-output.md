For your Cassandra ring with local SSDs, I **strongly recommend blue-green upgrade**. Here's why and how to configure it:

## Why Blue-Green for Cassandra + Local SSDs

**Critical issue with surge:** Surge upgrades drain nodes, which **destroys local SSD data**. For Cassandra, this means:
- Data loss on each node as it's drained
- Massive rebalancing storms as the ring rebuilds data
- Risk of quorum loss during concurrent node drains
- Potential for split-brain scenarios

**Blue-green advantages:**
- Preserves the existing Cassandra ring during upgrade
- Allows proper `nodetool decommission` workflow
- Quick rollback path if issues arise
- Controlled, validated migration

## Recommended Blue-Green Configuration

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
- `--node-pool-soak-duration=7200s` (2 hours): Time to validate the new ring before deleting old nodes
- `batch-node-count=1`: Migrate one Cassandra node at a time (conservative)
- `batch-soak-duration=300s` (5 minutes): Wait between each node migration

## Pre-Upgrade Preparation

```bash
# 1. Configure PDB to protect quorum (allow only 1 node down)
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-pdb
  namespace: CASSANDRA_NAMESPACE
spec:
  minAvailable: 2  # Maintains quorum of 2 out of 3 replicas
  selector:
    matchLabels:
      app: cassandra
EOF

# 2. Take a cluster-wide snapshot
kubectl exec -it cassandra-0 -n CASSANDRA_NAMESPACE -- nodetool snapshot

# 3. Verify cluster health before upgrade
kubectl exec -it cassandra-0 -n CASSANDRA_NAMESPACE -- nodetool status
```

## Cassandra-Specific Migration Workflow

During the blue-green upgrade, follow this workflow for each Cassandra node:

```bash
# For each node being migrated:
# 1. Decommission the node gracefully
kubectl exec -it CASSANDRA_POD -n CASSANDRA_NAMESPACE -- nodetool decommission

# 2. Wait for decommission to complete (status shows "Left")
kubectl exec -it CASSANDRA_POD -n CASSANDRA_NAMESPACE -- nodetool netstats

# 3. Allow the pod to be evicted to the new (green) node
# 4. New pod starts and automatically rejoins the ring
# 5. Verify ring health
kubectl exec -it CASSANDRA_POD -n CASSANDRA_NAMESPACE -- nodetool status
```

## Alternative: Manual Blue-Green (More Control)

If you need maximum control over the Cassandra migration timing:

```bash
# 1. Create new node pool with target version
gcloud container node-pools create cassandra-pool-new \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version TARGET_VERSION \
    --num-nodes 9 \
    --machine-type MACHINE_TYPE \
    --local-ssd-count 1

# 2. Update Cassandra StatefulSet to prefer new nodes
kubectl patch statefulset cassandra -n CASSANDRA_NAMESPACE \
    -p '{"spec":{"template":{"spec":{"nodeSelector":{"cloud.google.com/gke-nodepool":"cassandra-pool-new"}}}}}'

# 3. Cordon old pool
kubectl cordon -l cloud.google.com/gke-nodepool=cassandra-pool-old

# 4. Delete pods one by one with proper decommissioning
for i in {0..8}; do
  kubectl exec cassandra-$i -n CASSANDRA_NAMESPACE -- nodetool decommission
  kubectl delete pod cassandra-$i -n CASSANDRA_NAMESPACE
  # Wait for pod to reschedule and rejoin ring
  kubectl wait --for=condition=Ready pod/cassandra-$i -n CASSANDRA_NAMESPACE --timeout=600s
  kubectl exec cassandra-$i -n CASSANDRA_NAMESPACE -- nodetool status
done

# 5. Delete old node pool after validation
gcloud container node-pools delete cassandra-pool-old --cluster CLUSTER_NAME --zone ZONE
```

## Cost Consideration

Blue-green temporarily doubles your node pool resources (18 nodes instead of 9). Budget for ~2-4 hours of 2x cost during the upgrade window.

## Key Monitoring During Upgrade

```bash
# Monitor ring health
kubectl exec -it cassandra-0 -n CASSANDRA_NAMESPACE -- nodetool status

# Check for data streaming (should be minimal with proper decommission)
kubectl exec -it cassandra-0 -n CASSANDRA_NAMESPACE -- nodetool netstats

# Verify no stuck repairs
kubectl exec -it cassandra-0 -n CASSANDRA_NAMESPACE -- nodetool compactionstats
```

**Bottom line:** Blue-green is essential for Cassandra with local SSDs. The 2x temporary cost is far preferable to data loss and ring corruption from surge upgrades.