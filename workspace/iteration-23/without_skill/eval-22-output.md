This is a classic node pool upgrade issue! You're experiencing what happens when the cluster doesn't have enough "stable" capacity or when the upgrade process isn't properly coordinated. Here's what's happening and how to fix it:

## Root Causes

1. **Insufficient surge capacity** - Not enough new nodes available before draining starts
2. **Poor upgrade ordering** - Multiple nodes being drained simultaneously
3. **Lack of pod scheduling constraints** - Pods can land on any "ready" node, even if it's queued for upgrade

## Solutions

### 1. Configure Proper Surge Settings

**For managed node groups (EKS, GKE, AKS):**

```yaml
# EKS example
apiVersion: eksctl.io/v1alpha5
kind: ClusterConfig
metadata:
  name: my-cluster
nodeGroups:
  - name: worker-nodes
    updateConfig:
      maxUnavailablePercentage: 25  # Only drain 25% at a time
    # OR
    updateConfig:
      maxUnavailable: 1  # Only drain 1 node at a time
```

**For GKE:**
```bash
gcloud container node-pools update POOL_NAME \
    --cluster=CLUSTER_NAME \
    --max-surge=2 \
    --max-unavailable=1
```

### 2. Use Blue-Green Node Pool Strategy

Create new node pool before removing old one:

```bash
# 1. Create new node pool
kubectl apply -f new-nodepool.yaml

# 2. Wait for nodes to be ready
kubectl wait --for=condition=Ready nodes -l node-pool=new-pool

# 3. Cordon old nodes
kubectl get nodes -l node-pool=old-pool -o name | xargs kubectl cordon

# 4. Drain old nodes gradually
for node in $(kubectl get nodes -l node-pool=old-pool -o name); do
  kubectl drain $node --ignore-daemonsets --delete-emptydir-data --grace-period=300
  sleep 60  # Wait between drains
done

# 5. Delete old node pool
```

### 3. Add Node Selectors/Affinity

Prevent pods from landing on nodes about to be upgraded:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: critical-app
spec:
  template:
    spec:
      nodeSelector:
        node-lifecycle: "stable"  # Only schedule on stable nodes
      # OR use node affinity
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - key: node-pool-version
                operator: In
                values: ["v1.28", "v1.29"]  # Specify acceptable versions
```

### 4. Label Nodes During Upgrade

```bash
# Label old nodes to prevent new scheduling
kubectl get nodes -l node-pool=old-pool -o name | \
  xargs -I {} kubectl label {} node-lifecycle=upgrading

# Update your pod specs to avoid these nodes
nodeSelector:
  node-lifecycle: "stable"
```

### 5. Use PodDisruptionBudgets

Prevent too many pods from being evicted simultaneously:

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  minAvailable: 50%  # Keep at least 50% running
  selector:
    matchLabels:
      app: my-app
```

### 6. Staged Upgrade Script

Here's a controlled upgrade approach:

```bash
#!/bin/bash
set -e

CLUSTER_NAME="my-cluster"
OLD_POOL="old-nodepool"
NEW_POOL="new-nodepool"

echo "Starting controlled node pool upgrade..."

# 1. Create new node pool with surge capacity
echo "Creating new node pool..."
# Add your node pool creation command here

# 2. Wait for new nodes
echo "Waiting for new nodes to be ready..."
kubectl wait --for=condition=Ready \
  --timeout=600s \
  nodes -l node-pool=$NEW_POOL

# 3. Label old nodes
echo "Labeling old nodes as upgrading..."
kubectl label nodes -l node-pool=$OLD_POOL node-lifecycle=upgrading

# 4. Drain nodes one by one
echo "Draining old nodes..."
OLD_NODES=$(kubectl get nodes -l node-pool=$OLD_POOL -o name)
for node in $OLD_NODES; do
  echo "Draining $node..."
  kubectl drain $node \
    --ignore-daemonsets \
    --delete-emptydir-data \
    --grace-period=300 \
    --timeout=600s
  
  # Wait and verify pods rescheduled successfully
  sleep 30
  
  echo "Checking pod health..."
  kubectl get pods --all-namespaces --field-selector=status.phase!=Running,status.phase!=Succeeded
  
  read -p "Continue with next node? (y/n) " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
  fi
done

echo "Upgrade completed successfully!"
```

### 7. Monitor and Validate

Add monitoring during upgrades:

```bash
# Watch pod distribution
watch 'kubectl get pods -o wide --all-namespaces | grep -E "(Pending|ContainerCreating|Terminating)"'

# Monitor node readiness
kubectl get nodes -o custom-columns=NAME:.metadata.name,STATUS:.status.conditions[-1].type,VERSION:.status.nodeInfo.kubeletVersion,POOL:.metadata.labels.node-pool
```

## Best Practices Going Forward

1. **Always configure surge capacity** before upgrades
2. **Use gradual rollout strategies** (max 25% nodes at once)
3. **Implement proper PDBs** for critical applications
4. **Label nodes appropriately** during lifecycle events
5. **Test upgrade procedures** in non-production first
6. **Monitor resource capacity** throughout the process

The key is ensuring you have enough "landing spots" (stable nodes) before you start "removing chairs" (draining nodes)!