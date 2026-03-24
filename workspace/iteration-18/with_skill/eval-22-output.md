# Musical Chairs Problem During GKE Node Upgrades

You're experiencing the classic "musical chairs" problem during node pool upgrades. This happens when your `maxSurge` setting is too high relative to your cluster size, causing multiple nodes to drain simultaneously before enough upgraded nodes are available.

## What's happening

1. GKE starts upgrading multiple nodes in parallel (based on `maxSurge`)
2. Pods get evicted from Node A (being drained)
3. Kubernetes scheduler places them on Node B 
4. But Node B is also in the upgrade queue and gets cordoned/drained shortly after
5. Pods get evicted again and land on Node C, which is also about to be drained
6. This continues until pods finally land on already-upgraded nodes

## Root cause: maxSurge too high

When `maxSurge` allows many nodes to upgrade simultaneously, there's a timing gap where:
- Old nodes are being drained (pods evicted)
- New surge nodes are still starting up (not ready for scheduling)
- Remaining old nodes become targets for rescheduled pods, but they're also queued for upgrade

## Fix 1: Reduce maxSurge to 1 (recommended)

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Why this works:** With `maxSurge=1`, only one node upgrades at a time. The upgraded node becomes available before the next node starts draining, guaranteeing a safe landing spot for evicted pods.

**Trade-off:** Slower upgrade (sequential vs parallel), but eliminates the musical chairs problem entirely.

## Fix 2: Use autoscaled blue-green upgrade (if available)

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --strategy AUTOSCALED_BLUE_GREEN \
  --enable-autoscaling \
  --total-min-nodes MIN_NODES \
  --total-max-nodes MAX_NODES \
  --autoscaled-rollout-policy blue-green-initial-node-percentage=0.25
```

**Why this works:** Creates a completely separate "green" node pool first, then gradually drains the "blue" pool. No musical chairs because the destination nodes exist before any draining begins.

**Trade-off:** Requires autoscaling to be enabled and temporarily uses more resources.

## Fix 3: Pod placement preferences (advanced)

Add node affinity to prefer already-upgraded nodes:

```yaml
# Example deployment modification
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
                values: ["MACHINE_TYPE"]  # Matches your target node type
```

## Validation that the fix worked

Monitor pod placement during upgrade:

```bash
# Watch nodes and their versions
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check for pods landing on already-upgraded nodes
kubectl get pods -A -o wide | grep -E "NODE_NAME_PATTERN"

# Confirm no pods stuck in Pending
kubectl get pods -A --field-selector=status.phase=Pending
```

## Prevention for future upgrades

**Small-to-medium clusters (< 50 nodes):** Always use `maxSurge=1, maxUnavailable=0`

**Large clusters (50+ nodes):** Calculate maxSurge as a small percentage of pool size:
- 100 nodes → `maxSurge=2-3` (2-3% of pool)
- 500 nodes → `maxSurge=10` (2% of pool)
- Cap at GKE's maximum parallelism (~20 nodes simultaneously)

**GPU pools:** Use `maxSurge=0, maxUnavailable=1` since surge GPU capacity is typically unavailable.

The key insight: **maxSurge controls parallelism, but too much parallelism creates the musical chairs problem.** Lower maxSurge = slower but more predictable pod placement.