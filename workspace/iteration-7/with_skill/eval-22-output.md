# Pod Musical Chairs During GKE Node Pool Upgrades

This is a classic **upgrade sequencing issue** where pods are being rescheduled to nodes that are themselves queued for upgrade, creating a continuous shuffle. Here's what's happening and how to fix it.

## Root Cause Analysis

**The problem:** GKE's node upgrade algorithm doesn't guarantee that pods land on "safe" (already upgraded) nodes. The scheduler sees all Ready nodes as valid targets, including nodes that are next in the upgrade queue.

**Why this happens:**
1. Node A gets cordoned and drained
2. Pods reschedule to Node B (still on old version, looks healthy)
3. Node B becomes the next upgrade target
4. Pods get evicted AGAIN and land on Node C
5. Repeat until pods eventually land on an upgraded node or the pool runs out of surge capacity

This is most common with:
- **Low surge settings** (`maxSurge=1`) — only one "safe" node exists at a time
- **Large node pools** — more opportunities for pods to land on "about to be upgraded" nodes  
- **High pod density** — many pods competing for limited upgraded nodes
- **Slow pod startup** — pods don't become Ready quickly enough to reserve space

## Immediate Fixes

### 1. Increase surge capacity (most effective)

```bash
# Increase maxSurge to create more "safe landing spots"
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

**Why this works:** More nodes upgrade simultaneously = more "safe" nodes available as landing spots. Pods are more likely to land on already-upgraded nodes.

**Recommended surge settings by pool type:**
- **Stateless workloads:** `maxSurge=3-5` (or higher for large pools)
- **Stateful workloads:** `maxSurge=2, maxUnavailable=0` (conservative but better than 1)
- **Large pools (50+ nodes):** `maxSurge=10-20` (GKE's max parallelism is ~20 anyway)
- **GPU pools:** Use `maxUnavailable` mode instead — see GPU section below

### 2. Switch to blue-green upgrade strategy

```bash
# Cancel current surge upgrade
# Then use GKE's native blue-green approach
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoupgrade \
  --enable-auto-scaling \
  --node-pool-soak-duration 0s \
  --blue-green-settings max-surge=0,max-unavailable=100%,node-pool-soak-duration=0s
```

**Why this works:** Blue-green creates a completely separate replacement pool, migrates all pods at once, then removes the old pool. No musical chairs because there's always a full "safe" pool available.

### 3. Add node affinity to prefer upgraded nodes

```yaml
# Add to critical workloads during upgrade
spec:
  template:
    spec:
      affinity:
        nodeAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            preference:
              matchExpressions:
              - key: node.kubernetes.io/instance-type  # Any stable node label
                operator: Exists
```

This gives the scheduler a preference but won't prevent all reshuffling.

## GPU Pool Special Case

**GPU nodes have unique constraints** that make musical chairs worse:

- **No live migration** — every upgrade requires pod restart
- **Surge capacity often unavailable** — A100/H100 reservations may not have headroom
- **Long startup times** — GPU driver loading takes 2-5 minutes

**Fix for GPU pools:**
```bash
# Use maxUnavailable mode instead of surge
gcloud container node-pools update GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2  # Adjust based on pool size
```

Or use blue-green if you have capacity for a full replacement pool:
```bash
gcloud container node-pools update GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-blue-green-update \
  --blue-green-settings max-surge=0,max-unavailable=100%
```

## Monitoring the Fix

Watch for the musical chairs pattern to stop:

```bash
# Monitor pod scheduling patterns
kubectl get events -A --field-selector reason=Scheduled -w

# Watch node upgrade progress  
watch 'kubectl get nodes -o custom-columns="NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,READY:.status.conditions[?(@.type==\"Ready\")].status"'

# Check if pods are staying put
kubectl get pods -A -o wide --watch | grep -E "Running.*NODE_NAME"
```

**Good signs:**
- Fewer `Scheduled` events per pod (pods land once and stay)
- Pods clustering on already-upgraded nodes
- Faster overall upgrade completion

## Prevention for Future Upgrades

**1. Default to higher surge values** — `maxSurge=1` is conservative for development but causes musical chairs in production.

**2. Consider blue-green as default** for critical workloads that can't tolerate multiple evictions.

**3. Use skip-level node upgrades** where possible (e.g., 1.28 → 1.30 directly) to reduce total disruption.

**4. Implement proper PodDisruptionBudgets** — they don't prevent musical chairs but they limit how many pods get shuffled simultaneously.

The fundamental fix is **more surge capacity** or **blue-green strategy**. This gives pods stable landing spots instead of a constantly shifting upgrade queue.