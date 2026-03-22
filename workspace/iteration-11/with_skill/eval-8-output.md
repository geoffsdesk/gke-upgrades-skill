For a Cassandra ring with local SSDs, I **strongly recommend blue-green upgrade** over surge. Here's why and how to configure it:

## Why Blue-Green for Cassandra

**Cassandra + Local SSDs = High Risk with Surge:**
- **Data locality**: Cassandra with local SSDs means your data is physically tied to specific nodes. Surge upgrades terminate nodes, permanently destroying local SSD data.
- **Ring topology**: Cassandra's ring architecture means losing multiple nodes simultaneously can cause data unavailability or consistency issues, even with replication.
- **No graceful migration**: Unlike network-attached storage, local SSD data cannot be "moved" to new nodes during surge.

**Blue-Green Benefits:**
- **Zero data loss**: Old nodes (blue pool) stay running with all data intact until cutover
- **Fast rollback**: If issues arise, simply uncordon the blue pool - all data is still there
- **Controlled migration**: You can orchestrate Cassandra ring rebalancing properly
- **Validation window**: Soak time lets you verify the new ring is healthy before committing

## Configuration Steps

### 1. Pre-upgrade: Prepare Cassandra
```bash
# Backup your keyspaces (even though blue-green preserves data)
nodetool snapshot --tag pre-upgrade-backup

# Verify ring health
nodetool status
nodetool describecluster
```

### 2. Configure Blue-Green Upgrade
```bash
# Set the node pool upgrade strategy to blue-green
gcloud container node-pools update cassandra-pool \
  --cluster YOUR_CLUSTER_NAME \
  --region YOUR_REGION \
  --enable-blue-green-update \
  --node-pool-soak-duration 600s \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 0
```

**Key parameters explained:**
- `--enable-blue-green-update`: Activates blue-green mode
- `--node-pool-soak-duration 600s`: 10-minute soak period (adjust as needed)
- Both surge settings to 0: Forces pure blue-green behavior

### 3. Execute the Upgrade
```bash
# Upgrade the node pool
gcloud container node-pools upgrade cassandra-pool \
  --cluster YOUR_CLUSTER_NAME \
  --region YOUR_REGION \
  --cluster-version TARGET_VERSION
```

### 4. Monitor the Process
```bash
# Watch nodes during upgrade
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=cassandra-pool -o wide'

# Monitor Cassandra ring status
watch 'kubectl exec -it cassandra-0 -- nodetool status'

# Check pod distribution
kubectl get pods -o wide | grep cassandra
```

## Blue-Green Flow for Your Cassandra Ring

1. **Green pool creation**: GKE provisions 9 new nodes with updated version
2. **Pod rescheduling**: Cassandra pods start on green nodes, begin bootstrapping
3. **Ring rebalancing**: Cassandra automatically starts rebalancing data across old + new nodes
4. **Soak period**: 10-minute window to verify new nodes are healthy and participating
5. **Blue pool drainage**: Old nodes are cordoned and drained
6. **Cleanup**: Blue pool deleted after successful cutover

## Important Considerations

**Quota Requirements:**
- You'll need capacity for 18 nodes temporarily (9 blue + 9 green)
- Local SSDs will be provisioned on both pools during overlap
- Budget for ~2x your normal capacity cost during the upgrade window

**Cassandra-Specific Validation:**
```bash
# During soak period, verify:
kubectl exec -it cassandra-0 -- nodetool status
# All nodes should show "UN" (Up Normal)

kubectl exec -it cassandra-0 -- nodetool describecluster
# Verify schema agreement across all nodes

# Check for repair/bootstrap progress
kubectl exec -it cassandra-0 -- nodetool compactionstats
```

**Rollback Plan:**
If issues occur during soak period:
```bash
# Uncordon blue pool (old nodes)
kubectl uncordon -l cloud.google.com/gke-nodepool=cassandra-pool-blue

# Delete green pool pods if needed
kubectl delete pods -l app=cassandra --field-selector spec.nodeName=green-node-*
```

## Alternative: Autoscaled Blue-Green (Preview)

If you're open to preview features, consider autoscaled blue-green for even better resource efficiency:

```bash
gcloud container node-pools update cassandra-pool \
  --cluster YOUR_CLUSTER_NAME \
  --region YOUR_REGION \
  --enable-autoscaled-blue-green-update \
  --node-pool-soak-duration 900s  # 15 mins for Cassandra
```

This scales the green pool up as needed rather than provisioning all 9 nodes upfront, reducing cost while maintaining the safety benefits.

## Timeline Expectations

- **Green pool provisioning**: 5-10 minutes
- **Cassandra bootstrap on new nodes**: 15-30 minutes (depends on data size)
- **Soak period**: 10 minutes (configurable)
- **Blue pool drainage**: 10-15 minutes
- **Total**: 45-60 minutes for the full upgrade

Blue-green is the right choice here - the temporary cost overhead is worth avoiding the catastrophic risk of data loss with surge upgrades on local SSDs.