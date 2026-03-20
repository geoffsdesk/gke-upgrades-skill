This is the classic "pod shuffle" or "musical chairs" problem during node pool upgrades. Your pods are bouncing between nodes that are all in the upgrade queue instead of landing on stable, already-upgraded nodes. Here's what's happening and how to fix it.

## Root Cause

GKE's upgrade process creates a "wave" of nodes being cordoned/drained simultaneously (up to ~20 nodes in parallel). When a pod gets evicted from Node A, the scheduler sees Node B as available, but Node B is also queued for upgrade and will drain the pod again shortly. The pod never gets a chance to land on a truly stable node.

This happens because:
- **Cordon timing**: Nodes are cordoned at the start of their upgrade slot, but may not drain immediately
- **Scheduler visibility**: The scheduler can't see which nodes are "next in line" for upgrade
- **Default surge settings**: `maxSurge=1, maxUnavailable=0` creates too few stable landing spots

## Fix 1: Increase surge capacity (immediate relief)

Create more "safe harbor" nodes by increasing `maxSurge`:

```bash
# Current settings
gcloud container node-pools describe NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --format="value(upgradeSettings.maxSurge,upgradeSettings.maxUnavailable)"

# Increase surge for more stable nodes
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

**Why this works**: With `maxSurge=3`, you have 3 freshly upgraded nodes ready to accept pods before the next batch of 3 gets cordoned.

## Fix 2: Add pod disruption budgets with better timing

```bash
# Check current PDBs
kubectl get pdb -A -o wide

# For each critical workload, ensure PDB allows some disruption but not total chaos:
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  minAvailable: 75%  # Allow 25% disruption, prevents total shuffle
  selector:
    matchLabels:
      app: my-app
```

## Fix 3: Use node affinity to prefer stable nodes

Add temporary node affinity to prefer already-upgraded nodes:

```bash
# Check which nodes are on the target version
kubectl get nodes -o wide

# Add preferred affinity to deployments (example):
kubectl patch deployment MY_DEPLOYMENT -p '
{
  "spec": {
    "template": {
      "spec": {
        "affinity": {
          "nodeAffinity": {
            "preferredDuringSchedulingIgnoredDuringExecution": [
              {
                "weight": 100,
                "preference": {
                  "matchExpressions": [
                    {
                      "key": "kubernetes.io/version", 
                      "operator": "In",
                      "values": ["TARGET_VERSION"]
                    }
                  ]
                }
              }
            ]
          }
        }
      }
    }
  }
}'
```

## Fix 4: Pause and let current wave complete

If the shuffle is severe, pause the upgrade to let the current batch finish:

```bash
# You can't pause a running upgrade, but you can prevent new nodes from starting
# by temporarily setting maxSurge=0 (this won't affect nodes already upgrading)
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

# Wait for current batch to complete, then restore higher surge
# Monitor: kubectl get nodes | grep -E "Ready|SchedulingDisabled"
```

## Monitor the fix

```bash
# Watch pods finding homes on stable nodes
kubectl get pods -A -o wide | grep -v Terminating

# Track upgrade progress
kubectl get nodes -L kubernetes.io/version --sort-by=.metadata.creationTimestamp

# Verify pods aren't bouncing
kubectl get events -A --field-selector reason=Started | tail -20
```

## Prevention for next time

1. **Start with higher surge**: `maxSurge=2-3` for most pools, higher for large clusters
2. **Size surge to workload needs**: If you have 100 replicas of an app, ensure surge creates enough nodes to host them
3. **Pre-configure PDBs**: Don't let 100% of an app's pods be eligible for simultaneous eviction
4. **Stagger workload density**: Don't pack critical apps too tightly on individual nodes

## Why blue-green doesn't solve this

Blue-green upgrades avoid the musical chairs problem entirely by creating a completely separate node pool, but they:
- Require 2x the compute quota temporarily
- Are slower due to the full pool recreation
- May hit resource availability issues for GPU/large machine types

For most workloads, fixing surge settings is more practical than switching strategies mid-upgrade.

The key insight: **you need enough "safe harbor" capacity (upgraded nodes) to absorb evicted pods before the next wave of evictions begins**.