You're experiencing a classic Kubernetes upgrade race condition! This happens because the scheduler doesn't know which nodes are "safe" vs "about to be drained" when making placement decisions. Here's what's happening and how to fix it:

## Root Cause
- Nodes are being upgraded in parallel/rapid succession
- The scheduler sees nodes as "available" even if they're next in line for drainage
- Pods land on nodes that get cordoned/drained shortly after

## Solutions

### 1. **Sequential Node Upgrades with Proper Timing**
```bash
# Configure your node pool upgrade strategy
kubectl patch nodepool <nodepool-name> -p '{
  "spec": {
    "upgradePolicy": {
      "rollingUpdate": {
        "maxSurge": 1,
        "maxUnavailable": 0
      }
    }
  }
}'
```

### 2. **Pre-cordon Strategy**
```bash
# Script to cordon nodes before they're drained
#!/bin/bash
NODES_TO_UPGRADE=$(kubectl get nodes --selector=nodepool=target -o name)

# Cordon all nodes first
for node in $NODES_TO_UPGRADE; do
  kubectl cordon $node
done

# Then upgrade one by one
for node in $NODES_TO_UPGRADE; do
  kubectl drain $node --ignore-daemonsets --delete-emptydir-data
  # Trigger node upgrade
  upgrade_node $node
  # Wait for node to be ready
  kubectl wait --for=condition=Ready $node --timeout=600s
  kubectl uncordon $node
done
```

### 3. **Node Affinity for Upgraded Nodes**
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
                values: ["new-instance-type"]
              - key: kubernetes.io/arch
                operator: NotIn
                values: ["upgrading"] # Custom label
```

### 4. **Cluster Autoscaler Configuration**
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cluster-autoscaler-status
  namespace: kube-system
data:
  nodes.max-node-provision-time: "15m"
  scale-down-delay-after-add: "10m"
  scale-down-unneeded-time: "10m"
```

### 5. **Pod Disruption Budgets (Critical)**
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: app-pdb
spec:
  minAvailable: 50%
  selector:
    matchLabels:
      app: your-app
```

### 6. **Upgrade Strategy with Node Pools**

**For EKS:**
```bash
# Create new node group first
eksctl create nodegroup \
  --cluster=your-cluster \
  --name=upgraded-nodes \
  --node-type=m5.large \
  --nodes=3 \
  --nodes-min=1 \
  --nodes-max=5

# Cordon old nodes
kubectl get nodes --selector=eks.amazonaws.com/nodegroup=old-nodegroup \
  -o name | xargs -I {} kubectl cordon {}

# Drain old nodes gradually
kubectl get nodes --selector=eks.amazonaws.com/nodegroup=old-nodegroup \
  -o name | xargs -I {} kubectl drain {} --ignore-daemonsets --delete-emptydir-data
```

**For GKE:**
```bash
# Configure surge upgrade
gcloud container node-pools update old-pool \
  --cluster=your-cluster \
  --zone=your-zone \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=0
```

### 7. **Monitoring Script**
```bash
#!/bin/bash
# Monitor pod movements during upgrade
watch -n 5 '
echo "=== Node Status ==="
kubectl get nodes -o wide
echo -e "\n=== Pod Distribution ==="
kubectl get pods -o wide --all-namespaces | grep -E "(Pending|ContainerCreating)"
echo -e "\n=== Cordoned Nodes ==="
kubectl get nodes | grep SchedulingDisabled
'
```

### 8. **Proper Upgrade Sequence**
```bash
#!/bin/bash
upgrade_node_pool() {
  local OLD_POOL=$1
  local NEW_POOL=$2
  
  # 1. Create new node pool
  create_node_pool $NEW_POOL
  
  # 2. Wait for new nodes to be ready
  wait_for_nodes_ready $NEW_POOL
  
  # 3. Cordon all old nodes at once
  kubectl get nodes -l nodepool=$OLD_POOL -o name | xargs kubectl cordon
  
  # 4. Drain nodes one by one with delays
  for node in $(kubectl get nodes -l nodepool=$OLD_POOL -o name); do
    kubectl drain $node --ignore-daemonsets --delete-emptydir-data
    sleep 60  # Give time for pods to settle
  done
  
  # 5. Delete old node pool
  delete_node_pool $OLD_POOL
}
```

## Best Practices to Prevent This

1. **Always surge before drain** - Add new nodes before removing old ones
2. **Use maxSurge > 0, maxUnavailable = 0** for zero-downtime upgrades
3. **Implement proper PDBs** for all critical applications
4. **Monitor pod distribution** during upgrades
5. **Use node taints/tolerations** for more control over scheduling
6. **Coordinate with application teams** about upgrade windows

The key is ensuring you have stable landing spots (new nodes) before you start the musical chairs game!