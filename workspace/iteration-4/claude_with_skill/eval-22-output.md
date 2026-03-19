This is a classic "musical chairs" problem during GKE upgrades! The issue is that your surge settings aren't providing enough stable capacity, so pods keep getting shuffled between nodes that are all in the upgrade queue.

## What's happening

During a surge upgrade, GKE:
1. Creates new nodes with the target version
2. Starts draining old nodes in parallel
3. Pods get evicted and reschedule to "any available node"

But if `maxSurge` is too low or `maxUnavailable` is too high, there aren't enough stable (already-upgraded) nodes to absorb the evicted pods. They land on old nodes that are also queued for drain, creating the shuffle.

## Quick fix - adjust surge settings

```bash
# Stop the musical chairs - prioritize stability over speed
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0

# This ensures 3 new nodes are always available before any old nodes drain
```

The key insight: **`maxUnavailable=0`** prevents any old nodes from draining until new nodes are ready to receive their pods.

## Monitor the fix

```bash
# Watch nodes by version - you should see clear separation
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,STATUS:.status.conditions[?(@.type==\"Ready\")].status

# Verify pods aren't bouncing between Terminating states
kubectl get pods -A | grep Terminating | wc -l
```

## Optimal surge settings by workload type

For future upgrades, tailor your settings to prevent this:

**Stateless workloads (web apps, APIs):**
```bash
--max-surge-upgrade 2-3 \
--max-unavailable-upgrade 0
# Fast upgrades, pods can land anywhere safe
```

**Stateful workloads (databases, persistent storage):**
```bash
--max-surge-upgrade 1 \
--max-unavailable-upgrade 0
# Conservative, let PDBs protect data integrity
```

**Large node pools (>10 nodes):**
```bash
--max-surge-upgrade 5-10 \
--max-unavailable-upgrade 0
# More parallel capacity to avoid the shuffle
```

## Why this happens

The Kubernetes scheduler doesn't have "upgrade awareness" - it just sees "available nodes" and schedules there. GKE's upgrade controller operates independently, marking nodes for drain based on the surge/unavailable settings, not the scheduler's decisions.

## Prevention for next time

Add this to your pre-upgrade checklist:
```
Node Pool Sizing
- [ ] maxSurge ≥ 20% of pool size (minimum 2 for small pools)
- [ ] maxUnavailable = 0 (unless you need faster completion)
- [ ] Sufficient compute quota for surge nodes
```

The upgrade should stabilize within 10-15 minutes after applying the new surge settings. Pods will stop shuffling and start landing on the stable, already-upgraded nodes.