This is a classic "pod shuffle" problem during node pool upgrades! The issue occurs because your pods are landing on nodes that are marked for upgrade but haven't been cordoned/drained yet. Here's what's happening and how to fix it:

## Root Cause Analysis

```bash
# Check the upgrade status and node conditions
kubectl get nodes -o wide --show-labels
kubectl describe nodes | grep -E "(Taints|Unschedulable)"

# See which nodes are in the upgrade queue
kubectl get nodes -l node.kubernetes.io/instance-type=your-type -o custom-columns=NAME:.metadata.name,STATUS:.status.conditions[-1].type,SCHEDULABLE:.spec.unschedulable
```

## Solutions

### 1. **Use Node Selectors/Affinity for Stable Placement**

```yaml
# Deploy pods with affinity for upgraded nodes
apiVersion: apps/v1
kind: Deployment
metadata:
  name: your-app
spec:
  template:
    spec:
      affinity:
        nodeAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            preference:
              matchExpressions:
              - key: node.kubernetes.io/instance-type
                operator: In
                values: ["new-instance-type"]  # or upgraded node pool
          - weight: 50
            preference:
              matchExpressions:
              - key: kubernetes.io/arch
                operator: In
                values: ["amd64"]
```

### 2. **Control Upgrade Order with Taints**

```bash
# Pre-taint nodes that will be upgraded to prevent new pods
kubectl taint nodes node-to-upgrade upgrade-in-progress=true:NoSchedule

# Create a new node pool first, then upgrade
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-strategy
data:
  strategy: |
    1. Create new node pool
    2. Wait for nodes to be ready
    3. Taint old nodes
    4. Drain old nodes
    5. Delete old node pool
EOF
```

### 3. **Use PodDisruptionBudgets for Better Control**

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: app-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: your-app
---
# This slows down the drain process, giving pods time to land properly
```

### 4. **Implement Staged Upgrades**

```bash
# For managed clusters (EKS/GKE/AKS), use rolling upgrade settings
# EKS example:
aws eks update-nodegroup \
    --cluster-name your-cluster \
    --nodegroup-name your-nodegroup \
    --update-config maxUnavailablePercentage=25 \
    --scaling-config minSize=3,maxSize=6,desiredSize=4

# GKE example:
gcloud container node-pools update your-pool \
    --cluster=your-cluster \
    --max-surge=1 \
    --max-unavailable=1
```

### 5. **Monitor and Control with Custom Script**

```bash
#!/bin/bash
# upgrade-coordinator.sh

CLUSTER_NAME="your-cluster"
OLD_POOL="old-pool"
NEW_POOL="new-pool"

# 1. Create new node pool first
echo "Creating new node pool..."
# Your node pool creation command here

# 2. Wait for new nodes to be ready
echo "Waiting for new nodes..."
kubectl wait --for=condition=Ready nodes -l node-pool=$NEW_POOL --timeout=600s

# 3. Taint old nodes to prevent new scheduling
echo "Tainting old nodes..."
kubectl taint nodes -l node-pool=$OLD_POOL upgrade=true:NoSchedule

# 4. Drain nodes one by one with delays
for node in $(kubectl get nodes -l node-pool=$OLD_POOL -o name); do
    echo "Draining $node..."
    kubectl drain $node --ignore-daemonsets --delete-emptydir-data --force --grace-period=60
    
    # Wait for pods to stabilize before next node
    sleep 120
    
    # Check if pods landed on new nodes
    kubectl get pods -A -o wide | grep $NEW_POOL
done
```

### 6. **Use Cluster Autoscaler Annotations**

```yaml
# On your deployments, prefer newer nodes
apiVersion: apps/v1
kind: Deployment
metadata:
  name: your-app
  annotations:
    cluster-autoscaler.kubernetes.io/safe-to-evict: "true"
spec:
  template:
    metadata:
      annotations:
        cluster-autoscaler.kubernetes.io/safe-to-evict: "true"
    spec:
      tolerations:
      - key: "upgrade"
        operator: "Equal"
        value: "true"
        effect: "NoSchedule"
        # This allows pods to run on nodes being upgraded if needed
```

### 7. **Pre-scale Strategy**

```bash
# Before upgrade, scale up the new node pool
kubectl scale deployment cluster-autoscaler --replicas=0 -n kube-system
# Manually add nodes to ensure capacity

# Then start the upgrade process
# After upgrade, re-enable autoscaler
kubectl scale deployment cluster-autoscaler --replicas=1 -n kube-system
```

## Best Practices for Future Upgrades

1. **Always create new capacity before removing old**
2. **Use gradual rollouts** (max 25% unavailable)
3. **Monitor pod placement** during upgrades
4. **Set appropriate PDBs** for critical applications
5. **Use node affinity** to guide pod placement
6. **Test upgrade process** in staging first

## Quick Fix for Current Situation

```bash
# Emergency fix: Scale up new nodes and taint remaining old ones
kubectl taint nodes -l old-node-pool=true upgrade=in-progress:NoSchedule
kubectl get pods -A -o wide | grep old-node-pool  # Check what's still there
```

The key is to ensure new capacity exists and is preferred before starting the drain process!