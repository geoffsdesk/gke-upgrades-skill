This "musical chairs" problem happens when `maxSurge` is set too high relative to your pool size, causing multiple nodes to drain simultaneously before enough upgraded nodes are available to absorb the evicted pods.

## What's happening

During a surge upgrade with high concurrency:
1. GKE cordons nodes A, B, C (to be drained)
2. Pods get evicted from node A
3. Kubernetes scheduler places them on nodes B or C (still schedulable but about to drain)
4. Nodes B, C start draining, evicting those same pods again
5. Cycle repeats until upgraded nodes become available

## Root cause analysis

Check your current surge settings:
```bash
gcloud container node-pools describe NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --format="value(upgradeSettings.maxSurge,upgradeSettings.maxUnavailable)"
```

If `maxSurge` is >10% of your pool size, this creates too much concurrent drain activity.

## Fix: Reduce maxSurge to 1

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

This ensures:
- Only 1 surge node is created at a time
- Only 1 old node is drained at a time  
- Upgraded nodes are always available before the next node starts draining
- Pods have a clear "landing zone" instead of musical chairs

## Alternative solutions

**Option 1: Use autoscaled blue-green upgrade**
This strategy avoids the musical chairs problem entirely by keeping the old pool serving while the new pool scales up:
```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --strategy=AUTOSCALED_BLUE_GREEN \
  --node-pool-soak-duration=1800s \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25
```

**Option 2: Add node affinity to prefer upgraded nodes**
This helps the scheduler bias toward already-upgraded nodes:
```yaml
spec:
  affinity:
    nodeAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        preference:
          matchExpressions:
          - key: node.kubernetes.io/instance-type
            operator: In
            values: ["n1-standard-1"]  # Your target node type
```

## Immediate troubleshooting

If you're seeing this right now:

1. **Check which nodes are being drained:**
```bash
kubectl get nodes -o wide
# Look for nodes with SchedulingDisabled
```

2. **Verify upgraded nodes exist:**
```bash
kubectl get nodes -o json | \
  jq -r '.items[] | select(.spec.unschedulable != true) | "\(.metadata.name) - \(.status.nodeInfo.kubeletVersion)"'
```

3. **Apply the maxSurge=1 fix above**

## Prevention for future upgrades

- **Small pools (≤20 nodes):** Always use `maxSurge=1`
- **Large pools (>20 nodes):** Use percentage-based surge like `maxSurge=5%` but never exceed 5-10% to avoid musical chairs
- **Consider autoscaled blue-green** for disruption-sensitive workloads - it eliminates this problem pattern entirely

The key insight is that **surge parallelism should scale with available landing capacity**, not just pool size. When in doubt, `maxSurge=1` is always safe and avoids the musical chairs anti-pattern.