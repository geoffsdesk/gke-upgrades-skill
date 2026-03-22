This is a classic surge upgrade scheduling problem! The pods are bouncing between nodes because the scheduler isn't aware of which nodes are "safe" (already upgraded) versus "about to be drained." Here's what's happening and how to fix it:

## Root cause: Scheduler lacks upgrade awareness

The Kubernetes scheduler sees all Ready nodes as valid targets, including nodes that are cordoned but still running pods (in the draining phase). Your pods land on these nodes, then get evicted again when that node's turn comes up in the upgrade sequence.

## Immediate fixes

### 1. Increase maxSurge to create more "safe harbor" nodes

```bash
# Create more upgraded nodes that won't be drained
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

**Why this works:** With higher surge, you have more brand-new upgraded nodes that are guaranteed safe landing spots. The scheduler will prefer these over the cordoned nodes.

### 2. Switch to blue-green upgrade strategy

```bash
# Cancel current upgrade if possible
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE

# Configure blue-green for next attempt
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-blue-green-upgrade \
  --blue-green-upgrade-policy-batch-soak-duration 60s
```

**Why this works:** Blue-green creates an entirely new pool of upgraded nodes first, then migrates everything at once. No musical chairs.

### 3. Node affinity to prefer upgraded nodes (advanced)

If you need to stick with surge, you can help the scheduler make better choices:

```bash
# Label the already-upgraded nodes
kubectl label nodes NODE_NAME upgrade-status=complete

# Add node affinity to your workloads
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
                  "key": "upgrade-status",
                  "operator": "In",
                  "values": ["complete"]
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

## Prevention for next time

### Configure optimal surge settings upfront

For different workload types:

```bash
# Stateless workloads - aggressive surge
gcloud container node-pools update stateless-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 0

# Stateful workloads - conservative surge
gcloud container node-pools update stateful-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### Use PDBs strategically

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: critical-app-pdb
spec:
  minAvailable: 75%  # Allows some disruption but maintains capacity
  selector:
    matchLabels:
      app: critical-app
```

This prevents too many pods from being evicted simultaneously, reducing the musical chairs effect.

## Monitoring the fix

```bash
# Watch pod movement patterns
kubectl get pods -A -o wide --watch

# Check which nodes are cordoned (being drained)
kubectl get nodes | grep SchedulingDisabled

# Monitor upgrade progress
watch 'gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=1'
```

## Why this happens more in some clusters

- **Large clusters:** More nodes = more opportunities for bad scheduling decisions
- **Mixed workloads:** Different eviction rates create uneven node availability
- **Tight resource utilization:** Less headroom means fewer "obvious" good nodes
- **Fast upgrade cycles:** Scheduler hasn't adapted to the changing node landscape

The **maxSurge increase** is usually the quickest fix since it creates obviously safe nodes that the scheduler will prefer. Blue-green is the most reliable long-term solution for workloads that can tolerate the resource doubling.