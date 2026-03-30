This is a classic node pool upgrade orchestration issue! You're experiencing the "musical chairs" problem because the upgrade process and pod scheduler aren't coordinating properly. Here's what's happening and how to fix it:

## Root Causes

1. **All nodes marked for upgrade simultaneously** - The upgrade controller marks nodes for draining without ensuring stable landing zones
2. **Scheduler lacks upgrade awareness** - Pods land on any available node, including ones queued for upgrade
3. **Insufficient ready nodes** - Not enough upgraded nodes available to absorb the workload

## Solutions

### 1. Control Upgrade Rollout Strategy

**For managed clusters (GKE/EKS/AKS):**
```yaml
# GKE example
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerNodePool
metadata:
  name: my-nodepool
spec:
  upgradeSettings:
    maxSurge: 1        # Add 1 new node before draining
    maxUnavailable: 0  # Don't drain until new nodes ready
    strategy: SURGE     # Create new nodes first
```

**For EKS:**
```yaml
# eksctl config
nodeGroups:
- name: workers
  updateConfig:
    maxUnavailablePercentage: 25  # Only drain 25% at once
  # Or use managed node group rolling updates
```

### 2. Use Node Affinity to Prefer Upgraded Nodes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
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
                values: ["new-instance-type"]  # Target upgraded nodes
          - weight: 50
            preference:
              matchExpressions:
              - key: kubernetes.io/arch
                operator: NotIn
                values: ["upgrading"]  # Avoid nodes being upgraded
```

### 3. Implement Custom Upgrade Orchestration

```bash
#!/bin/bash
# Custom rolling upgrade script

NODEPOOL_NAME="worker-nodes"
NODES=$(kubectl get nodes -l nodepool=$NODEPOOL_NAME -o name)

for node in $NODES; do
    NODE_NAME=$(echo $node | cut -d'/' -f2)
    
    # Wait for at least 2 ready nodes in pool
    while [[ $(kubectl get nodes -l nodepool=$NODEPOOL_NAME --field-selector=spec.unschedulable!=true | wc -l) -lt 3 ]]; do
        echo "Waiting for sufficient ready nodes..."
        sleep 30
    done
    
    # Cordon and drain one node at a time
    kubectl cordon $NODE_NAME
    kubectl drain $NODE_NAME \
        --ignore-daemonsets \
        --delete-emptydir-data \
        --timeout=300s
    
    # Trigger node replacement (cloud-specific)
    # For GKE: gcloud container operations wait
    # For EKS: aws eks update-nodegroup-version
    # For AKS: az aks nodepool upgrade
    
    # Wait for new node to be ready
    sleep 60
    
    echo "Node $NODE_NAME upgraded successfully"
done
```

### 4. Use PodDisruptionBudgets to Control Evictions

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  minAvailable: 2  # Keep at least 2 pods running
  selector:
    matchLabels:
      app: my-app
```

### 5. Implement Upgrade-Aware Scheduling

```yaml
# Add node labels during upgrade process
apiVersion: v1
kind: Node
metadata:
  name: worker-node-1
  labels:
    upgrade-status: "in-progress"  # Label nodes being upgraded
---
# Pod anti-affinity to avoid upgrading nodes
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - key: upgrade-status
                operator: NotIn
                values: ["in-progress", "pending"]
```

### 6. Monitor and Validate

```bash
# Check node readiness during upgrade
kubectl get nodes -o custom-columns=NAME:.metadata.name,STATUS:.status.conditions[-1].type,SCHEDULABLE:.spec.unschedulable

# Monitor pod movements
kubectl get events --field-selector reason=Evicted -w

# Verify workload stability
kubectl get pods -o wide --sort-by='.status.startTime'
```

## Best Practices

1. **Always use surge capacity** - Add new nodes before draining old ones
2. **Upgrade in small batches** - Never upgrade more than 25% of capacity simultaneously  
3. **Set appropriate timeouts** - Allow sufficient time for pod rescheduling
4. **Use blue-green for critical workloads** - Create entirely new node pools for zero-downtime upgrades
5. **Test upgrade procedures** - Practice on staging environments first

The key is ensuring you always have stable, upgraded nodes available before starting to drain nodes that need upgrading!