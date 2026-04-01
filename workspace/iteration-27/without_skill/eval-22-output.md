You've hit the classic "musical chairs" problem during rolling node upgrades! This happens because the Kubernetes scheduler doesn't know which nodes are about to be drained - it just sees available capacity. Here's what's happening and how to fix it:

## Root Causes

1. **Scheduler blindness**: The scheduler picks nodes based on current capacity, not future drain plans
2. **Simultaneous draining**: Multiple nodes being drained at once with nowhere "safe" to land
3. **No node preference**: Pods don't distinguish between old and new nodes

## Solutions

### 1. **Sequence the Upgrade with Node Taints**

Taint nodes that are about to be upgraded to prevent new pods from landing there:

```bash
# Before starting drain, taint nodes in the "about to upgrade" group
kubectl taint nodes <node-name> upgrade-in-progress=true:NoSchedule

# Then drain normally
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data
```

### 2. **Use Node Selectors/Affinity for New Nodes**

Label your upgraded nodes and configure workloads to prefer them:

```yaml
# Label new nodes
kubectl label nodes <upgraded-node> node-pool-version=v2

# Update deployments to prefer upgraded nodes
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
              - key: node-pool-version
                operator: In
                values: ["v2"]
```

### 3. **Control Upgrade Batch Size**

```bash
# Upgrade one node at a time, wait for completion
for node in $(kubectl get nodes -l node-pool=old --no-headers -o custom-columns=NAME:.metadata.name); do
  echo "Upgrading $node"
  kubectl taint node $node upgrade-in-progress=true:NoSchedule
  kubectl drain $node --ignore-daemonsets --delete-emptydir-data --timeout=300s
  
  # Wait for node to be upgraded and ready
  while ! kubectl get node $node | grep -q "Ready"; do
    sleep 30
  done
  
  echo "$node upgrade complete"
done
```

### 4. **Pre-provision New Nodes**

Add new nodes before draining old ones:

```bash
# Scale up node pool first
kubectl scale --replicas=6 deployment/cluster-autoscaler  # if using CA
# Or manually add nodes

# Wait for new nodes to be ready
kubectl wait --for=condition=Ready node -l node-pool=new --timeout=600s

# Then start draining old nodes
```

### 5. **Use PodDisruptionBudgets Wisely**

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: my-app
---
# This ensures at least one pod stays running during the musical chairs
```

### 6. **Cluster Autoscaler Configuration**

If using cluster autoscaler, tune it for upgrades:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cluster-autoscaler
spec:
  template:
    spec:
      containers:
      - name: cluster-autoscaler
        command:
        - ./cluster-autoscaler
        - --scale-down-enabled=false  # Disable during upgrade
        - --scale-down-delay-after-add=10m
        - --scale-down-unneeded-time=10m
```

### 7. **Automated Solution Script**

Here's a comprehensive upgrade script:

```bash
#!/bin/bash
set -e

NODEPOOL_LABEL="node-pool=worker"
NEW_VERSION="v1.25"

echo "Starting safe node pool upgrade..."

# Step 1: Label existing nodes as old
kubectl label nodes -l $NODEPOOL_LABEL version=old --overwrite

# Step 2: Add new nodes (cloud-provider specific)
echo "Adding new nodes..."
# gcloud container node-pools create new-pool ... (for GKE)
# eksctl create nodegroup ... (for EKS)
# az aks nodepool add ... (for AKS)

# Step 3: Wait for new nodes
echo "Waiting for new nodes..."
kubectl wait --for=condition=Ready node -l version=new --timeout=900s

# Step 4: Drain old nodes one by one
OLD_NODES=$(kubectl get nodes -l version=old --no-headers -o custom-columns=NAME:.metadata.name)

for node in $OLD_NODES; do
    echo "Processing node: $node"
    
    # Taint node to prevent new scheduling
    kubectl taint node $node upgrade-in-progress=true:NoSchedule
    
    # Drain the node
    kubectl drain $node \
        --ignore-daemonsets \
        --delete-emptydir-data \
        --timeout=300s \
        --grace-period=30
    
    # Wait a bit for pods to stabilize
    sleep 30
    
    echo "Node $node drained successfully"
done

# Step 5: Remove old nodes from node pool
echo "Removing old nodes..."
# Cloud provider specific cleanup

echo "Upgrade complete!"
```

### 8. **Monitor Pod Movements**

Track the musical chairs effect:

```bash
# Watch pod movements in real-time
kubectl get events --sort-by='.lastTimestamp' --field-selector reason=Scheduled -w

# Count evictions
kubectl get events --field-selector reason=Evicted --sort-by='.lastTimestamp'
```

## Best Practices Going Forward

1. **Staged rollouts**: Never drain more than 25% of nodes simultaneously
2. **Capacity buffer**: Always maintain 20-30% excess capacity during upgrades
3. **Taint early**: Mark nodes for upgrade before starting the drain process
4. **Monitor closely**: Watch for pods bouncing between nodes
5. **Test with non-critical workloads first**

The key is controlling the scheduler's choices by either removing bad options (taints) or making good options more attractive (affinity/preferences).