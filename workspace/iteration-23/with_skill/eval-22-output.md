This is a classic "musical chairs" problem during GKE node pool upgrades! Here's what's happening and how to fix it:

## What's Causing the Musical Chairs Problem

When `maxSurge` is set too high (e.g., 5+ nodes), GKE:
1. Creates surge nodes with the new version
2. **Simultaneously** cordons and drains multiple old nodes
3. Evicted pods get scheduled to ANY available node with capacity
4. The scheduler doesn't prefer upgraded nodes - it just finds space
5. Pods land on old nodes that are about to be drained in the next batch
6. Those pods get evicted again, creating a shuffle cycle

The root cause is **too much parallelism** - you're draining nodes faster than the scheduler can intelligently place pods on the "safe" upgraded nodes.

## Immediate Fix: Reduce maxSurge to 1

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Why this works:**
- Only 1 surge node created at a time
- Only 1 old node drained at a time  
- Pods evicted from the draining node land on the already-upgraded nodes (because they have capacity)
- No shuffling between "about to be drained" nodes

## Alternative Solutions

### Option 2: Node Affinity for Upgraded Nodes
Add temporary node affinity to prefer upgraded nodes:

```yaml
spec:
  affinity:
    nodeAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        preference:
          matchExpressions:
          - key: node.kubernetes.io/version
            operator: In
            values:
            - "v1.XX.XX-gke.XXXX"  # Target version
```

### Option 3: Use Autoscaled Blue-Green Strategy
This avoids the musical chairs problem entirely:

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes MIN --total-max-nodes MAX \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25
```

**How it works:**
- Creates a new "green" pool with upgraded nodes
- Cordons the old "blue" pool (no new pods scheduled there)
- Pods naturally drain to the green pool over time
- No shuffling between nodes that are about to be drained

## Monitor the Fix

```bash
# Watch pod placement during upgrade
kubectl get pods -A -o wide --sort-by='.spec.nodeName' | grep NODE_POOL_NAME

# Check which nodes are at which version
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool

# Monitor events for scheduling decisions
kubectl get events -A --field-selector reason=Scheduled --watch
```

## Prevention for Future Upgrades

**Best practice for surge settings:**
- **Small pools (< 20 nodes):** `maxSurge=1, maxUnavailable=0`
- **Large pools:** `maxSurge=5%` of pool size, capped at ~5 nodes
- **GPU pools:** `maxSurge=0, maxUnavailable=1-2` (no surge capacity typically available)

**The key insight:** Higher `maxSurge` doesn't always mean faster upgrades if it causes pod shuffling. Sometimes slower and steadier (maxSurge=1) actually completes faster because pods don't get evicted multiple times.

Your musical chairs problem should resolve within 10-15 minutes after applying the `maxSurge=1` setting. The remaining old nodes will drain one at a time, with pods landing safely on already-upgraded nodes.