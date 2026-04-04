For your Cassandra ring with local SSDs, I **strongly recommend blue-green upgrade**. Here's why surge is problematic for your setup and how to configure blue-green properly.

## Why Blue-Green for Cassandra + Local SSDs

**Surge upgrade problems:**
- **Data loss risk**: Surge drains the old node, destroying local SSD data. Even with proper decommissioning, this creates unnecessary risk.
- **Rebalancing storms**: If nodes are drained without proper Cassandra decommissioning, the cluster experiences data rebalancing chaos.
- **Quorum disruption**: With only 9 nodes, losing even 1-2 nodes during surge can impact read/write consistency.

**Blue-green advantages:**
- **Data preservation**: Old nodes stay available during the soak period, giving time for proper Cassandra decommissioning.
- **Controlled migration**: You can decommission Cassandra nodes gracefully before deleting the blue pool.
- **Quick rollback**: If issues arise, uncordon the blue pool and rollback fast.

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
- `--node-pool-soak-duration=7200s` (2 hours): Time to validate and decommission Cassandra nodes before deleting blue pool
- `batch-node-count=1`: Drain one node at a time for maximum safety
- `batch-soak-duration=300s` (5 minutes): Wait between each node drain

## Essential PDB Configuration

Set up a PDB to protect Cassandra quorum:

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-pdb
  namespace: cassandra-namespace
spec:
  minAvailable: 7  # Allow max 2 nodes down simultaneously
  selector:
    matchLabels:
      app: cassandra
```

```bash
kubectl apply -f cassandra-pdb.yaml
```

## Cassandra-Specific Upgrade Workflow

**During the soak period (critical steps):**

1. **Monitor cluster health:**
```bash
# Check ring status
kubectl exec -it cassandra-0 -n cassandra-namespace -- nodetool status

# Verify no nodes in "Down" or "Unreachable" state
kubectl exec -it cassandra-0 -n cassandra-namespace -- nodetool describecluster
```

2. **Decommission nodes on blue pool (old nodes):**
```bash
# For each Cassandra pod on blue pool nodes
kubectl exec -it CASSANDRA_POD -n cassandra-namespace -- nodetool decommission

# Wait for status "Left" before proceeding to next node
kubectl exec -it cassandra-0 -n cassandra-namespace -- nodetool status | grep Left
```

3. **Complete upgrade after decommissioning:**
```bash
# Only after all blue pool Cassandra nodes show "Left" status
gcloud container node-pools upgrade cassandra-pool \
    --cluster YOUR_CLUSTER_NAME \
    --zone YOUR_ZONE \
    --complete-upgrade
```

## Capacity Planning

Blue-green requires **2x your current node pool size** during the upgrade:
- Current: 9 nodes
- During upgrade: Up to 18 nodes temporarily
- Ensure you have quota for 9 additional nodes of your machine type

Check quota:
```bash
gcloud compute project-info describe --format="table(quotas.metric,quotas.limit,quotas.usage)"
```

## Alternative If Quota Is Insufficient

If you can't get 2x capacity, use **autoscaled blue-green** instead:

```bash
gcloud container node-pools update cassandra-pool \
    --cluster YOUR_CLUSTER_NAME \
    --zone YOUR_ZONE \
    --enable-autoscaling \
    --total-min-nodes 9 --total-max-nodes 18 \
    --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.33,blue-green-full-batch-timeout=7200s
```

This scales down the blue pool as green pool scales up, reducing peak capacity requirements while still allowing proper Cassandra decommissioning.

## Pre-Upgrade Checklist

```
- [ ] PDB configured with minAvailable: 7
- [ ] Quota confirmed for 9 additional nodes
- [ ] Cassandra ring healthy (all nodes "Up Normal")
- [ ] Backup taken via `nodetool snapshot`
- [ ] Blue-green strategy configured with 2-hour soak duration
- [ ] Maintenance window set for low-traffic period
- [ ] Team available to monitor decommissioning during soak period
```

The key is using that 2-hour soak period to properly decommission Cassandra nodes before the blue pool gets deleted. This approach respects Cassandra's distributed nature while protecting your local SSD data.