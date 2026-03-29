Given your Cassandra ring with local SSDs, I **strongly recommend blue-green upgrade**. Here's why and how to configure it:

## Why Blue-Green for Cassandra + Local SSDs

**Critical issue with surge:** Surge upgrades drain nodes, which **destroys local SSD data**. For Cassandra, this means:
- Data loss on each node as it's drained
- Massive rebalancing storms as the ring rebuilds
- Risk of quorum loss during the rebuild process
- Potential data consistency issues

**Blue-green advantages:**
- Old nodes (blue pool) stay running with data intact
- New nodes (green pool) join the ring gradually
- Cassandra can decommission nodes properly before deletion
- Quick rollback path if issues arise

## Configuration Commands

```bash
# Configure blue-green upgrade strategy
gcloud container node-pools update cassandra-pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --strategy=BLUE_GREEN \
    --node-pool-soak-duration=7200s \
    --standard-rollout-policy=batch-node-count=1,batch-soak-duration=600s

# Verify configuration
gcloud container node-pools describe cassandra-pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --format="yaml(upgradeSettings)"
```

**Key parameters:**
- `--node-pool-soak-duration=7200s` (2 hours): Time to validate the new ring before deleting old nodes
- `--batch-node-count=1`: Drain one node at a time (conservative for Cassandra)
- `--batch-soak-duration=600s` (10 minutes): Wait between each node drain

## Pre-Upgrade Cassandra Preparation

```bash
# 1. Check cluster health
kubectl exec -it cassandra-0 -- nodetool status
kubectl exec -it cassandra-0 -- nodetool ring

# 2. Configure PDB (protect quorum - allow max 3 nodes down from 9)
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-pdb
spec:
  minAvailable: 6  # Keeps majority available
  selector:
    matchLabels:
      app: cassandra

# 3. Take a snapshot before upgrade
kubectl exec -it cassandra-0 -- nodetool snapshot --tag pre-upgrade
```

## Blue-Green Upgrade Process

**Phase 1: Create Green Pool**
- New nodes provisioned at target version
- Cassandra pods remain on blue pool (original nodes)

**Phase 2: Cordon Blue Pool**
- Blue nodes marked unschedulable
- Existing pods continue running

**Phase 3: Drain Blue Pool (batches of 1)**
- One Cassandra pod terminated at a time
- Pod reschedules to green pool node
- New pod rejoins ring and rebuilds data
- 10-minute wait between each node

**Phase 4: Soak Period (2 hours)**
- Validate ring health on new nodes
- Check data consistency
- Monitor rebalancing completion

**Phase 5: Delete Blue Pool**
- Old nodes deleted permanently
- **Warning:** This phase force-deletes any remaining pods

## Validation Commands During Soak

```bash
# Monitor ring topology
kubectl exec -it cassandra-0 -- nodetool status

# Check for ongoing repairs/rebuilds
kubectl exec -it cassandra-0 -- nodetool compactionstats

# Verify data consistency
kubectl exec -it cassandra-0 -- nodetool repair --full

# Application-level health check
kubectl exec -it cassandra-0 -- cqlsh -e "SELECT * FROM system.local;"
```

## Important Considerations

**Capacity requirement:** Blue-green needs **2x your current node pool size** during the upgrade. Ensure you have quota for 18 nodes total (9 blue + 9 green).

**Ring rebalancing:** Even with blue-green, Cassandra will rebalance as new nodes join. This is normal but monitor the process.

**Rollback capability:** During soak period, you can rollback by uncordoning the blue pool:
```bash
kubectl uncordon -l cloud.google.com/gke-nodepool=cassandra-pool-old
```

**Extended soak for Cassandra:** Consider extending soak duration for large datasets:
```bash
--node-pool-soak-duration=14400s  # 4 hours for large rings
```

This approach protects your Cassandra data while minimizing disruption to the ring topology. The 2x capacity cost is worth it for the safety of your stateful data.