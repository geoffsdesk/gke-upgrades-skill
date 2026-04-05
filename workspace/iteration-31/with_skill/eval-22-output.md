This is a classic "musical chairs" problem during surge upgrades! The issue occurs when `maxSurge` is set too high relative to the available upgraded nodes.

## What's happening

1. GKE creates surge nodes and begins draining multiple old nodes simultaneously
2. Pods evicted from the first batch of draining nodes get scheduled to other old nodes
3. When those nodes start draining, the pods get evicted again
4. This creates a cycle where pods bounce between nodes that are all queued for upgrade

## Root causes

**High maxSurge with limited upgraded capacity:**
```bash
# Check your current surge settings
gcloud container node-pools describe NODE_POOL_NAME \
  --cluster CLUSTER_NAME --zone ZONE \
  --format="value(upgradeSettings.maxSurge,upgradeSettings.maxUnavailable)"

# Check node upgrade status
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool
```

**Scheduler preferences:**
- Kubernetes scheduler doesn't prefer upgraded nodes
- It may choose any available node, including ones about to be drained
- Pod anti-affinity or resource constraints can force pods onto doomed nodes

## Solutions

### 1. Reduce maxSurge (immediate fix)

Lower the surge parallelism so upgraded nodes are available before the next batch drains:

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

This ensures:
- Only 1 new node is created at a time
- Only 1 old node drains at a time  
- Evicted pods land on the upgraded node before the next node starts draining

### 2. Use node affinity to prefer upgraded nodes

Add node affinity to workloads to prefer nodes at the target version:

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
            values:
            - TARGET_MACHINE_TYPE  # or use node version labels
```

### 3. Switch to autoscaled blue-green (best for avoiding musical chairs)

This strategy completely eliminates the musical chairs problem:

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes MIN --total-max-nodes MAX \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25
```

How it works:
- Creates a separate "green" node pool with target version
- Cordons the old "blue" pool (no new pods scheduled there)
- Drains blue pool gradually while green pool scales up
- No pod shuffling between nodes destined for upgrade

### 4. Taint-based approach (advanced)

Temporarily taint nodes being drained to repel new pods:

```bash
# Apply to nodes about to be drained (automated by some upgrade controllers)
kubectl taint node NODE_NAME upgrade=in-progress:NoSchedule
```

## Monitoring the fix

```bash
# Watch pod movements during upgrade
kubectl get events -A --sort-by='.lastTimestamp' | grep -E "Scheduled|Pulled"

# Monitor which nodes pods land on
kubectl get pods -o wide -A --sort-by='.spec.nodeName'

# Check if pods are stabilizing on upgraded nodes
kubectl get nodes -l cloud.google.com/gke-nodepool=NODE_POOL_NAME -o wide
```

## Prevention for future upgrades

**For stateless workloads:**
- Use `maxSurge=1` as default to ensure sequential upgrade
- Only increase maxSurge if you've verified adequate upgraded capacity exists

**For large clusters:**
- Consider autoscaled blue-green as the default strategy
- It's more predictable and avoids the musical chairs problem entirely

**For mixed workloads:**
- Use pod priorities to ensure critical workloads land on upgraded nodes first
- Configure appropriate resource requests so scheduler makes better placement decisions

The key insight is that **maxSurge=1 trades speed for predictability** — slower upgrades but pods land where they should the first time.