# Node Pool Upgrade Strategy: Cassandra with Local SSDs

## Recommendation: **Surge Upgrade** with Conservative Settings

For your Cassandra ring with local SSDs, I recommend **surge upgrade** with very conservative settings. Here's why:

### Why Surge Over Blue-Green for Cassandra

**Surge advantages:**
- Preserves existing local SSD data during the upgrade window
- Cassandra can maintain quorum with temporary capacity increase
- More cost-effective (no 2x node cost)
- Simpler rollback if issues arise

**Blue-green risks for Cassandra:**
- Forces complete data rebuild on new nodes (local SSDs don't migrate)
- Requires careful coordination to avoid split-brain scenarios
- 2x compute cost during migration window
- Complex data synchronization between old and new rings

### Recommended Surge Configuration

```bash
# Configure conservative surge settings for Cassandra pool
gcloud container node-pools update CASSANDRA_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Why these settings:**
- `maxSurge=1`: Only one extra node at a time, minimizes cost and complexity
- `maxUnavailable=0`: Never reduces capacity below 9 nodes, maintains quorum safety
- Upgrade sequence: 9→10→9→10→9 (one node upgraded per cycle)

### Pre-Upgrade Checklist for Cassandra

```
Cassandra-Specific Pre-Upgrade Checks
- [ ] Cassandra ring health: `nodetool status` shows all nodes UP/NORMAL
- [ ] Replication factor ≥ 3 (can tolerate 1-2 node loss)
- [ ] No ongoing repairs or compactions: `nodetool compactionstats`
- [ ] Recent backup completed (even though data stays on local SSDs)
- [ ] PDB configured: minAvailable: 7 (allows 2 nodes down max)
- [ ] terminationGracePeriodSeconds: 300+ (time for graceful shutdown)
- [ ] Local SSD mount paths consistent in StatefulSet spec
- [ ] Anti-affinity rules prevent multiple Cassandra pods per node
- [ ] Adequate heap/off-heap memory limits for temporary node churn
```

### PDB Configuration

Create a restrictive PDB to protect your ring:

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-pdb
  namespace: cassandra
spec:
  minAvailable: 7  # Allow max 2 nodes down (9-7=2)
  selector:
    matchLabels:
      app: cassandra
```

```bash
kubectl apply -f cassandra-pdb.yaml
```

### Upgrade Runbook

```bash
# 1. Pre-flight checks
kubectl get nodes -l nodepool=cassandra
kubectl exec -it cassandra-0 -- nodetool status
kubectl get pdb cassandra-pdb -o wide

# 2. Verify PDB allows disruption
# Should show ALLOWED DISRUPTIONS: 2
kubectl get pdb cassandra-pdb -o wide

# 3. Start node pool upgrade
gcloud container node-pools upgrade CASSANDRA_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION

# 4. Monitor progress (expect ~45-60 min total for 9 nodes)
watch 'kubectl get nodes -l nodepool=cassandra -o wide'
watch 'kubectl exec -it cassandra-0 -- nodetool status'

# 5. Validate each node as it rejoins
# Each upgraded node should show UP/NORMAL in nodetool status
# before the next node begins upgrading
```

### Monitoring During Upgrade

Watch these Cassandra metrics:
```bash
# Ring status (all nodes should stay UP/NORMAL except the one upgrading)
kubectl exec -it cassandra-0 -- nodetool status

# No pending hints (indicates healthy cluster)
kubectl exec -it cassandra-0 -- nodetool tpstats | grep -i hint

# Confirm pods reschedule to upgraded nodes
kubectl get pods -l app=cassandra -o wide
```

### What to Expect

1. **Timeline**: ~45-60 minutes for 9 nodes (5-7 min per node)
2. **Capacity**: Ring operates at 10 nodes temporarily, then back to 9
3. **Data**: Local SSD data preserved - pods restart on same physical storage
4. **Quorum**: Maintained throughout (minimum 7/9 nodes always available)
5. **Performance**: Brief impact when each pod restarts, but ring stays available

### Rollback Plan

If the upgrade encounters issues:

```bash
# Cancel ongoing upgrade (completes current node, stops there)
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE
# Note the operation ID, then contact GKE support if stuck

# Cassandra-level recovery
kubectl exec -it cassandra-0 -- nodetool repair -pr
kubectl exec -it cassandra-1 -- nodetool repair -pr
# Continue for all nodes to ensure consistency
```

### Alternative: Blue-Green (if surge fails)

Only consider blue-green if:
- Surge upgrade fails due to local SSD attachment issues
- You have 2x compute quota available
- You can afford the data rebuild time (hours to days depending on data size)

The blue-green approach would require careful orchestration to bootstrap new nodes from existing data, which is significantly more complex for Cassandra than the surge approach.

**Bottom line**: Surge with conservative settings is the safest path for your Cassandra ring. The local SSD data preservation and maintained quorum make it much lower risk than blue-green.