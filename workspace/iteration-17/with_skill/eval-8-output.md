Based on your Cassandra ring with local SSDs, I **strongly recommend blue-green upgrade**. Here's why and how to configure it:

## Why Blue-Green for Cassandra + Local SSDs

**Critical issue with surge:** Surge upgrades drain nodes, which **destroys local SSD data**. For Cassandra, this means:
- Data loss on the drained node
- Cassandra must rebuild data from other replicas
- Potential rebalancing storms across the ring
- Risk of quorum loss if multiple nodes drain simultaneously

**Blue-green advantages:**
- Old nodes (blue pool) remain available with intact local SSD data
- New nodes (green pool) are provisioned fresh
- You control the migration timing through the soak period
- Rollback is instant (uncordon blue pool)
- Proper time for Cassandra decommission workflow

## Recommended Blue-Green Configuration

```bash
# Configure blue-green with conservative batch settings
gcloud container node-pools update CASSANDRA_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --strategy=BLUE_GREEN \
    --node-pool-soak-duration=7200s \
    --standard-rollout-policy=batch-node-count=1,batch-soak-duration=600s
```

**Configuration explained:**
- `batch-node-count=1`: Migrate one Cassandra node at a time (conservative)
- `batch-soak-duration=600s`: 10 minutes between nodes for ring stabilization
- `node-pool-soak-duration=7200s`: 2-hour final soak to validate ring health

## Cassandra-Specific Migration Workflow

During the blue-green upgrade, follow this sequence for each node:

1. **Cordon the blue node** (GKE does this automatically)
2. **Decommission the Cassandra node:**
   ```bash
   kubectl exec -it cassandra-pod-name -- nodetool decommission
   ```
3. **Wait for decommission to complete:**
   ```bash
   kubectl exec -it cassandra-pod-name -- nodetool status
   # Wait for status to show "Left"
   ```
4. **Allow pod to drain** (GKE handles this)
5. **New pod starts on green pool** and joins the ring automatically

## Pre-Upgrade Checklist for Your Cassandra Pool

```markdown
Cassandra Blue-Green Pre-Upgrade Checklist
- [ ] Cassandra ring is healthy: `nodetool status` shows all nodes UN (Up/Normal)
- [ ] Replication factor ≥ 3 to survive single node loss
- [ ] No ongoing repairs or compactions: `nodetool compactionstats`
- [ ] Snapshot taken: `nodetool snapshot`
- [ ] PDB configured: `minAvailable: 2` (allows 1 node to decommission)
- [ ] Sufficient quota for 2x node pool size during upgrade
- [ ] Local SSD reclaim policy verified (should be Delete for ephemeral data)
```

## Why Not Surge (Don't Use This)

For comparison, surge would look like this but **should NOT be used**:
```bash
# DON'T USE - This destroys local SSD data
gcloud container node-pools update CASSANDRA_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 1 \
    --max-unavailable-upgrade 0
```

## Resource Planning

**Quota requirement:** You'll need temporary capacity for 18 nodes (9 blue + 9 green) during the upgrade. Ensure you have:
- 18x your machine type quota
- 18x local SSD quota
- Network quota for additional nodes

## Monitoring During Upgrade

```bash
# Watch ring status
kubectl exec -it cassandra-pod-name -- watch nodetool status

# Monitor blue-green progress
kubectl get nodes -l cloud.google.com/gke-nodepool=CASSANDRA_POOL_NAME -o wide

# Check pod distribution
kubectl get pods -l app=cassandra -o wide
```

The blue-green approach gives you the safety net Cassandra needs while preserving your local SSD data integrity. The 2-hour soak period lets you validate ring health before committing to the new nodes.