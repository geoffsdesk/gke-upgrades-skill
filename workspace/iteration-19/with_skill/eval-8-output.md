For your Cassandra ring with local SSDs, **blue-green upgrade is the only safe option**. Here's why and how to configure it:

## Why Blue-Green is Required for Cassandra

**Surge upgrade would cause data loss:**
- Surge drains nodes, destroying local SSD data
- Cassandra nodes would lose their data and need to rebuild from other replicas
- This causes massive rebalancing storms and potential data loss if multiple nodes are affected

**Blue-Green preserves your ring:**
- Old nodes (blue pool) stay running with data intact during the upgrade
- New nodes (green pool) are created and join the ring properly
- Cassandra can decommission gracefully before the old nodes are deleted

## Recommended Configuration

```bash
# Configure blue-green upgrade strategy
gcloud container node-pools update CASSANDRA_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --strategy=BLUE_GREEN \
    --node-pool-soak-duration=7200s \
    --standard-rollout-policy=batch-node-count=1,batch-soak-duration=600s
```

**Key parameters explained:**
- `--node-pool-soak-duration=7200s` (2 hours): Time to validate the new ring topology before deleting old nodes
- `--batch-node-count=1`: Upgrade one node at a time (conservative for Cassandra)
- `--batch-soak-duration=600s` (10 minutes): Wait between each node to allow ring stabilization

## Pre-Upgrade Checklist for Cassandra

```bash
# 1. Configure PDB to protect quorum (assuming RF=3)
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-pdb
  namespace: NAMESPACE
spec:
  minAvailable: 2  # Maintains quorum during upgrades
  selector:
    matchLabels:
      app: cassandra
EOF

# 2. Take application-level backup
kubectl exec -it cassandra-0 -n NAMESPACE -- nodetool snapshot

# 3. Verify cluster health
kubectl exec -it cassandra-0 -n NAMESPACE -- nodetool status
# All nodes should show UN (Up/Normal)

# 4. Check local SSD mount points are healthy
kubectl get pods -l app=cassandra -o wide
# Verify all pods are running on different nodes
```

## Upgrade Execution

```bash
# Start the blue-green upgrade
gcloud container node-pools upgrade CASSANDRA_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version TARGET_VERSION

# Monitor the upgrade phases
watch 'gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=1'
```

## Monitoring During Upgrade

```bash
# Watch Cassandra ring status
watch 'kubectl exec -it cassandra-0 -n NAMESPACE -- nodetool status'

# Monitor pod distribution
watch 'kubectl get pods -l app=cassandra -o wide'

# Check for any stuck operations
kubectl get pods -l app=cassandra | grep -v Running
```

## Blue-Green Phases for Your Cassandra Ring

1. **Create Phase**: New nodes (green pool) are created and join the Cassandra ring
2. **Cordon Phase**: Old nodes (blue pool) are marked unschedulable but keep running
3. **Drain Phase**: Cassandra pods are gracefully moved to new nodes (one at a time)
4. **Soak Phase**: 2-hour validation period - verify ring health, data consistency, performance
5. **Delete Phase**: Old nodes are removed (this is when local SSD data is finally destroyed)

## Important Notes

- **Capacity requirement**: You'll temporarily need 2x your node pool capacity during the upgrade
- **Network policies**: Ensure Cassandra inter-node communication works between blue and green pools
- **Storage class**: Your StatefulSet should use local SSD storage class that works on the new nodes
- **Ring expansion**: Cassandra will see the new nodes join and may start rebalancing - this is expected
- **Rollback capability**: During the soak phase, you can still rollback if issues are detected

## If Blue-Green Isn't Feasible (Capacity Constraints)

If you can't temporarily double your capacity, consider **manual blue-green**:

1. Create a new node pool at the target version
2. Scale your StatefulSet to add replicas on new nodes
3. Use `nodetool decommission` to safely remove old nodes
4. Delete the old pool once all data is migrated

This is more work but gives you complete control over the Cassandra ring topology changes.

Would you like me to help you plan the specific timeline and monitoring approach for your upgrade window?