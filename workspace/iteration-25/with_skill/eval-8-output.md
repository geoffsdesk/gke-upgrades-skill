For your Cassandra ring with local SSDs, **you must use blue-green upgrade**. Here's why surge is not viable and how to configure blue-green properly:

## Why Blue-Green is Required

**Surge upgrade will cause data loss** for your Cassandra cluster:
- Surge upgrades **drain nodes first**, which destroys local SSD data
- Cassandra stores data on local SSDs that cannot be migrated between nodes
- Even with proper decommissioning, surge's drain-first approach risks data loss

**Blue-green upgrade preserves your data** by:
- Keeping the old (blue) nodes available while new (green) nodes are provisioned
- Allowing controlled decommissioning before the old nodes are deleted
- Providing a rollback path if issues arise during the upgrade

## Blue-Green Configuration for Cassandra

```bash
# Configure blue-green upgrade strategy
gcloud container node-pools update CASSANDRA_POOL_NAME \
    --cluster CLUSTER_NAME \
    --region REGION \
    --strategy=BLUE_GREEN \
    --node-pool-soak-duration=7200s \
    --standard-rollout-policy=batch-node-count=1,batch-soak-duration=300s
```

**Key parameters explained:**
- `--node-pool-soak-duration=7200s` (2 hours): Time to validate the new Cassandra ring before deleting old nodes
- `--batch-node-count=1`: Drain one node at a time (conservative for Cassandra)
- `--batch-soak-duration=300s` (5 minutes): Wait between each node drain

## Cassandra-Specific PDB Configuration

**Critical:** Configure PDBs to protect your Cassandra ring during the upgrade:

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-pdb
  namespace: cassandra-namespace
spec:
  minAvailable: 6  # Ensures 6 of 9 nodes always available (maintains quorum)
  selector:
    matchLabels:
      app: cassandra
```

Apply before upgrading:
```bash
kubectl apply -f cassandra-pdb.yaml
```

## Upgrade Workflow with Proper Decommissioning

1. **Pre-upgrade preparation:**
   ```bash
   # Take Cassandra snapshots
   kubectl exec -it cassandra-0 -- nodetool snapshot
   
   # Verify ring health
   kubectl exec -it cassandra-0 -- nodetool status
   ```

2. **Start the upgrade:**
   ```bash
   gcloud container node-pools upgrade CASSANDRA_POOL_NAME \
       --cluster CLUSTER_NAME \
       --region REGION \
       --cluster-version TARGET_VERSION
   ```

3. **During the soak period, validate the new ring:**
   ```bash
   # Check all nodes are Up and Normal
   kubectl exec -it cassandra-0 -- nodetool status
   
   # Verify data consistency
   kubectl exec -it cassandra-0 -- nodetool repair
   
   # Test application connectivity
   ```

4. **Complete or rollback:**
   ```bash
   # If validation passes, complete the upgrade
   gcloud container node-pools complete-upgrade CASSANDRA_POOL_NAME \
       --cluster CLUSTER_NAME \
       --region REGION
   
   # If issues found, rollback (uncordons blue pool)
   gcloud container node-pools rollback-upgrade CASSANDRA_POOL_NAME \
       --cluster CLUSTER_NAME \
       --region REGION
   ```

## Resource Requirements

**Important:** Blue-green temporarily doubles your node pool size:
- **Current:** 9 Cassandra nodes
- **During upgrade:** Up to 18 nodes (9 blue + 9 green)
- **Quota check:** Verify you have quota for 18 nodes of your machine type

```bash
# Check current quota usage
gcloud compute regions describe REGION --format="table(quotas[].metric,quotas[].usage,quotas[].limit)"
```

## Alternative: Manual Blue-Green (if quota constrained)

If you lack quota for 18 nodes, consider a manual approach:

1. Create 3 new nodes (1/3 of ring)
2. Let Cassandra auto-bootstrap and rebalance
3. Decommission 3 old nodes: `nodetool decommission`
4. Repeat in 3-node batches

This keeps total nodes closer to 12 (9 + 3) rather than 18.

## Timeline Expectations

- **Blue pool creation:** 5-10 minutes
- **Pod migration:** 15-30 minutes (depends on Cassandra bootstrap time)
- **Soak period:** 2 hours (configurable)
- **Blue pool deletion:** 5 minutes
- **Total:** ~3-4 hours for the complete blue-green cycle

Blue-green is the only safe approach for your Cassandra + local SSD setup. The extra time and resources are essential to prevent data loss.