This "musical chairs" problem is a common issue with aggressive `maxSurge` settings during node pool upgrades. Here's what's happening and how to fix it:

## Root Cause

When `maxSurge` is set too high (e.g., 5+ nodes), GKE cordons and drains multiple nodes simultaneously **before** the surge nodes are fully ready to receive workloads. The Kubernetes scheduler sees available capacity on nodes that are cordoned but not yet draining, so it places evicted pods there - only for those nodes to start draining shortly after.

**Timeline breakdown:**
1. GKE cordons nodes A, B, C, D (marks unschedulable)  
2. GKE starts creating surge nodes, but they take 2-3 minutes to become Ready
3. GKE begins draining node A → pods evicted
4. Scheduler looks for capacity → finds nodes B, C, D (not yet draining)
5. Pods land on node B
6. Node B starts draining → pods evicted again
7. Cycle repeats until surge nodes are Ready

## Immediate Fix: Reduce maxSurge to 1

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Why this works:** With `maxSurge=1`, GKE upgrades one node at a time. The surge node becomes Ready before the next old node starts draining, ensuring upgraded nodes are available as landing spots.

## Alternative Fix: Autoscaled Blue-Green Strategy

If you need faster upgrades without the musical chairs problem:

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes MIN --total-max-nodes MAX \
  --strategy=BLUE_GREEN \
  --node-pool-soak-duration=3600s \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25
```

**Why this works:** Blue-green creates the entire new pool first, then drains the old pool. Pods always have upgraded nodes available.

## Prevention for Future Upgrades

**Strategy selection guidelines:**
- **Small pools (≤10 nodes):** `maxSurge=1` is fine and avoids the issue
- **Large pools needing speed:** Consider autoscaled blue-green instead of high surge
- **GPU pools:** Always use `maxSurge=0, maxUnavailable=1-4` (surge capacity rarely available)

**Node affinity workaround** (if you must keep high maxSurge):
Add this to critical workloads to prefer already-upgraded nodes:

```yaml
affinity:
  nodeAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
    - weight: 100
      preference:
        matchExpressions:
        - key: node.kubernetes.io/instance-type
          operator: In
          values: ["TARGET_MACHINE_TYPE"]  # Surge nodes use same type
```

## Monitor the Fix

```bash
# Watch node versions during upgrade
watch 'kubectl get nodes -o custom-columns="NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,STATUS:.status.conditions[?(@.type==\"Ready\")].status" --sort-by=.metadata.name'

# Check pod placement
kubectl get pods -A -o wide | grep -E "Running|Pending"
```

**Expected behavior after fix:** Pods should land on already-upgraded nodes and stay there, rather than getting shuffled multiple times.

The key insight is that **upgrade speed vs. placement stability is a trade-off**. Slower upgrades (`maxSurge=1`) provide predictable pod placement, while faster upgrades risk the musical chairs problem unless you use blue-green strategies.