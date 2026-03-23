# GKE Node Pool Upgrade Strategy: Stateful Cassandra Workload

## Recommendation: Surge Upgrade (Conservative Configuration)

For your Cassandra ring with local SSDs, I recommend **surge upgrade** with conservative settings rather than blue-green. Here's why:

### Why Surge Over Blue-Green for Cassandra

**Cassandra-specific considerations:**
- **Data locality**: Cassandra with local SSDs means data is tied to specific nodes
- **Ring topology**: Cassandra handles node replacement well through its distributed architecture
- **Replication factor**: With RF=3 (typical), you can safely lose 1-2 nodes temporarily
- **Local SSD constraint**: Blue-green would require recreating all local SSD data from scratch

**Blue-green downsides for your use case:**
- Requires 2x compute quota (18 nodes temporarily)
- All local SSD data must be rebuilt from replicas during green pool provisioning
- Extended data transfer time for TB-scale datasets
- Higher network and disk I/O during the rebuild phase

## Recommended Configuration

```bash
# Configure conservative surge settings for Cassandra pool
gcloud container node-pools update cassandra-pool \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Verify configuration
gcloud container node-pools describe cassandra-pool \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --format="value(upgradeSettings.maxSurge,upgradeSettings.maxUnavailable)"
```

**Why these settings:**
- `maxSurge=1`: Only one extra node at a time - minimizes quota usage
- `maxUnavailable=0`: Never lose an existing node until replacement is ready
- **Total impact**: Only 1 node rebuilding data at any given time
- **Cassandra tolerance**: RF=3 easily handles 1 node being rebuilt

## Pre-Upgrade Cassandra Preparation

```bash
# 1. Check cluster health
nodetool status
nodetool describecluster

# 2. Verify replication factor provides adequate redundancy
# Run this on one Cassandra pod:
kubectl exec -it cassandra-0 -- cqlsh -e "DESCRIBE KEYSPACES;"
# Check that your keyspaces have RF >= 3

# 3. Ensure no ongoing repairs or compactions
kubectl exec -it cassandra-0 -- nodetool compactionstats
kubectl exec -it cassandra-0 -- nodetool netstats

# 4. Set up PodDisruptionBudget (if not already configured)
cat <<EOF | kubectl apply -f -
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-pdb
  namespace: YOUR_NAMESPACE
spec:
  minAvailable: 7  # Allow 2 nodes down simultaneously (9 total - 2 = 7)
  selector:
    matchLabels:
      app: cassandra
EOF
```

## Upgrade Execution

```bash
# 1. Initiate node pool upgrade
gcloud container node-pools upgrade cassandra-pool \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --cluster-version TARGET_GKE_VERSION

# 2. Monitor upgrade progress
watch 'kubectl get nodes -o wide | grep -E "cassandra-pool|Ready"'

# 3. Monitor Cassandra ring health during upgrade
# Run this periodically during the upgrade:
kubectl exec -it cassandra-0 -- nodetool status
```

## Expected Upgrade Behavior

**Timeline:** ~2-3 hours for 9 nodes (20-30 min per node including data rebuild)

**Per-node process:**
1. New node provisioned with local SSDs
2. Cassandra pod scheduled on new node
3. Pod starts and joins ring as a new node
4. Data streams from replicas to rebuild local dataset
5. Old node cordoned and drained
6. Old node terminated
7. Process repeats for next node

**Cassandra ring impact:**
- Brief increase to 10 nodes during each replacement
- 1 node rebuilding data at any time
- Ring remains fully available (RF=3 protects against 1 node rebuilding)

## Alternative: If You Must Use Blue-Green

If you have specific requirements that necessitate blue-green (e.g., zero data rebuilding time), here's the configuration:

```bash
# Enable blue-green upgrade
gcloud container node-pools update cassandra-pool \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --enable-blue-green-upgrade
```

**Blue-green process for Cassandra:**
1. Green pool (9 new nodes) provisioned
2. All 9 Cassandra pods start on green pool
3. All 9 pods rebuild data from replicas simultaneously
4. Ring temporarily has 18 nodes during transition
5. Blue pool cordoned and drained
6. Blue pool deleted

**Requires:** 2x compute quota, significantly longer data rebuild time

## Monitoring During Upgrade

```bash
# Cassandra cluster health
kubectl exec -it cassandra-0 -- nodetool status | grep -E "UN|DN|UJ"

# Node upgrade progress
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,STATUS:.status.conditions[?(@.type==\"Ready\")].status

# Pod disruption status
kubectl get pdb cassandra-pdb -o yaml

# Data streaming progress (during rebuild)
kubectl exec -it cassandra-0 -- nodetool netstats | grep -A 10 "Pool Name"
```

The surge upgrade approach respects Cassandra's architecture while minimizing resource usage and risk. The conservative `maxSurge=1` setting ensures only one node rebuilds data at a time, which is well within Cassandra's fault tolerance capabilities.