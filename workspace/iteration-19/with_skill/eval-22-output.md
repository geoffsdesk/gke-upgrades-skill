This is a classic "musical chairs" problem during GKE node pool upgrades! Here's what's happening and how to fix it:

## Root Cause

When `maxSurge` is set too high, GKE cordons and drains multiple nodes simultaneously **before** the surge nodes are fully ready. The scheduler sees the draining nodes as "available" (they're cordoned but pods are still running) and places evicted pods on them, only to evict them again when those nodes start draining.

**Example scenario:**
- Node pool: 10 nodes
- `maxSurge=3, maxUnavailable=0`  
- GKE creates 3 surge nodes but cordons nodes 1, 2, 3 immediately
- Pods from node 1 land on node 2, pods from node 2 land on node 3, pods from node 3 land on node 1
- Musical chairs ensues until surge nodes are Ready

## Primary Fix: Reduce maxSurge to 1

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Why this works:**
- Creates 1 surge node at a time
- Waits for it to be Ready before draining the next node
- Ensures upgraded nodes are always available as landing spots
- Slower but eliminates musical chairs

## Alternative: Use Autoscaled Blue-Green

If the musical chairs problem persists or you need faster upgrades:

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes MIN --total-max-nodes MAX \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25
```

**Why autoscaled blue-green avoids this:**
- Creates the entire green pool first
- Cordons the blue pool only after green nodes are Ready
- Pods always land on stable, non-draining nodes

## Immediate Mitigation (if upgrade is stuck)

If your upgrade is currently stuck in musical chairs:

```bash
# 1. Check which nodes are being drained
kubectl get nodes -o wide --sort-by='.metadata.creationTimestamp'

# 2. Manually cordon nodes that aren't upgraded yet to stop new pod placement
kubectl cordon NODE_NAME

# 3. Force pods to land on upgraded nodes using node affinity
kubectl patch deployment DEPLOYMENT_NAME -p '
{
  "spec": {
    "template": {
      "spec": {
        "affinity": {
          "nodeAffinity": {
            "preferredDuringSchedulingIgnoredDuringExecution": [{
              "weight": 100,
              "preference": {
                "matchExpressions": [{
                  "key": "node.kubernetes.io/instance-type",
                  "operator": "Exists"
                }]
              }
            }]
          }
        }
      }
    }
  }
}'
```

## Prevention for Future Upgrades

**For most workloads:**
```bash
# Conservative, reliable settings
--max-surge-upgrade 1 --max-unavailable-upgrade 0
```

**For large node pools (100+ nodes):**
```bash
# Use percentage-based surge, still conservative
--max-surge-upgrade 5% --max-unavailable-upgrade 0
# This gives you 5 surge nodes on a 100-node pool
```

**For GPU pools with fixed reservations:**
```bash
# No surge capacity available, use drain-first
--max-surge-upgrade 0 --max-unavailable-upgrade 1
```

## Why This Happens More with Certain Workloads

- **High replica count deployments** create more pod movement
- **Workloads without resource requests** can land anywhere
- **Missing pod anti-affinity rules** allow clustering on draining nodes
- **Cluster autoscaler scaling up** during upgrades can create new nodes at the old version

## Monitoring Musical Chairs

```bash
# Watch pod placement in real-time
watch 'kubectl get pods -A -o wide | grep -E "NODE_NAME_1|NODE_NAME_2|NODE_NAME_3"'

# Check for pods stuck in Terminating
kubectl get pods -A --field-selector=status.phase=Running | grep Terminating

# See which nodes are cordoned
kubectl get nodes | grep SchedulingDisabled
```

The key insight: **maxSurge controls CREATION speed, but GKE cordons nodes immediately**. The mismatch between surge node readiness and cordon timing causes the musical chairs. Setting `maxSurge=1` synchronizes these operations and eliminates the problem.