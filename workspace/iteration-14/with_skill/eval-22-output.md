This is a classic node upgrade scheduling problem! The pods are bouncing between nodes because Kubernetes doesn't have visibility into GKE's upgrade plan - it just sees "schedulable nodes" and picks based on standard criteria (resource fit, affinity rules, etc.), not upgrade sequence.

## What's happening

GKE upgrades nodes in batches based on your `maxSurge`/`maxUnavailable` settings, but Kubernetes scheduler doesn't know which nodes are "next to be upgraded." So evicted pods can land on:
- Nodes scheduled for the next upgrade batch
- Nodes with the old version that haven't been touched yet
- Even nodes that were just cordoned but haven't started draining

This creates the "musical chairs" effect where pods migrate multiple times during a single upgrade.

## Immediate fixes

### Option 1: Use node selectors to prefer upgraded nodes
```bash
# Add a temporary nodeSelector to critical workloads
kubectl patch deployment YOUR_DEPLOYMENT -p '{
  "spec": {
    "template": {
      "spec": {
        "nodeSelector": {
          "cloud.google.com/gke-nodepool": "POOL_NAME"
        },
        "affinity": {
          "nodeAffinity": {
            "preferredDuringSchedulingIgnoredDuringExecution": [{
              "weight": 100,
              "preference": {
                "matchExpressions": [{
                  "key": "node.kubernetes.io/instance-type",
                  "operator": "In",
                  "values": ["TARGET_MACHINE_TYPE"]
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

### Option 2: Adjust surge settings to reduce churn
```bash
# Increase maxSurge, decrease maxUnavailable - more stable nodes available
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

This creates more "landing pad" nodes before starting to drain.

### Option 3: Switch to blue-green upgrade strategy
```bash
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --node-pool-soak-duration 300s
```

Blue-green eliminates the musical chairs problem entirely - all new nodes are created first, then workloads migrate once.

## Long-term prevention strategies

### 1. Use pod topology spread constraints
Add to your Deployment specs:
```yaml
spec:
  template:
    spec:
      topologySpreadConstraints:
      - maxSkew: 1
        topologyKey: node.kubernetes.io/instance-type
        whenUnsatisfiable: DoNotSchedule
        labelSelector:
          matchLabels:
            app: YOUR_APP
```

This spreads pods across node "generations" more evenly.

### 2. Configure pod disruption budgets appropriately
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: your-app-pdb
spec:
  minAvailable: 50%  # Not too restrictive
  selector:
    matchLabels:
      app: your-app
```

Overly restrictive PDBs (like `minAvailable: 90%`) can force all pods onto a few nodes, making them all victims of the same drain cycle.

### 3. Use node affinity to prefer stable nodes during upgrades
Create a DaemonSet that labels nodes by their "stability":
```yaml
# Node labeler DaemonSet
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: node-stability-labeler
spec:
  template:
    spec:
      containers:
      - name: labeler
        image: google/cloud-sdk:slim
        command: ["/bin/bash"]
        args:
        - -c
        - |
          NODE_NAME=$(hostname)
          # Label nodes that have been stable for >1 hour
          kubectl label node $NODE_NAME upgrade-stable=true --overwrite
```

Then use `nodeAffinity` to prefer `upgrade-stable=true` nodes.

## Monitoring the shuffle

Track pod migrations during upgrades:
```bash
# Watch pod locations in real-time
kubectl get pods -o wide --watch

# Count migrations per pod
kubectl get events --field-selector reason=Scheduled \
  --sort-by='.lastTimestamp' | \
  grep "Successfully assigned"
```

## Why blue-green is often the best solution

For workloads experiencing significant churn, **autoscaled blue-green** is the most elegant fix:
- Creates all new nodes first (green pool)
- Workloads migrate exactly once: old nodes → new nodes
- No intermediate shuffling between "about to be upgraded" nodes
- Supports longer graceful termination periods

The only downside is temporary 2x resource usage, but it eliminates all the scheduling chaos you're experiencing.

Would you like me to generate a specific runbook for switching your current upgrade to blue-green, or help you implement one of the nodeAffinity solutions?