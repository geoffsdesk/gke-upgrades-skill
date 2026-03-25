Based on your Cassandra setup with local SSDs, I strongly recommend **blue-green upgrade**. Here's why and how to configure it:

## Why Blue-Green for Cassandra + Local SSDs

**Surge upgrade is problematic for your setup:**
- Surge drains nodes, **destroying local SSD data** — Cassandra data stored on local SSDs would be lost
- Even with proper decommissioning, surge's 1-hour drain timeout may be insufficient for Cassandra to safely redistribute data
- Risk of multiple nodes draining simultaneously if `maxSurge > 1`, which could break Cassandra quorum

**Blue-green upgrade advantages:**
- Old (blue) nodes stay available during the entire process — **local SSD data is preserved**
- Gives you time to properly decommission Cassandra nodes before they're deleted
- Quick rollback path if issues arise
- Controlled, predictable process that respects Cassandra's distributed nature

## Configuration Commands

### 1. Configure Blue-Green Strategy

```bash
gcloud container node-pools update CASSANDRA_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --strategy=BLUE_GREEN \
    --node-pool-soak-duration=7200s \
    --standard-rollout-policy=batch-node-count=1,batch-soak-duration=300s
```

**Key parameters explained:**
- `--node-pool-soak-duration=7200s` (2 hours) — time to validate Cassandra health before deleting blue nodes
- `batch-node-count=1` — drain one Cassandra node at a time (conservative)
- `batch-soak-duration=300s` (5 minutes) — wait between each node drain for Cassandra to stabilize

### 2. Set Up PDB for Cassandra Protection

```bash
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-pdb
  namespace: CASSANDRA_NAMESPACE
spec:
  minAvailable: 7  # Allows 2 nodes down simultaneously max (9-7=2)
  selector:
    matchLabels:
      app: cassandra
EOF
```

### 3. Pre-Upgrade Cassandra Health Check

```bash
# Verify all nodes are UN (Up Normal)
kubectl exec -it cassandra-0 -n CASSANDRA_NAMESPACE -- nodetool status

# Check no pending repairs or streaming
kubectl exec -it cassandra-0 -n CASSANDRA_NAMESPACE -- nodetool netstats
```

## Blue-Green Upgrade Workflow for Cassandra

### Phase 1: Preparation
1. **Take snapshots** before starting:
```bash
kubectl exec -it cassandra-0 -n CASSANDRA_NAMESPACE -- nodetool snapshot
```

2. **Verify cluster health** — all nodes UN, no pending operations

3. **Start the upgrade:**
```bash
gcloud container node-pools upgrade CASSANDRA_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version TARGET_VERSION
```

### Phase 2: During Blue-Green Process
- **Green nodes created** — new nodes provision with target version
- **Blue nodes cordoned** — old nodes marked unschedulable  
- **Gradual drain** — Cassandra pods move to green nodes one at a time
- **Monitor Cassandra health** during each batch:
```bash
# Watch ring status during drain
kubectl exec -it cassandra-0 -n CASSANDRA_NAMESPACE -- watch nodetool status
```

### Phase 3: Soak Period (2 hours)
- **Validate Cassandra ring** on new nodes
- **Check data consistency**:
```bash
kubectl exec -it cassandra-0 -n CASSANDRA_NAMESPACE -- nodetool repair -pr
```
- **Performance testing** if needed

### Phase 4: Completion
- Blue nodes deleted automatically after soak period
- Local SSD data on blue nodes is safely discarded (after Cassandra migrated to green)

## Important Cassandra-Specific Considerations

**Node replacement handling:**
- Cassandra will see new nodes joining and old nodes leaving the ring
- Use `auto_bootstrap: true` in cassandra.yaml so new nodes properly join
- Monitor for any "JOINING" or "LEAVING" states during the process

**Resource requirements:**
- You'll need capacity for **18 Cassandra nodes temporarily** (9 blue + 9 green)
- Ensure you have sufficient quota for double the node pool size
- Local SSD quota will also need to accommodate both pools

**Rollback capability:**
During soak period, you can rollback quickly:
```bash
# Uncordon blue nodes if rollback needed
kubectl uncordon NODE_NAME
```

**Alternative if quota is constrained:**
If you can't accommodate 18 nodes, consider **autoscaled blue-green** (preview):
```bash
gcloud container node-pools update CASSANDRA_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --enable-autoscaling \
    --total-min-nodes 9 --total-max-nodes 15 \
    --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.33
```
This scales down blue as green scales up, reducing peak resource usage.

**Bottom line:** Blue-green is the only safe choice for Cassandra with local SSDs. The 2x resource cost is justified by data safety and the controlled migration process.