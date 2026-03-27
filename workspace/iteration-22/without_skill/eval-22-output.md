You're experiencing the classic "node upgrade thrashing" problem! This happens because the scheduler doesn't know which nodes are about to be drained, so it places evicted pods on any available node - including ones queued for upgrade.

## What's Causing This

1. **No scheduler awareness**: The scheduler only sees current node status, not future upgrade plans
2. **Upgrade strategy**: Depending on your strategy, multiple nodes might be upgrading simultaneously
3. **Resource constraints**: Limited capacity on already-upgraded nodes
4. **Missing anti-affinity rules**: Pods aren't being directed to prefer stable nodes

## Solutions

### 1. Control Upgrade Parallelism
```yaml
# For managed node pools (GKE example)
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerNodePool
spec:
  upgradeSettings:
    maxSurge: 1      # Add 1 new node before removing old
    maxUnavailable: 0 # Don't remove nodes until replacement is ready
    strategy: "SURGE"
```

### 2. Use Node Affinity to Prefer Upgraded Nodes
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
              - key: node.kubernetes.io/instance-type
                operator: In
                values: ["upgraded-node-type"]
          # Or use custom labels
          - weight: 100
            preference:
              matchExpressions:
              - key: upgrade-status
                operator: In
                values: ["completed"]
```

### 3. Pre-label Your Upgraded Nodes
```bash
# Label nodes as they complete upgrade
kubectl label node <upgraded-node> upgrade-status=completed

# Remove label from nodes about to upgrade
kubectl label node <node-to-upgrade> upgrade-status=pending
```

### 4. Use Pod Disruption Budgets Strategically
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: my-app
---
# This slows down the upgrade but prevents thrashing
```

### 5. Implement a Controlled Upgrade Script
```bash
#!/bin/bash

# Get all nodes to upgrade
NODES_TO_UPGRADE=$(kubectl get nodes -l node-pool=target-pool -o name)

for node in $NODES_TO_UPGRADE; do
  echo "Upgrading $node"
  
  # Label node as upgrading
  kubectl label $node upgrade-status=upgrading
  
  # Cordon the node
  kubectl cordon $node
  
  # Wait for pods to reschedule before draining
  sleep 30
  
  # Drain the node
  kubectl drain $node --ignore-daemonsets --delete-emptydir-data --grace-period=300
  
  # Trigger the actual node upgrade (platform-specific)
  # upgrade_node $node
  
  # Wait for node to come back and be ready
  kubectl wait --for=condition=Ready $node --timeout=600s
  
  # Label as completed
  kubectl label $node upgrade-status=completed
  
  echo "$node upgrade completed"
done
```

### 6. Use Topology Spread Constraints
```yaml
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      topologySpreadConstraints:
      - maxSkew: 1
        topologyKey: upgrade-status
        whenUnsatisfiable: ScheduleAnyway  # Soft constraint
        labelSelector:
          matchLabels:
            app: my-app
```

### 7. Platform-Specific Solutions

**For GKE:**
```bash
# Use blue-green node pool strategy
gcloud container node-pools create new-pool \
  --cluster=my-cluster \
  --machine-type=n1-standard-2 \
  --num-nodes=3

# Migrate workloads, then delete old pool
```

**For EKS:**
```yaml
# In your EKS managed node group
apiVersion: eksctl.io/v1alpha5
kind: ClusterConfig
nodeGroups:
- name: upgraded-nodes
  updateConfig:
    maxUnavailable: 1
    maxUnavailablePercentage: 25
```

### 8. Monitor the Upgrade Process
```bash
# Watch pod movements
kubectl get pods -o wide --watch

# Monitor node status during upgrade
kubectl get nodes -l upgrade-status --watch

# Check for pods stuck in pending
kubectl get pods --field-selector=status.phase=Pending
```

## Best Practices for Future Upgrades

1. **Always use surge upgrades** when possible (add before removing)
2. **Implement gradual rollout** - upgrade one node at a time for critical workloads
3. **Use node selectors** to pin critical workloads to stable nodes
4. **Monitor resource capacity** - ensure upgraded nodes have enough capacity
5. **Test with non-critical workloads first**

The key is giving the scheduler better information about where pods should land and controlling the pace of the upgrade to prevent the musical chairs effect.