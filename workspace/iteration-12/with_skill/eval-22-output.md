# Node Pool Musical Chairs Problem

This is a classic **surge upgrade scheduling issue** where pods keep getting evicted and rescheduled onto nodes that are also queued for upgrade. It happens when your surge settings and upgrade batch size don't provide enough stable "landing zones" for evicted pods.

## Root Cause Analysis

**Diagnose the current state:**
```bash
# Check surge settings
gcloud container node-pools describe NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --format="value(upgradeSettings.maxSurge,upgradeSettings.maxUnavailable)"

# See which nodes are cordoned (queued for upgrade)
kubectl get nodes -o wide | grep SchedulingDisabled

# Check pod placement patterns
kubectl get pods -A -o wide | grep -E "node-name"
```

## Why This Happens

1. **Insufficient surge capacity**: Your `maxSurge` is too small relative to pool size, so there aren't enough "safe" upgraded nodes
2. **Large upgrade batches**: GKE cordons nodes in batches, but if the batch size approaches your available capacity, pods have nowhere stable to land
3. **Anti-affinity rules**: Pod anti-affinity or topology spread constraints may be forcing pods onto soon-to-be-drained nodes
4. **Resource fragmentation**: Available nodes may lack sufficient resources for the evicted pods

## Immediate Fixes

### Option 1: Increase surge capacity (recommended)
```bash
# Calculate better surge settings
# For a 20-node pool: maxSurge=4 (20% of pool) gives you 4 stable nodes at any time
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 4 \
  --max-unavailable-upgrade 0
```

**Sizing guidance:**
- **Small pools (≤20 nodes)**: `maxSurge = 2-4 nodes` 
- **Medium pools (21-100 nodes)**: `maxSurge = 5-10% of pool size`
- **Large pools (100+ nodes)**: `maxSurge = 5% of pool size` (GKE's max batch concurrency is ~20 nodes anyway)

### Option 2: Use autoscaled blue-green upgrade
This eliminates the musical chairs problem entirely by keeping the old pool available while the new pool scales up:

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes MIN --total-max-nodes MAX \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

### Option 3: Pause and cordon manually (last resort)
If you need to stop the musical chairs immediately:

```bash
# Cancel current upgrade operation
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE
# Note the operation ID, then contact support to cancel it

# Manually cordon specific nodes to create stable landing zones
kubectl cordon NODE_NAME_1 NODE_NAME_2
# Let pods settle, then upgrade cordoned nodes manually
```

## Long-term Prevention

### 1. Right-size your surge settings
```bash
# Template for most workloads
# Pool size 10-50: maxSurge=2-5, maxUnavailable=0
# Pool size 50+: maxSurge=5-10% of pool size, maxUnavailable=0

# For stateful workloads: maxSurge=1, maxUnavailable=0
# For GPU pools: maxSurge=0, maxUnavailable=1 (GPU surge capacity is rare)
```

### 2. Check for problematic pod scheduling constraints
```bash
# Look for anti-affinity rules that limit pod placement
kubectl get deploy,sts -A -o yaml | grep -A 10 -B 5 "anti.*affinity"

# Check topology spread constraints
kubectl get deploy,sts -A -o yaml | grep -A 10 -B 5 "topologySpread"
```

**Fix overly restrictive scheduling:**
- Relax `requiredDuringSchedulingIgnoredDuringExecution` to `preferredDuringSchedulingIgnoredDuringExecution`
- Increase `maxSkew` in topology spread constraints
- Use `WhenUnsatisfiable: ScheduleAnyway` instead of `DoNotSchedule`

### 3. Resource request optimization
```bash
# Check if resource requests match actual usage
kubectl top pods -A --containers
kubectl describe nodes | grep -A 5 "Allocated resources"
```

Right-size resource requests to improve pod "packability" on available nodes.

## GPU Pool Special Case

For GPU pools, the musical chairs problem is worse because:
- GPU surge capacity is rare (no extra GPUs available)
- GPU workloads often have large resource requests
- GPU nodes can't be live-migrated

**GPU-specific fix:**
```bash
# Use maxUnavailable instead of maxSurge for GPU pools
gcloud container node-pools update GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

# This drains first, creates replacement, then moves to next node
# Slower but avoids the musical chairs problem with limited GPU capacity
```

## Validation

Monitor that pods are landing on stable nodes:
```bash
# Watch node status during upgrade
watch 'kubectl get nodes -o custom-columns=NAME:.metadata.name,STATUS:.status.conditions[?(@.type==\"Ready\")].status,VERSION:.status.nodeInfo.kubeletVersion | grep -v SchedulingDisabled'

# Check that evicted pods land on upgraded nodes
kubectl get events -A --field-selector reason=SuccessfulCreate -w
```

The musical chairs problem should resolve once you have sufficient surge capacity or use blue-green upgrade strategy. The key insight is that **pods need somewhere stable to land** — either newly created surge nodes or the old blue pool in a blue-green strategy.