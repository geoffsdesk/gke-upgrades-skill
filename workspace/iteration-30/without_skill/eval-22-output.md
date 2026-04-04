This is a classic "musical chairs" problem during rolling node upgrades! The issue is that your scheduler doesn't distinguish between old nodes (about to be drained) and new nodes (already upgraded), so pods can land anywhere that has capacity.

## What's Happening

During node pool upgrades:
1. New nodes come online but aren't immediately preferred
2. Pods get evicted from Node A
3. Scheduler places them on Node B (which is also old)
4. Node B gets drained, pods move to Node C (also old)
5. This continues until pods eventually land on new nodes by chance

## Solutions

### 1. Use Node Affinity to Prefer New Nodes

Label your new nodes and configure workloads to prefer them:

```yaml
# Label new nodes during upgrade
kubectl label nodes <new-node-name> node-generation=new

# Add to your deployments
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
              - key: node-generation
                operator: In
                values: ["new"]
```

### 2. Cordon Old Nodes Before Draining

This prevents new pods from being scheduled on nodes that will be drained:

```bash
# Cordon nodes before starting drain process
kubectl cordon <old-node-name>

# Then drain with a delay
kubectl drain <old-node-name> --ignore-daemonsets --delete-emptydir-data
```

### 3. Control Upgrade Parallelism

Limit how many nodes are upgraded simultaneously:

```yaml
# For managed node groups (EKS example)
apiVersion: eksctl.io/v1alpha5
kind: ClusterConfig
nodeGroups:
  - name: workers
    updateConfig:
      maxUnavailablePercentage: 25  # Only 25% of nodes at once
```

### 4. Use PodDisruptionBudgets Strategically

Ensure critical workloads have appropriate PDBs:

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: app-pdb
spec:
  minAvailable: 50%  # Ensures some pods always running
  selector:
    matchLabels:
      app: my-app
```

### 5. Automated Script for Controlled Upgrades

```bash
#!/bin/bash
# controlled-node-upgrade.sh

OLD_NODES=$(kubectl get nodes -l node-generation!=new -o name)

for node in $OLD_NODES; do
    echo "Processing $node"
    
    # Cordon first to prevent new pods
    kubectl cordon $node
    
    # Wait for other nodes to be ready to receive workloads
    kubectl wait --for=condition=Ready node -l node-generation=new --timeout=300s
    
    # Drain the node
    kubectl drain $node --ignore-daemonsets --delete-emptydir-data --timeout=300s
    
    # Wait a bit for pods to settle before next node
    sleep 30
done
```

### 6. Use Cluster Autoscaler Annotations

If using cluster autoscaler, use annotations to control behavior:

```bash
# Prevent scale-down on new nodes during upgrade
kubectl annotate node <new-node> cluster-autoscaler/scale-down-disabled=true

# Remove annotation after upgrade complete
kubectl annotate node <new-node> cluster-autoscaler/scale-down-disabled-
```

### 7. For Cloud Provider Managed Upgrades

**AWS EKS:**
```bash
# Use update-nodegroup-config to control upgrade
aws eks update-nodegroup-config \
    --cluster-name my-cluster \
    --nodegroup-name my-nodegroup \
    --update-config maxUnavailablePercentage=10
```

**GKE:**
```bash
# Control surge upgrades
gcloud container node-pools update my-pool \
    --cluster=my-cluster \
    --max-surge-upgrade=1 \
    --max-unavailable-upgrade=0
```

## Best Practices for Future Upgrades

1. **Pre-provision capacity**: Ensure new nodes are ready before starting drains
2. **Gradual rollout**: Upgrade small percentages at a time
3. **Monitor pod placement**: Watch where evicted pods land
4. **Use topology spread constraints**: Ensure even distribution across zones
5. **Test with non-critical workloads first**: Validate your upgrade process

The key is to either guide the scheduler toward new nodes or prevent it from using old nodes, breaking the musical chairs cycle!