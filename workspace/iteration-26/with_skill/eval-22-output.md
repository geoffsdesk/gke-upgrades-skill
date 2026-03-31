This is a classic "musical chairs" problem during surge upgrades! Here's what's happening and how to fix it:

## What's causing the musical chairs effect

**Root cause:** Your `maxSurge` setting is too high relative to your cluster capacity. When GKE drains multiple nodes simultaneously, the scheduler places evicted pods on ANY available nodes - including nodes that are queued for upgrade next. This creates a cascade where pods bounce between nodes about to be drained.

**Why it happens:**
- High `maxSurge` (e.g., 5+ nodes) cordons and drains multiple nodes before enough upgraded nodes exist
- Scheduler sees "available capacity" on old-version nodes and places pods there
- Those nodes then get cordoned/drained in the next batch, forcing another reshuffle
- Pods never "settle" on the upgraded nodes

## Immediate fix: Reduce maxSurge to 1

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Why this works:** With `maxSurge=1`, GKE creates 1 new node, waits for it to be ready, then drains 1 old node. This ensures upgraded nodes are always available before the next drain cycle starts.

**Trade-off:** Slower upgrade (sequential instead of parallel), but pods land on stable, upgraded nodes.

## Alternative solutions

### Option 2: Use pod anti-affinity to prefer upgraded nodes
Add this to your workload specs to avoid old-version nodes:

```yaml
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      affinity:
        nodeAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            preference:
              matchExpressions:
              - key: node.kubernetes.io/instance-type
                operator: In
                values: ["n1-standard-4"]  # Replace with your target node type
```

### Option 3: Use autoscaled blue-green upgrade (Preview)
This strategy avoids musical chairs entirely by creating a new pool before draining the old one:

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes MIN --total-max-nodes MAX \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25
```

**How it works:** Creates 25% of nodes in the new (green) pool, cordons the old (blue) pool, then scales down blue as workloads migrate to green. No musical chairs because green nodes exist before blue nodes drain.

### Option 4: Temporary node taints during upgrade
Apply a temporary taint to nodes queued for upgrade:

```bash
# Taint nodes about to be upgraded (prevents new pods from landing there)
kubectl taint nodes NODE_NAME upgrade=pending:NoSchedule

# Remove taint after upgrade completes
kubectl taint nodes NODE_NAME upgrade=pending:NoSchedule-
```

## Prevention for future upgrades

1. **Default to `maxSurge=1`** for most workloads - it's predictable
2. **Use percentage-based maxSurge** only when you've verified the math: for a 20-node pool, `maxSurge=2` means 10% concurrency, but ensure 2+ upgraded nodes exist before the next batch
3. **Monitor pod churn** during upgrades: `kubectl get events -A --field-selector reason=SuccessfulCreate | wc -l`
4. **Consider autoscaled blue-green** for production workloads where upgrade predictability matters more than speed

## Validation commands

Check if pods are stabilizing on upgraded nodes:
```bash
# Show which nodes pods are running on
kubectl get pods -A -o wide | grep -E "NODE|IP"

# Check node versions
kubectl get nodes -o custom-columns="NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion"

# Monitor pod movements
kubectl get events -A --field-selector reason=Scheduled --sort-by='.lastTimestamp' | tail -10
```

**The key insight:** Musical chairs happens when you drain faster than you create stable landing spots. `maxSurge=1` is the simplest fix - it ensures every evicted pod has a permanent home on an already-upgraded node.