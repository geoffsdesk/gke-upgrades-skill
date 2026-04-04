# Musical Chairs Problem in GKE Node Pool Upgrades

You're experiencing the "musical chairs" problem - a common issue during node pool upgrades where pods evicted from draining nodes land on other nodes that are also scheduled for drain, causing repeated evictions and poor upgrade performance.

## Root Cause

This happens when:
1. **High `maxSurge`** causes GKE to drain many nodes simultaneously
2. **Insufficient upgraded nodes** exist to absorb the evicted pods
3. **Scheduler spreads pods** across available nodes, including ones about to be drained
4. **No affinity rules** prefer already-upgraded nodes

## Immediate Fix: Reduce maxSurge

The most effective solution is to reduce surge parallelism so upgraded nodes are available before the next batch drains:

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Why this works:** With `maxSurge=1`, GKE:
1. Creates 1 new node at target version
2. Waits for it to become Ready
3. Drains 1 old node
4. Evicted pods land on the new upgraded node (guaranteed available)
5. Repeats for next node

## Alternative Solution: Autoscaled Blue-Green

For workloads that can't tolerate the musical chairs problem at all, use autoscaled blue-green upgrade:

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes MIN --total-max-nodes MAX \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

This creates a new "green" pool that scales up as the old "blue" pool scales down, eliminating the musical chairs entirely.

## Advanced: Pod Scheduling Preferences

For clusters that must use higher surge values, add node affinity to prefer upgraded nodes:

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
                values: [MACHINE_TYPE]  # Same type but newer nodes
```

Or use anti-affinity to avoid nodes being drained:

```yaml
podAntiAffinity:
  preferredDuringSchedulingIgnoredDuringExecution:
  - weight: 100
    podAffinityTerm:
      topologyKey: kubernetes.io/hostname
      labelSelector:
        matchLabels:
          app: YOUR_APP
```

## Monitoring the Fix

Watch node upgrade progress to confirm pods are landing on stable nodes:

```bash
# Monitor which nodes are being drained
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool

# Watch pod placement during upgrade
kubectl get pods -o wide --sort-by='.spec.nodeName'

# Check for repeated evictions (should decrease after fix)
kubectl get events --field-selector reason=Evicted --sort-by='.lastTimestamp'
```

## Prevention for Future Upgrades

**Default recommendation:** Always start with `maxSurge=1` for production workloads. Only increase if you need faster upgrades AND can tolerate the pod shuffling.

**For GPU pools:** Use `maxSurge=0, maxUnavailable=1-4` since surge capacity often doesn't exist anyway.

**For large clusters:** Even with `maxSurge=5%`, GKE's ~20-node parallelism limit means musical chairs is less common, but `maxSurge=1` is still safest.

The musical chairs problem is a classic sign that surge parallelism exceeds the cluster's ability to provide stable landing spots for evicted pods. Reducing `maxSurge` to 1 is the most reliable fix.