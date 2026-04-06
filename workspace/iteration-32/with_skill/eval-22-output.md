This is a classic "musical chairs" problem during GKE upgrades! You've identified the issue perfectly - pods are being evicted from nodes about to be drained, but they're landing on other nodes that are also queued for drain, causing repeated evictions.

## Root Cause

The problem occurs when `maxSurge` is set too high relative to your cluster size. Here's what happens:

1. GKE cordons multiple nodes simultaneously (based on your `maxSurge` setting)
2. All those nodes start draining at roughly the same time
3. Evicted pods look for somewhere to land, but many of the "available" nodes are also cordoned and about to drain
4. Pods get rescheduled to soon-to-be-drained nodes, causing cascading evictions

## Immediate Fix: Reduce maxSurge

The most effective solution is to reduce `maxSurge` to ensure upgraded nodes are available before the next batch starts draining:

```bash
# Set maxSurge to 1 for conservative, sequential upgrades
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Why this works:** With `maxSurge=1`, GKE:
1. Creates 1 new node with the target version
2. Cordons and drains exactly 1 old node
3. Evicted pods land on the newly upgraded node (guaranteed available)
4. Repeats with the next node only after the previous cycle completes

## Alternative Solutions

### Option 1: Use Autoscaled Blue-Green (Preview)
This strategy completely avoids the musical chairs problem:

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --strategy=AUTOSCALED_BLUE_GREEN \
  --enable-autoscaling \
  --total-min-nodes MIN_NODES \
  --total-max-nodes MAX_NODES
```

**How it works:** Creates a new "green" pool that scales up as the old "blue" pool scales down, ensuring pods always have upgraded nodes available.

### Option 2: Pod Anti-Affinity Rules
Add anti-affinity rules to prefer upgraded nodes:

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
              - key: cloud.google.com/gke-nodepool
                operator: In
                values: [NODE_POOL_NAME]
```

### Option 3: Temporary Node Taints
Manually taint nodes before GKE drains them to prevent new pod scheduling:

```bash
# Taint nodes you know will be drained soon
kubectl taint nodes NODE_NAME upgrade=in-progress:NoSchedule

# Remove after upgrade completes
kubectl taint nodes NODE_NAME upgrade=in-progress:NoSchedule-
```

## Best Practice Recommendations

1. **Start with maxSurge=1** for problematic pools, then gradually increase if needed
2. **For large node pools (50+ nodes):** Use percentage-based maxSurge (e.g., 2-5%) but cap at low absolute numbers initially
3. **Monitor the pattern:** Watch `kubectl get pods -A -o wide` during upgrades to see pod movement
4. **Consider upgrade timing:** Run upgrades during low-traffic periods when fewer pods are running

## Monitoring the Fix

```bash
# Watch node status during upgrade
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "Ready|NotReady|SchedulingDisabled"'

# Monitor pod movements
kubectl get pods -A -o wide --sort-by='.status.startTime' | tail -10

# Check for pending pods (shouldn't see many with maxSurge=1)
kubectl get pods -A --field-selector=status.phase=Pending
```

The maxSurge=1 approach trades speed for reliability - your upgrade will be slower but much more stable, with pods landing predictably on already-upgraded nodes.