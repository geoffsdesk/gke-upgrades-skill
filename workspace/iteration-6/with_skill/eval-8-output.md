For a Cassandra ring with local SSDs, I recommend **surge upgrade** with conservative settings. Here's why and how to configure it:

## Recommendation: Surge Upgrade

**Why surge over blue-green for Cassandra:**
- **Cassandra handles node failures gracefully** — it's designed for nodes to come and go. A properly configured ring can tolerate losing nodes during upgrades.
- **Local SSD data is ephemeral anyway** — you can't preserve local SSD data during upgrades regardless of strategy. Cassandra must rebuild data on new nodes from replicas.
- **Cost efficiency** — surge only creates replacement nodes as needed, while blue-green would double your entire node pool temporarily.
- **Simpler orchestration** — no manual workload migration between pools.

**Blue-green would be overkill** unless you need instant rollback capability or have an extremely fragile Cassandra configuration.

## Configuration

```bash
# Configure conservative surge settings for your Cassandra node pool
gcloud container node-pools update CASSANDRA_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Verify settings
gcloud container node-pools describe CASSANDRA_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --format="value(upgradeSettings)"
```

**Settings explained:**
- `maxSurge=1` — Only one extra node at a time. Minimizes cost while allowing rolling replacement.
- `maxUnavailable=0` — Never remove a node until its replacement is ready. Preserves capacity.

## Pre-upgrade Cassandra preparation

```bash
# 1. Verify cluster health
nodetool status
nodetool describecluster

# 2. Ensure proper replication factor (should be ≥3 for fault tolerance)
cqlsh -e "SELECT keyspace_name, replication FROM system_schema.keyspaces WHERE keyspace_name NOT IN ('system', 'system_schema', 'system_auth', 'system_traces', 'system_distributed');"

# 3. Run repair to ensure data consistency
nodetool repair

# 4. Configure PodDisruptionBudget to protect against too many simultaneous evictions
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-pdb
  namespace: CASSANDRA_NAMESPACE
spec:
  minAvailable: 7  # Allow max 2 nodes down simultaneously (adjust based on RF)
  selector:
    matchLabels:
      app: cassandra  # Match your Cassandra pod labels
EOF
```

## Upgrade process

```bash
# 1. Start the upgrade
gcloud container node-pools upgrade CASSANDRA_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION

# 2. Monitor progress (this will take time - ~15-30min per node)
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=CASSANDRA_NODE_POOL'

# 3. Watch Cassandra ring status during upgrade
watch 'nodetool status'
```

## What happens during the upgrade

1. **Node-by-node replacement:** GKE creates one new node, waits for it to be Ready
2. **Pod eviction:** Cassandra pod gets terminated gracefully (respects `terminationGracePeriodSeconds`)
3. **Data rebuilding:** New Cassandra pod starts on new node with empty local SSD, rebuilds data from ring
4. **Repeat:** Process continues to next node only after current replacement is complete

## Key considerations for Cassandra + local SSD

- **Data rebuilding time:** Each new node must stream data from replicas. With local SSDs this is fast, but still takes time proportional to data size.
- **Network bandwidth:** Multiple nodes rebuilding simultaneously can saturate cross-AZ bandwidth. The `maxSurge=1` setting prevents this.
- **Temporary capacity loss:** During rebuild, new nodes can't serve reads until data streaming completes. Ensure your application can handle reduced capacity.
- **Compaction storms:** New nodes will trigger compaction after data rebuild. Monitor resource usage.

## Rollback strategy

If the upgrade causes issues:

```bash
# 1. Cordon the new nodes to prevent new pods
kubectl cordon NODE_NAME

# 2. Create a new node pool at the previous version
gcloud container node-pools create cassandra-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version PREVIOUS_VERSION \
  --num-nodes 9 \
  --machine-type CURRENT_MACHINE_TYPE \
  --local-ssd-count CURRENT_SSD_COUNT

# 3. Manually migrate Cassandra pods to the rollback pool
# 4. Delete the problematic upgraded pool once data is rebuilt
```

## Alternative: If you prefer blue-green

If you specifically want blue-green (e.g., for instant rollback), here's the approach:

```bash
# 1. Create parallel node pool
gcloud container node-pools create cassandra-new \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION \
  --num-nodes 9 \
  --machine-type CURRENT_MACHINE_TYPE \
  --local-ssd-count CURRENT_SSD_COUNT

# 2. Scale Cassandra StatefulSet to 18 replicas (spans both pools)
kubectl scale statefulset cassandra --replicas=18 -n CASSANDRA_NAMESPACE

# 3. Wait for new pods to rebuild data, then cordon old nodes
# 4. Scale back to 9 replicas (only on new pool)
# 5. Delete old node pool
```

Blue-green requires double the compute cost during migration and more manual orchestration, but gives you instant rollback capability.

**Bottom line:** Stick with surge upgrade unless you have specific requirements for blue-green. Cassandra is resilient enough to handle rolling upgrades gracefully.