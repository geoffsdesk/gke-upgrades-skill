# Musical Chairs Problem During GKE Node Upgrades

This is a classic "musical chairs" scheduling issue during surge upgrades. Here's what's happening and how to fix it.

## Root Cause Analysis

**What's happening:**
1. GKE creates surge nodes and starts draining multiple nodes simultaneously (based on your `maxSurge` setting)
2. Pods evicted from Node A land on Node B
3. Node B is also in the "to be drained" queue, so those pods get evicted again
4. This creates a cascade of pod shuffling instead of stable placement on upgraded nodes

**Why it happens:**
- High `maxSurge` values (e.g., 10+ nodes) can drain many nodes before enough upgraded nodes are available
- Kubernetes scheduler doesn't prefer "safe" (already upgraded) nodes over "temporary" (about to be drained) nodes
- Pod anti-affinity rules or resource constraints may force scheduling onto soon-to-be-drained nodes

## Immediate Fix: Reduce maxSurge

The most effective solution is to reduce `maxSurge` so upgraded nodes are available before the next batch drains:

```bash
# Reduce to maxSurge=1 for conservative, sequential upgrades
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# This ensures: create 1 upgraded node → drain 1 old node → repeat
# Pods always have a stable upgraded node to land on
```

**For larger pools where maxSurge=1 is too slow:**
```bash
# Use maxSurge = 2-5% of pool size, minimum 2
# Example: 100-node pool → maxSurge=3
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

## Alternative Solutions

### Option 1: Switch to Autoscaled Blue-Green (Recommended for large pools)

Autoscaled blue-green completely avoids the musical chairs problem by cordoning the entire old pool and scaling up replacement nodes based on demand:

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes MIN_NODES \
  --total-max-nodes MAX_NODES \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

**Advantages:**
- No pod shuffling — old nodes are cordoned, new nodes scale up as needed
- Respects longer `terminationGracePeriodSeconds` (unlike surge's 1-hour limit)
- More cost-effective than standard blue-green (doesn't require 2x resources)

### Option 2: Pod Anti-Affinity to Prefer Upgraded Nodes

Add pod anti-affinity rules to prefer nodes with newer versions:

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
              - key: node.kubernetes.io/kubelet-version
                operator: In
                values: ["v1.31.1-gke.1678000"]  # Target version
```

### Option 3: Taint-Based Scheduling Control

Apply temporary taints to nodes being drained and ensure workloads can tolerate them:

```bash
# Manually taint nodes before they're drained (advanced)
kubectl taint nodes NODE_NAME upgrade=draining:NoSchedule
```

## Monitoring the Fix

Watch upgrade progress to confirm pods land on stable nodes:

```bash
# Monitor node versions and pod distribution
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | head -20; echo "---"; kubectl get pods -A -o wide | grep -v Running | head -10'

# Check for pods in Pending state (indicates musical chairs resolved)
kubectl get pods -A --field-selector=status.phase=Pending

# Verify upgrade progress
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=1
```

## Prevention for Future Upgrades

1. **Use percentage-based maxSurge:** Scale with pool size (e.g., 5% of pool, minimum 1, maximum 20)
2. **Consider autoscaled blue-green for large pools:** Especially pools with 100+ nodes or long-running workloads
3. **Test surge settings in staging:** Validate pod placement behavior before production upgrades
4. **Monitor PDB constraints:** Overly restrictive PDBs can force scheduling onto suboptimal nodes

## Why This Matters

Musical chairs causes:
- **Extended upgrade times** — pods restart multiple times instead of once
- **Service disruption** — pods may be unavailable longer than expected
- **Resource waste** — CPU/memory churn from repeated scheduling
- **Potential data loss** — if stateful pods restart multiple times

The fix ensures pods migrate cleanly to stable, upgraded nodes in a single hop.