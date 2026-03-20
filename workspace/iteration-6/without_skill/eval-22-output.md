This is a classic node pool upgrade scheduling issue! You're experiencing what I call "upgrade musical chairs" where pods keep landing on nodes in the "to-be-upgraded" queue instead of the safe, already-upgraded nodes.

## What's Happening

The root causes are typically:

1. **Upgrade strategy is too aggressive** - draining multiple nodes simultaneously
2. **Scheduler lacks upgrade awareness** - it sees "ready" nodes that are actually queued for upgrade
3. **Resource constraints** - upgraded nodes might not have enough capacity
4. **Affinity/anti-affinity rules** forcing pods to specific node groups

## Solutions

### 1. **Adjust Upgrade Strategy (Immediate Fix)**

```yaml
# For GKE
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerNodePool
spec:
  upgradeSettings:
    maxSurge: 1
    maxUnavailable: 0  # Don't drain until new nodes are ready
```

```yaml
# For EKS (managed node groups)
apiVersion: eks.aws.crossplane.io/v1alpha1
kind: NodeGroup
spec:
  updateConfig:
    maxUnavailablePercentage: 25  # Reduce from default
```

### 2. **Use Node Taints During Upgrades**

```bash
# Manually taint nodes scheduled for upgrade
kubectl taint nodes node-to-upgrade upgrade=in-progress:NoSchedule

# Or use a script to taint all old-version nodes
kubectl get nodes -o json | jq -r '.items[] | select(.status.nodeInfo.kubeletVersion != "v1.28.0") | .metadata.name' | \
xargs -I {} kubectl taint nodes {} upgrade=pending:NoSchedule
```

### 3. **Implement Pod Disruption Budgets**

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  minAvailable: 1  # or use maxUnavailable: 25%
  selector:
    matchLabels:
      app: my-app
```

### 4. **Pre-scale Before Upgrade**

```bash
# Add extra nodes before starting upgrade
kubectl scale --replicas=5 deployment/cluster-autoscaler

# Or manually add nodes to handle the shuffle
gcloud container clusters resize my-cluster --num-nodes=6 --zone=us-central1-a
```

### 5. **Use Node Selectors for Staged Rollout**

```yaml
# Label your upgraded nodes
kubectl label nodes upgraded-node-1 upgrade-status=completed

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
              - key: upgrade-status
                operator: In
                values: ["completed"]
```

### 6. **Monitor and Control the Process**

```bash
# Watch the upgrade process
kubectl get nodes -w --sort-by='.status.nodeInfo.kubeletVersion'

# Script to ensure pods land on upgraded nodes
#!/bin/bash
while true; do
  # Get nodes being drained
  draining_nodes=$(kubectl get nodes -o json | jq -r '.items[] | select(.spec.unschedulable == true) | .metadata.name')
  
  # Taint them to prevent scheduling
  for node in $draining_nodes; do
    kubectl taint nodes $node draining=true:NoSchedule --overwrite
  done
  
  sleep 30
done
```

## Best Practices Going Forward

### 1. **Blue-Green Node Pool Strategy**
```bash
# Create new node pool with updated version
gcloud container node-pools create new-pool \
  --cluster=my-cluster \
  --machine-type=n1-standard-4 \
  --num-nodes=3

# Gradually migrate workloads
kubectl cordon old-nodes
kubectl drain old-nodes --ignore-daemonsets

# Delete old pool when done
gcloud container node-pools delete old-pool --cluster=my-cluster
```

### 2. **Use Cluster Autoscaler Annotations**
```yaml
apiVersion: v1
kind: Node
metadata:
  annotations:
    cluster-autoscaler/scale-down-disabled: "true"  # Protect during upgrades
```

### 3. **Implement Upgrade-Aware Scheduling**
```yaml
# Use priority classes to control scheduling during upgrades
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: upgrade-safe
value: 1000
description: "Pods that should prefer upgraded nodes"
```

## Quick Emergency Fix

If you're in the middle of this situation right now:

```bash
# 1. Pause the upgrade
kubectl patch nodepool <nodepool-name> --type='merge' -p='{"spec":{"upgradeSettings":{"maxUnavailable":0}}}'

# 2. Taint all non-upgraded nodes
kubectl get nodes -o json | jq -r '.items[] | select(.status.nodeInfo.kubeletVersion != "DESIRED_VERSION") | .metadata.name' | \
xargs -I {} kubectl taint nodes {} upgrade=pending:NoSchedule

# 3. Resume upgrade with controlled pace
kubectl patch nodepool <nodepool-name> --type='merge' -p='{"spec":{"upgradeSettings":{"maxUnavailable":1}}}'
```

The key is controlling the upgrade pace and giving the scheduler clear signals about which nodes are safe for scheduling. Would you like me to elaborate on any of these approaches?