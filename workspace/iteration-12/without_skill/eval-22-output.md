This is a classic issue with rolling node pool upgrades! You're experiencing the "musical chairs" problem where pods keep bouncing between nodes that are all scheduled for replacement. Here's what's happening and how to fix it:

## Root Cause

The scheduler doesn't know which nodes are "safe" (already upgraded) vs "doomed" (scheduled for drain). It's just placing pods on any available node, including ones that will be drained shortly.

## Solutions

### 1. **Control Upgrade Batch Size and Timing**

```yaml
# For GKE
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerNodePool
spec:
  upgradeSettings:
    maxSurge: 1          # Add only 1 new node at a time
    maxUnavailable: 0    # Don't remove old nodes until new ones are ready
    blueGreenSettings:   # Use blue-green upgrades if available
      standardRolloutPolicy:
        batchNodeCount: 1
```

```yaml
# For EKS (managed node groups)
apiVersion: eks.aws.crossplane.io/v1alpha1
kind: NodeGroup
spec:
  updateConfig:
    maxUnavailablePercentage: 25  # Limit concurrent updates
```

### 2. **Use Node Taints During Upgrades**

Pre-taint nodes scheduled for upgrade:

```bash
# Before draining, taint the old nodes
kubectl taint node <old-node> upgrade=in-progress:NoSchedule

# Your upgraded nodes should be taint-free
kubectl taint node <new-node> upgrade=in-progress:NoSchedule-
```

### 3. **Implement Pod Disruption Budgets**

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

### 4. **Use Node Selectors/Affinity for Stability**

Label your upgraded nodes and prefer them:

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
              - key: node.kubernetes.io/upgrade-status
                operator: In
                values: ["complete"]
          # Avoid nodes being upgraded
          - weight: 50
            preference:
              matchExpressions:
              - key: node.kubernetes.io/upgrade-status
                operator: NotIn
                values: ["in-progress"]
```

### 5. **Controlled Manual Upgrade Process**

```bash
#!/bin/bash
# Better upgrade script

OLD_NODES=$(kubectl get nodes -l pool=old-pool -o name)
NEW_NODES=$(kubectl get nodes -l pool=new-pool -o name)

for node in $OLD_NODES; do
    echo "Upgrading $node"
    
    # 1. Taint the node to prevent new scheduling
    kubectl taint node $node upgrade=draining:NoSchedule
    
    # 2. Wait a bit for scheduler to avoid it
    sleep 30
    
    # 3. Gracefully drain
    kubectl drain $node --ignore-daemonsets --delete-emptydir-data --grace-period=300
    
    # 4. Wait for pods to stabilize on good nodes
    kubectl wait --for=condition=Ready pod -l app=my-app --timeout=300s
    
    # 5. Remove the node
    kubectl delete node $node
done
```

### 6. **Use Cluster Autoscaler Annotations**

```bash
# Prevent specific nodes from being scaled down during upgrade
kubectl annotate node <node-name> cluster-autoscaler/scale-down-disabled=true

# Remove annotation after upgrade
kubectl annotate node <node-name> cluster-autoscaler/scale-down-disabled-
```

### 7. **Topology Spread Constraints**

Help distribute pods across stable nodes:

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
```

## Best Practices for Future Upgrades

### 1. **Staged Upgrade Strategy**
```bash
# Upgrade in smaller batches
kubectl patch nodepool <pool-name> -p '{"spec":{"upgradeSettings":{"maxSurge":2,"maxUnavailable":1}}}'
```

### 2. **Monitor Pod Distribution**
```bash
# Watch where pods are landing
watch "kubectl get pods -o wide | grep my-app"

# Check node readiness
kubectl get nodes -o custom-columns=NAME:.metadata.name,STATUS:.status.conditions[-1].type,VERSION:.status.nodeInfo.kubeletVersion
```

### 3. **Use Blue-Green Node Pool Strategy**
```bash
# Create new node pool alongside old one
kubectl create nodepool new-pool --version=new-version

# Gradually move workloads
kubectl patch deployment my-app -p '{"spec":{"template":{"spec":{"nodeSelector":{"pool":"new-pool"}}}}}'

# Delete old pool when done
kubectl delete nodepool old-pool
```

The key is giving the scheduler better information about which nodes are safe and controlling the upgrade pace to prevent the musical chairs scenario. Start with PDBs and controlled batch sizes for immediate relief!