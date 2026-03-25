# Musical Chairs Problem: Pods Landing on Soon-to-be-Drained Nodes

This is a classic GKE upgrade issue called the "musical chairs" problem. Here's what's happening and how to fix it:

## Root Cause

During surge upgrades with high `maxSurge` settings, GKE:
1. Cordons multiple nodes simultaneously (marks them unschedulable)
2. Creates surge nodes to replace them
3. Starts draining the cordoned nodes

**The problem:** When pods are evicted from Node A, the scheduler may place them on Node B - but Node B is also cordoned and about to be drained. The pods get shuffled between nodes that are all in the "draining" state rather than landing on stable, upgraded nodes.

This happens because:
- Surge nodes may not be Ready yet when pods need rescheduling
- The scheduler sees multiple nodes with similar characteristics and spreads pods across them
- High `maxSurge` settings drain many nodes before enough upgraded nodes are available

## Immediate Fix: Reduce maxSurge to 1

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Why this works:** With `maxSurge=1`, GKE:
1. Creates 1 surge node and waits for it to be Ready
2. Cordons and drains 1 old node
3. Evicted pods land on the already-upgraded surge node
4. Repeats with the next node

This ensures upgraded nodes are available BEFORE the next batch of pods needs rescheduling.

## Alternative: Switch to Autoscaled Blue-Green

For a more elegant solution that avoids the musical chairs problem entirely:

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --strategy BLUE_GREEN \
  --enable-autoscaling \
  --total-min-nodes MIN --total-max-nodes MAX \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

**How autoscaled blue-green solves this:**
- Creates the new (green) pool first
- Cordons the old (blue) pool
- Autoscaler provisions green nodes as workloads drain from blue
- Pods always land on stable, upgraded nodes

## Additional Mitigations

### 1. Use pod anti-affinity to prefer upgraded nodes

```yaml
spec:
  affinity:
    podAntiAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        podAffinityTerm:
          labelSelector:
            matchLabels:
              app: your-app
          topologyKey: kubernetes.io/hostname
```

### 2. Check for node taints causing scheduler confusion

```bash
kubectl describe nodes | grep Taints
```

If nodes have custom taints, the scheduler may be limited in placement options.

### 3. Monitor the musical chairs pattern

```bash
# Watch pods getting rescheduled
kubectl get events -A --watch --field-selector reason=Scheduled

# Check which nodes pods are landing on
kubectl get pods -A -o wide --sort-by='.spec.nodeName'
```

## Why High maxSurge Causes This

| maxSurge Setting | Behavior | Musical Chairs Risk |
|------------------|----------|-------------------|
| `maxSurge=1` | Drain 1 node at a time, surge node Ready first | **Low** - upgraded nodes available |
| `maxSurge=5%` of pool | Drain multiple nodes, may outpace surge node creation | **Medium** - timing dependent |
| `maxSurge=10` (fixed) | Drain 10 nodes simultaneously | **High** - many cordoned nodes, few upgraded nodes |

## Trade-offs

**Reducing maxSurge to 1:**
- ✅ Eliminates musical chairs
- ✅ More predictable pod placement
- ❌ Slower upgrade (less parallelism)

**Autoscaled blue-green:**
- ✅ Eliminates musical chairs entirely
- ✅ Faster than maxSurge=1
- ✅ Better for stateful workloads
- ❌ Requires autoscaling to be enabled
- ❌ More complex (preview feature)

## Recommendation

For your immediate situation:
1. **Set `maxSurge=1`** to stop the musical chairs
2. **Monitor** that pods now land on stable nodes
3. **Consider autoscaled blue-green** for future upgrades if you need faster completion

The musical chairs problem is a sign that your surge settings are too aggressive for the cluster's scheduling dynamics. Reducing parallelism fixes the root cause and makes upgrades more predictable.