You've perfectly described the "musical chairs" problem in Kubernetes node pool upgrades! This happens because pods are being scheduled to any available node without regard for which nodes are about to be upgraded. Here's what's happening and how to fix it:

## Root Cause
The default upgrade strategy drains nodes simultaneously or in quick succession, but the scheduler doesn't know which nodes are "safe" long-term destinations.

## Solutions

### 1. **Use Rolling Update Strategy with Proper Configuration**

```yaml
# For managed node groups (EKS example)
apiVersion: eksctl.io/v1alpha5
kind: ClusterConfig
metadata:
  name: my-cluster
nodeGroups:
  - name: workers
    # ... other config
    updateConfig:
      maxUnavailable: 1  # Only drain 1 node at a time
      # OR
      maxUnavailablePercentage: 25  # Drain 25% at a time
```

### 2. **Implement Node Affinity for Upgraded Nodes**

Label your upgraded nodes and use node affinity:

```bash
# Label upgraded nodes
kubectl label nodes <upgraded-node> node.kubernetes.io/upgraded=true

# Update your deployments
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
              - key: node.kubernetes.io/upgraded
                operator: In
                values: ["true"]
```

### 3. **Use Taints and Tolerations Strategy**

```bash
# Taint nodes that are about to be upgraded
kubectl taint nodes <node-to-upgrade> upgrade=pending:NoSchedule

# Only pods with tolerations can be scheduled there
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      tolerations:
      - key: "upgrade"
        operator: "Equal"
        value: "pending"
        effect: "NoSchedule"
        # Only add this toleration to non-critical workloads
```

### 4. **Controlled Manual Upgrade Process**

```bash
#!/bin/bash
# Upgrade script with proper sequencing

NODES=$(kubectl get nodes -l node-pool=workers --no-headers | awk '{print $1}')

for node in $NODES; do
    echo "Upgrading node: $node"
    
    # Taint the node to prevent new scheduling
    kubectl taint nodes $node upgrade=in-progress:NoSchedule
    
    # Cordon the node
    kubectl cordon $node
    
    # Gracefully drain
    kubectl drain $node --ignore-daemonsets --delete-emptydir-data --grace-period=300
    
    # Perform the actual upgrade (cloud provider specific)
    # aws eks update-nodegroup-version --cluster-name ... --nodegroup-name ...
    
    # Wait for node to be ready
    kubectl wait --for=condition=Ready node/$node --timeout=600s
    
    # Remove taint and uncordon
    kubectl taint nodes $node upgrade=in-progress:NoSchedule-
    kubectl uncordon $node
    
    # Wait a bit before next node
    sleep 30
done
```

### 5. **Pod Disruption Budgets (PDBs) for Better Control**

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  minAvailable: 2  # or maxUnavailable: 1
  selector:
    matchLabels:
      app: my-app
```

### 6. **Cloud Provider Specific Solutions**

**For EKS:**
```bash
# Use update-config for managed node groups
aws eks update-nodegroup-config \
    --cluster-name my-cluster \
    --nodegroup-name my-nodegroup \
    --update-config maxUnavailable=1
```

**For GKE:**
```bash
# Use surge upgrades
gcloud container node-pools update my-pool \
    --cluster=my-cluster \
    --max-surge-upgrade=1 \
    --max-unavailable-upgrade=0
```

**For AKS:**
```bash
# Configure upgrade settings
az aks nodepool update \
    --cluster-name my-cluster \
    --name mynodepool \
    --max-surge 1
```

### 7. **Pre-create New Node Pool (Blue/Green Strategy)**

```bash
# Create new node pool with updated version
kubectl create -f new-nodepool.yaml

# Wait for nodes to be ready
kubectl wait --for=condition=Ready nodes -l nodepool=new --timeout=600s

# Gradually migrate workloads
kubectl patch deployment my-app -p '{
  "spec": {
    "template": {
      "spec": {
        "nodeSelector": {
          "nodepool": "new"
        }
      }
    }
  }
}'

# Delete old node pool after migration
```

## Best Practices During Upgrades

1. **Monitor pod scheduling:**
```bash
kubectl get events --field-selector reason=Scheduled -w
```

2. **Check node capacity:**
```bash
kubectl top nodes
kubectl describe nodes | grep -A 5 "Allocated resources"
```

3. **Use priority classes for critical workloads:**
```yaml
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: high-priority
value: 1000
globalDefault: false
```

The key is controlling the upgrade sequence so pods have stable destinations rather than playing musical chairs between soon-to-be-upgraded nodes.