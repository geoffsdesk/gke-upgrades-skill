For your Cassandra ring with local SSDs, I **strongly recommend blue-green upgrade**. Here's why and how to configure it:

## Why Blue-Green for Cassandra + Local SSDs

**Surge upgrade would be problematic:**
- Surge drains nodes immediately, **destroying local SSD data** 
- Cassandra nodes need proper decommissioning (`nodetool decommission`) before removal
- The 1-hour drain timeout isn't sufficient for safe Cassandra decommissioning
- Risk of data loss and rebalancing storms

**Blue-green advantages:**
- Old nodes stay available during the upgrade process
- Extended soak period allows proper Cassandra decommissioning workflow
- Local SSD data preserved until you explicitly confirm the new ring is healthy
- Fast rollback path if issues arise

## Recommended Configuration

```bash
# Configure blue-green upgrade strategy
gcloud container node-pools update CASSANDRA_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --strategy=BLUE_GREEN \
  --node-pool-soak-duration=7200s \
  --standard-rollout-policy=batch-node-count=1,batch-soak-duration=600s
```

**Key parameters:**
- `--node-pool-soak-duration=7200s` (2 hours) - Extended time to validate new Cassandra ring health and decommission old nodes
- `--batch-node-count=1` - Process one node at a time for maximum safety
- `--batch-soak-duration=600s` (10 minutes) - Wait between each node batch

## Pre-Upgrade Steps

1. **Verify cluster health:**
```bash
# Check Cassandra ring status
kubectl exec -it cassandra-0 -- nodetool status
# Ensure all nodes are UP and NORMAL (UN)
```

2. **Configure PDB for quorum protection:**
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-pdb
spec:
  minAvailable: 7  # Maintain majority quorum (7 out of 9)
  selector:
    matchLabels:
      app: cassandra
```

3. **Take application-level backup:**
```bash
# Create snapshot before upgrade
kubectl exec -it cassandra-0 -- nodetool snapshot
```

## Blue-Green Upgrade Workflow

When you trigger the upgrade, here's what happens:

1. **Create phase:** GKE provisions 9 new nodes (green pool) with target version
2. **Cordon phase:** Old nodes (blue pool) marked unschedulable  
3. **Drain phase:** Pods gradually moved from blue to green nodes (1 at a time)
4. **Soak phase:** 2-hour validation period with both pools running

## During the Soak Period (Critical Steps)

This is when you'll perform the Cassandra-specific operations:

1. **Monitor new ring formation:**
```bash
# Check that new Cassandra pods are joining the ring
kubectl exec -it cassandra-0 -- nodetool status
# Look for new nodes appearing as UP/JOINING then UP/NORMAL
```

2. **Decommission old nodes safely:**
```bash
# For each old Cassandra node, decommission before the blue pool is deleted
kubectl exec -it OLD_CASSANDRA_POD -- nodetool decommission
# Wait for status to show "Left" before proceeding to next node
```

3. **Validate cluster health:**
```bash
# Ensure ring is healthy with 9 nodes
kubectl exec -it cassandra-0 -- nodetool status | grep UN | wc -l
# Should show 9 UP/NORMAL nodes

# Check data consistency
kubectl exec -it cassandra-0 -- nodetool repair
```

## Complete or Rollback

After validating during soak:

```bash
# If everything looks good - complete the upgrade
gcloud container node-pools complete-upgrade CASSANDRA_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE

# If issues found - rollback quickly
gcloud container node-pools rollback-upgrade CASSANDRA_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE
```

## Resource Requirements

**Important:** Blue-green requires **2x your current node pool capacity** during the upgrade (18 nodes total). Ensure you have sufficient quota:

```bash
# Check current quota
gcloud compute project-info describe --format="table(quotas[].metric,quotas[].usage,quotas[].limit)"
```

If quota is tight, you could use the drain-first approach instead, but it's riskier:

```bash
# Alternative if quota is constrained (NOT recommended for Cassandra)
gcloud container node-pools update CASSANDRA_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

## Key Takeaway

Blue-green is the **only safe native GKE strategy** for Cassandra with local SSDs. The extended soak period gives you time to properly decommission old nodes and validate the new ring before committing to the upgrade.