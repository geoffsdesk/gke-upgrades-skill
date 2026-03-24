This is a classic node pool upgrade orchestration issue! Your pods are indeed playing musical chairs because the upgrade process isn't coordinating properly with pod scheduling. Here's what's happening and how to fix it:

## Root Causes

**1. Upgrade Strategy Issues**
- Too many nodes being upgraded simultaneously
- No distinction between "safe" and "unsafe" nodes for scheduling
- Pod disruption budgets not properly configured

**2. Scheduler Confusion**
- Kubernetes scheduler sees multiple "available" nodes
- No preference for already-upgraded nodes
- Anti-affinity rules may be spreading pods to soon-to-be-drained nodes

## Solutions

### 1. Fix Your Upgrade Strategy

**For managed clusters (EKS/GKE/AKS):**
```yaml
# EKS - Configure update config
apiVersion: eksctl.io/v1alpha5
kind: ClusterConfig
nodeGroups:
  - name: workers
    maxUnavailable: 1  # Only upgrade 1 node at a time
    # OR
    maxUnavailablePercentage: 25  # Max 25% unavailable
```

**For manual upgrades:**
```bash
# Upgrade nodes one at a time with proper coordination
kubectl drain node-1 --ignore-daemonsets --delete-emptydir-data --force
# Wait for pods to stabilize before draining next node
kubectl get pods --all-namespaces --field-selector spec.nodeName=""
# Only proceed when pods are scheduled and running
```

### 2. Use Node Selectors/Affinity for Upgraded Nodes

**Label your upgraded nodes:**
```bash
kubectl label nodes upgraded-node-1 node.upgrade/status=upgraded
kubectl label nodes upgraded-node-2 node.upgrade/status=upgraded
```

**Update deployments to prefer upgraded nodes:**
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
              - key: node.upgrade/status
                operator: In
                values: ["upgraded"]
          # Avoid nodes being upgraded
          - weight: 50
            preference:
              matchExpressions:
              - key: node.upgrade/status
                operator: NotIn
                values: ["upgrading"]
```

### 3. Implement Pod Disruption Budgets

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  minAvailable: 2  # Keep at least 2 replicas running
  selector:
    matchLabels:
      app: my-app
```

### 4. Controlled Upgrade Script

```bash
#!/bin/bash
# controlled-upgrade.sh

NODES_TO_UPGRADE=$(kubectl get nodes -l node.upgrade/status!=upgraded -o name)

for node in $NODES_TO_UPGRADE; do
    NODE_NAME=$(echo $node | cut -d'/' -f2)
    echo "Upgrading $NODE_NAME..."
    
    # Label node as being upgraded
    kubectl label node $NODE_NAME node.upgrade/status=upgrading
    
    # Drain the node
    kubectl drain $NODE_NAME \
        --ignore-daemonsets \
        --delete-emptydir-data \
        --timeout=300s
    
    # Perform upgrade (example for kubeadm)
    ssh $NODE_NAME 'sudo kubeadm upgrade node'
    
    # Uncordon the node
    kubectl uncordon $NODE_NAME
    
    # Label as upgraded
    kubectl label node $NODE_NAME node.upgrade/status=upgraded
    
    # Wait for pods to stabilize
    echo "Waiting for pods to stabilize..."
    sleep 30
    
    # Check if any pods are still pending
    while kubectl get pods --all-namespaces --field-selector status.phase=Pending | grep -q .; do
        echo "Waiting for pending pods to be scheduled..."
        sleep 10
    done
done
```

### 5. For Cloud Provider Managed Upgrades

**EKS with eksctl:**
```bash
# Configure rolling update properly
eksctl create nodegroup \
    --cluster=my-cluster \
    --name=new-workers \
    --node-type=m5.large \
    --nodes=3 \
    --nodes-min=1 \
    --nodes-max=6 \
    --max-pods-per-node=110 \
    --update-config='{"maxUnavailable":1}'
```

**GKE:**
```bash
# Set upgrade strategy
gcloud container node-pools update workers \
    --cluster=my-cluster \
    --zone=us-central1-a \
    --surge-upgrade \
    --max-surge-upgrade=1 \
    --max-unavailable-upgrade=0
```

### 6. Monitor the Process

**Create a monitoring script:**
```bash
#!/bin/bash
# monitor-upgrade.sh

watch -n 5 '
echo "=== Node Status ==="
kubectl get nodes -o custom-columns="NAME:.metadata.name,STATUS:.status.conditions[-1].type,UPGRADE:.metadata.labels.node\.upgrade/status"

echo -e "\n=== Pod Distribution ==="
kubectl get pods -o wide --all-namespaces | grep -v kube-system

echo -e "\n=== Pending Pods ==="
kubectl get pods --all-namespaces --field-selector status.phase=Pending
'
```

## Best Practices Going Forward

1. **Always upgrade incrementally** - max 25% of nodes at once
2. **Use pod disruption budgets** for all critical workloads
3. **Label nodes during upgrade process** to guide scheduling
4. **Monitor pod placement** during upgrades
5. **Have enough buffer capacity** to handle displaced pods
6. **Test upgrade procedures** in non-production first

The key is coordination - making sure your upgrade process, pod scheduling, and cluster capacity all work together rather than against each other!