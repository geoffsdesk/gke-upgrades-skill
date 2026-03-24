# Musical Chairs Problem - Pod Scheduling During Node Upgrades

You're experiencing the classic "musical chairs" anti-pattern during node pool upgrades. This happens when your `maxSurge` setting is too high relative to your pool size, causing multiple nodes to drain simultaneously before enough upgraded nodes are available to absorb the evicted pods.

## What's happening

**Root cause:** High `maxSurge` creates too many surge nodes at once, but GKE cordons and drains the old nodes **before** the new surge nodes are fully ready to receive pods. The scheduler places evicted pods on other old nodes that are also queued for draining.

**The cycle:**
1. GKE creates surge nodes (not yet Ready)
2. GKE cordons nodes A, B, C for draining
3. Pods from node A get scheduled to nodes B and C (still schedulable)
4. Node A completes drain and is deleted
5. Surge node from step 1 becomes Ready
6. GKE starts draining nodes B and C (which now have pods from node A)
7. Process repeats with pods bouncing between nodes

## Fix: Reduce maxSurge to ensure sequential availability

**Immediate fix:**
```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Why this works:** With `maxSurge=1`, only one surge node is created at a time. GKE waits for that surge node to become Ready and schedulable before cordoning the next old node. This ensures upgraded nodes are always available for evicted pods.

## Alternative approaches by scenario

### Small pools (≤20 nodes)
```bash
# Conservative: one node at a time
--max-surge-upgrade 1 --max-unavailable-upgrade 0
```

### Medium pools (20-100 nodes)
```bash
# Slightly faster but still safe
--max-surge-upgrade 2 --max-unavailable-upgrade 0
```

### Large pools (100+ nodes) with adequate quota
```bash
# Higher surge but cap at ~5% of pool size
# For 200-node pool: maxSurge=10
--max-surge-upgrade 10 --max-unavailable-upgrade 0
```

### GPU pools (fixed reservations, no surge capacity)
```bash
# Use maxUnavailable as the primary lever
--max-surge-upgrade 0 --max-unavailable-upgrade 1
```

## Monitoring the fix

**Watch node status during upgrade:**
```bash
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "(NAME|NODE_POOL_NAME)"'
```

**Check for pods landing on correct nodes:**
```bash
# Verify pods are scheduling to upgraded nodes
kubectl get pods -A -o wide | grep -v kube-system | head -20
```

**Look for the musical chairs pattern (should stop):**
```bash
kubectl get events -A --field-selector reason=FailedScheduling,reason=Scheduled \
  --sort-by='.lastTimestamp' | tail -10
```

## Why this happens more frequently now

**GKE's upgrade parallelism:** GKE can upgrade up to ~20 nodes simultaneously (increasing to 100 in future versions). High `maxSurge` settings combined with this parallelism can trigger musical chairs even in medium-sized pools.

**Node readiness timing:** Surge nodes must complete full startup (kubelet, CNI, system pods) before becoming schedulable. During this 2-3 minute window, old nodes may already be cordoned, forcing pods onto other soon-to-be-drained nodes.

## Prevention for future upgrades

**Sizing rule:** Set `maxSurge` as a percentage of pool size, not a fixed number:
- **Small pools (≤50 nodes):** 2-5% (minimum 1)
- **Large pools (50+ nodes):** 3-5% (capped at 10-20 based on upgrade parallelism)
- **GPU pools:** Use `maxUnavailable` instead of `maxSurge`

**Calculate maxSurge example:**
```bash
# For a 40-node pool at 5%:
# 40 * 0.05 = 2 nodes
--max-surge-upgrade 2
```

The trade-off is speed vs stability. Lower `maxSurge` means slower upgrades but eliminates the musical chairs problem and reduces resource pressure on the cluster.