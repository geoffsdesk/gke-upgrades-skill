# Pod Shuffling During Node Pool Upgrades

You're experiencing the "musical chairs" problem where pods keep moving between nodes that are all scheduled for upgrade. This is a common issue with GKE's default surge upgrade strategy when the surge settings aren't optimized for your workload patterns.

## What's happening

**Root cause:** GKE is cordoning and draining nodes faster than it's creating replacement nodes, so evicted pods land on nodes that haven't been cordoned yet but are still in the "to be upgraded" queue.

**Default behavior:** GKE's surge upgrade processes nodes in batches. With default settings (`maxSurge=1, maxUnavailable=1`), you get:
1. Create 1 new node
2. Cordon 1 old node  
3. Drain pods to available capacity (including other old nodes)
4. Delete the drained node
5. Repeat

The problem is that "available capacity" includes old nodes that haven't been cordoned yet.

## Immediate fixes

### Option 1: Increase surge capacity (recommended)
```bash
# Stop the current upgrade if it's running
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES"

# Increase surge, eliminate unavailable
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

This ensures you always have more new nodes available than old nodes being drained simultaneously.

### Option 2: Switch to blue-green upgrade
```bash
# Cancel current upgrade
gcloud container operations cancel OPERATION_ID --zone ZONE

# Switch to blue-green strategy
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --node-pool-soak-duration 10m \
  --enable-blue-green-upgrade
```

Blue-green creates ALL replacement nodes first, then gradually shifts traffic.

### Option 3: Use autoscaled blue-green (preview)
```bash
# Best for cost-sensitive workloads
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaled-blue-green-upgrade
```

This scales up green nodes based on demand as blue nodes are drained.

## Why this happens more with certain workload patterns

**Anti-affinity rules**: Pods with anti-affinity spread across many nodes, making them more likely to land on nodes in the upgrade queue.

**Large pods with tight resource requests**: Fewer placement options mean higher chance of landing on upgrade-bound nodes.

**Cluster autoscaler interaction**: If autoscaler is scaling up during the upgrade, new nodes compete with surge nodes for pod placement.

## Prevention strategies

### Right-size your surge settings
```bash
# For stateless workloads - aggressive surge
--max-surge-upgrade 5 --max-unavailable-upgrade 0

# For mixed workloads - conservative surge  
--max-surge-upgrade 2 --max-unavailable-upgrade 0

# For GPU/resource-constrained - drain-first approach
--max-surge-upgrade 0 --max-unavailable-upgrade 1
```

### Use node selectors strategically
```yaml
# Pin critical workloads to already-upgraded nodes during the upgrade window
nodeSelector:
  cloud.google.com/gke-node-version: "TARGET_VERSION"
```

### Configure pod disruption budgets appropriately
```yaml
# Prevent too many replicas being moved simultaneously
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  minAvailable: 75%  # Keep most replicas running
  selector:
    matchLabels:
      app: my-app
```

## Monitoring the fix

```bash
# Watch node upgrade progress and pod distribution
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool && echo "=== Pod distribution ===" && kubectl get pods -A -o wide --sort-by=".spec.nodeName" | grep NODE_POOL_NAME'

# Check for pods landing on nodes with different versions
kubectl get pods -A -o custom-columns=POD:.metadata.name,NODE:.spec.nodeName,NODE_VERSION:.status.hostIP --no-headers | \
  while read pod node version; do 
    kubectl get node $node -o jsonpath='{.status.nodeInfo.kubeletVersion}' 2>/dev/null && echo " $pod"
  done
```

## Future upgrade planning

For your next upgrade:
1. **Start with higher surge settings** - begin with `maxSurge=3, maxUnavailable=0` for stateless workloads
2. **Consider blue-green for critical workloads** - eliminates the musical chairs problem entirely  
3. **Pause cluster autoscaler** during upgrades to avoid competing node creation
4. **Upgrade during low-traffic windows** when fewer pods are being created/rescheduled

The musical chairs problem is solvable - it's primarily a configuration issue rather than a fundamental GKE limitation. Blue-green upgrades completely eliminate it, while properly tuned surge settings minimize it for most workloads.