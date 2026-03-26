This is a classic node pool upgrade orchestration issue! The problem is that the scheduler is placing evicted pods on any available node without considering the upgrade rollout strategy. Here's what's happening and how to fix it:

## Root Causes

1. **Scheduler doesn't know about upgrade intentions** - It sees all Ready nodes as valid targets
2. **Upgrade rollout is too aggressive** - Multiple nodes being drained simultaneously
3. **Missing anti-affinity rules** - Pods can land anywhere that has capacity
4. **Insufficient ready capacity** - Not enough upgraded nodes to absorb the workload

## Solutions

### 1. Control Upgrade Rollout Speed

**For managed clusters (GKE, EKS, AKS):**
```yaml
# GKE example
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerNodePool
spec:
  upgradeSettings:
    maxSurge: 1        # Only upgrade 1 node at a time
    maxUnavailable: 0  # Don't drain until replacement is ready
```

**For self-managed clusters:**
```bash
# Drain nodes one at a time with proper waits
kubectl drain node1 --ignore-daemonsets --delete-emptydir-data
# Wait for pods to stabilize before draining next node
sleep 300
kubectl drain node2 --ignore-daemonsets --delete-emptydir-data
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
                values: ["new-instance-type"]  # Target upgraded nodes
          - weight: 80
            preference:
              matchExpressions:
              - key: kubernetes.io/arch
                operator: In
                values: ["amd64"]
```

### 3. Implement Pod Disruption Budgets

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  minAvailable: 2  # or use maxUnavailable: 1
  selector:
    matchLabels:
      app: my-app
```

### 4. Use Topology Spread Constraints

```yaml
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      topologySpreadConstraints:
      - maxSkew: 1
        topologyKey: topology.kubernetes.io/zone
        whenUnsatisfiable: DoNotSchedule
        labelSelector:
          matchLabels:
            app: my-app
      - maxSkew: 2
        topologyKey: kubernetes.io/hostname
        whenUnsatisfiable: ScheduleAnyway  # Soft constraint
        labelSelector:
          matchLabels:
            app: my-app
```

### 5. Strategic Node Labeling During Upgrades

**Before upgrade, label nodes by status:**
```bash
# Label nodes being upgraded
kubectl label nodes old-node-1 old-node-2 upgrade-status=draining

# Label already upgraded nodes  
kubectl label nodes new-node-1 new-node-2 upgrade-status=ready
```

**Update deployments to avoid draining nodes:**
```yaml
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
                values: ["draining"]
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            preference:
              matchExpressions:
              - key: upgrade-status
                operator: In
                values: ["ready"]
```

### 6. Automated Upgrade Script

```bash
#!/bin/bash
# Smart node pool upgrade script

NODES_TO_UPGRADE=$(kubectl get nodes -l node-pool=old-pool -o name)

for node in $NODES_TO_UPGRADE; do
    NODE_NAME=$(echo $node | cut -d'/' -f2)
    
    echo "Labeling $NODE_NAME as draining..."
    kubectl label node $NODE_NAME upgrade-status=draining
    
    # Wait for scheduler to move pods away from draining nodes
    sleep 60
    
    echo "Draining $NODE_NAME..."
    kubectl drain $NODE_NAME \
        --ignore-daemonsets \
        --delete-emptydir-data \
        --timeout=300s
    
    # Wait for node to be replaced (managed clusters)
    echo "Waiting for replacement node..."
    while [[ $(kubectl get nodes -l upgrade-status=ready | wc -l) -lt 2 ]]; do
        sleep 30
    done
    
    echo "Node $NODE_NAME upgrade complete"
done
```

### 7. Use Descheduler for Rebalancing

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: descheduler-policy
data:
  policy.yaml: |
    apiVersion: "descheduler/v1alpha1"
    kind: "DeschedulerPolicy"
    strategies:
      "RemovePodsFromUnschedulableNodes":
        enabled: true
      "LowNodeUtilization":
        enabled: true
        params:
          nodeResourceUtilizationThresholds:
            thresholds:
              "cpu": 20
              "memory": 20
            targetThresholds:
              "cpu": 50
              "memory": 50
```

## Best Practices for Smooth Upgrades

1. **Always upgrade with surge capacity** - Have replacement nodes ready before draining
2. **Monitor pod scheduling** - Watch where evicted pods land
3. **Use gradual rollouts** - Never drain more than 25% of nodes simultaneously  
4. **Implement proper PDBs** - Prevent too many replicas being unavailable
5. **Test upgrade procedures** - Practice on dev/staging first
6. **Monitor application health** - Ensure services remain available throughout

The key is controlling the pace and giving the scheduler better information about where pods should land during the upgrade process.