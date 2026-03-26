This is a classic "musical chairs" problem during GKE upgrades! Here's what's happening and how to fix it:

## Root Cause Analysis

**What's happening:** Your `maxSurge` setting is too high relative to your cluster size. GKE is cordoning and draining multiple nodes simultaneously before enough upgraded nodes exist to absorb the evicted workloads. The scheduler places pods on available (non-cordoned) nodes, but those nodes are queued for upgrade and get cordoned shortly after.

**Example scenario:**
- 20-node pool with `maxSurge=5`
- GKE cordons nodes 1-5 simultaneously
- Pods from node 1 land on nodes 6-10
- Before pods settle, GKE cordons nodes 6-10 for the next batch
- Pods get evicted again and land on nodes 11-15
- The cycle continues...

## Immediate Fix: Reduce maxSurge to 1

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Why this works:** With `maxSurge=1`, GKE upgrades exactly one node at a time. The upgraded node becomes available before the next node is cordoned, giving evicted pods a stable landing spot.

## Alternative Solutions

### Option 2: Use Autoscaled Blue-Green Strategy
```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --strategy=AUTOSCALED_BLUE_GREEN \
  --enable-autoscaling \
  --total-min-nodes MIN --total-max-nodes MAX \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

**Advantage:** Creates the new (green) pool first, then drains the old (blue) pool. Eliminates musical chairs entirely by ensuring destination capacity exists before draining begins.

### Option 3: Pod Anti-Affinity (Workload-Level Fix)
Add this to your workload specs to prefer upgraded nodes:
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

## Why Musical Chairs Happens

1. **High maxSurge**: Too many nodes cordoned simultaneously
2. **Scheduler behavior**: Kubernetes scheduler places pods on first available node, not considering upgrade queue
3. **Timing**: Node cordoning happens faster than pod startup/stabilization
4. **No upgrade-aware scheduling**: The scheduler doesn't know which nodes are "safe" from future cordoning

## Best Practice: Sizing maxSurge

**Recommended formula:** `maxSurge = max(1, pool_size * 0.05)` (5% of pool size, minimum 1)

Examples:
- 10-node pool → `maxSurge=1`
- 40-node pool → `maxSurge=2` 
- 100-node pool → `maxSurge=5`

**Why 5%?** Balances upgrade speed with stability. Ensures upgraded nodes are available before the next batch drains.

## Monitoring the Fix

Watch the upgrade progress after applying the fix:
```bash
# Monitor node status during upgrade
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "Ready|NotReady|SchedulingDisabled"'

# Check for pods stuck in Pending
kubectl get pods -A | grep Pending

# Verify pods are landing on upgraded nodes
kubectl get pods -A -o wide | grep your-app-name
```

## Prevention for Future Upgrades

1. **Default to `maxSurge=1` for all node pools** unless you have specific performance requirements
2. **For large pools (100+ nodes):** Use percentage-based maxSurge (5%) rather than fixed numbers
3. **Consider autoscaled blue-green** for mission-critical workloads where musical chairs risk is unacceptable
4. **Test surge settings in dev/staging** before applying to production

The musical chairs problem is completely avoidable with proper maxSurge tuning. `maxSurge=1` is the safest default and will resolve your immediate issue.