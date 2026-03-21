This is a classic "musical chairs" problem during GKE node pool upgrades! The issue is that your surge settings aren't providing stable landing spots for evicted pods. Here's what's happening and how to fix it:

## What's Causing This

**Root cause:** Your `maxSurge` is too low relative to `maxUnavailable`, so there aren't enough "safe" (already-upgraded or new) nodes to absorb the pods being evicted.

**The cycle:**
1. Node A gets cordoned and starts draining
2. Pods from Node A land on Node B (still old version)
3. Node B then gets cordoned and starts draining
4. Pods from Node B land on Node C or back to a new node replacing Node A
5. This continues until enough new nodes exist to break the cycle

## Immediate Fix: Increase Surge

**For stateless workloads (recommended):**
```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

This creates 3 new nodes before draining any old ones, giving pods stable landing spots.

**For resource-constrained environments:**
```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 1
```

This ensures at least 1 net-positive node capacity during the upgrade.

## Why This Happens More in Certain Scenarios

- **Small node pools (3-5 nodes):** Not enough nodes to create stable "islands" of upgraded capacity
- **Tightly packed clusters:** High pod density means every node matters
- **Default settings:** GKE's default `maxSurge=1, maxUnavailable=1` can create this shuffle pattern
- **Resource requests close to node capacity:** Pods can only fit on specific nodes, limiting landing options

## Alternative: Switch to Blue-Green

If surge capacity is limited or expensive:

```bash
# Enable blue-green upgrade strategy
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-blue-green-upgrade \
  --blue-green-upgrade-policy-batch-node-count=NODE_COUNT \
  --blue-green-upgrade-policy-batch-soak-duration=300s
```

Blue-green eliminates the musical chairs problem by keeping all old nodes available until the full replacement pool is ready.

## Monitoring the Fix

Watch the upgrade progress to confirm pods are landing stably:

```bash
# Monitor nodes by upgrade status
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "Ready|NotReady|SchedulingDisabled"'

# Check for pods not finding homes
kubectl get pods -A | grep Pending

# Monitor pod churn (should decrease after applying fix)
kubectl get events -A --field-selector reason=Scheduled | tail -10
```

## Prevention for Next Time

**For stateless workloads:**
- Always use `maxSurge ≥ 2` and `maxUnavailable=0`
- For large pools: `maxSurge=20%` or higher

**For stateful workloads:**
- Use `maxSurge=1, maxUnavailable=0` (conservative but avoids shuffle)
- Consider blue-green for mission-critical databases

**For mixed workloads:**
- Separate stateless and stateful workloads into different node pools
- Upgrade stateless pools with high surge, stateful pools conservatively

The key insight: **surge capacity must exceed drain rate** to create stable landing zones and break the musical chairs cycle.