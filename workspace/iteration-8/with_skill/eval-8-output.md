# Node Pool Upgrade Strategy for Cassandra Cluster

Given your stateful Cassandra workload with local SSDs, I recommend **surge upgrade with conservative settings** over blue-green. Here's why and how to configure it:

## Recommendation: Surge Upgrade

**Why surge is better for your Cassandra setup:**

1. **Cost efficiency** - Blue-green would require temporarily doubling your node pool (18 nodes instead of 9), which is expensive for large instances with local SSDs
2. **Local SSD complexity** - Blue-green creates entirely new nodes, meaning you'd need to rebuild/restore data on all new SSDs, while surge preserves the Cassandra ring structure better through rolling updates  
3. **Cassandra fault tolerance** - Your 9-node ring can handle individual node failures during rolling updates, which is exactly what surge provides
4. **Simpler data migration** - Surge allows Cassandra's native replication to handle data as nodes are replaced one-by-one

## Configuration Commands

```bash
# Configure conservative surge settings for your Cassandra pool
gcloud container node-pools update CASSANDRA_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# This creates 1 new node before draining any existing nodes
# Total temporary nodes: 10 (9 existing + 1 surge)
```

## Pre-Upgrade Cassandra Preparation

```bash
# 1. Verify Cassandra cluster health
kubectl exec -it cassandra-0 -- nodetool status
# All nodes should show UN (Up Normal)

# 2. Configure PodDisruptionBudget to protect the ring
cat << EOF | kubectl apply -f -
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-pdb
  namespace: cassandra-namespace
spec:
  selector:
    matchLabels:
      app: cassandra
  maxUnavailable: 1  # Only allow 1 pod down at a time
EOF

# 3. Increase termination grace period for clean shutdown
# In your StatefulSet spec:
# terminationGracePeriodSeconds: 300  # 5 minutes for clean shutdown
```

## Upgrade Process

```bash
# 1. Initiate the node pool upgrade
gcloud container node-pools upgrade CASSANDRA_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION

# 2. Monitor progress - watch for orderly node replacement
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=CASSANDRA_NODE_POOL -o wide'

# 3. Monitor Cassandra ring health during upgrade
watch 'kubectl exec -it cassandra-0 -- nodetool status'
```

## Why Not Blue-Green for Your Case

Blue-green would require:
- **18 nodes temporarily** (double your current 9)
- **Complete data rebuild** on new local SSDs 
- **Complex coordination** to migrate the entire ring at once
- **Higher risk** - if the new ring has issues, rollback is complex

With surge, Cassandra handles the rolling replacement naturally through its replication, and you only need 1 extra node temporarily.

## Monitoring During Upgrade

```bash
# Check that only 1 Cassandra pod is down at a time
kubectl get pods -l app=cassandra

# Verify ring stays healthy (should always show 8-9 nodes UP)
kubectl exec -it cassandra-0 -- nodetool status

# Monitor PDB - should show 1 allowed disruption
kubectl get pdb cassandra-pdb
```

The conservative surge approach works with Cassandra's natural resilience while minimizing cost and complexity. The PDB ensures GKE respects your 1-node-at-a-time requirement during the rolling upgrade.