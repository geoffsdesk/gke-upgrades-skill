You're experiencing the classic "pod thrashing" problem during rolling node upgrades! This happens when the Kubernetes scheduler can't distinguish between nodes that are stable versus those queued for replacement. Here's what's going on and how to fix it:

## Root Cause
During rolling upgrades, multiple nodes may be in different stages:
- Nodes being drained (cordoned, pods evicting)
- Nodes queued for upgrade (still schedulable but doomed)
- Fresh nodes (recently upgraded)
- Untouched nodes (waiting their turn)

The scheduler sees all non-cordoned nodes as valid targets, leading to the musical chairs effect.

## Solutions

### 1. **Control Upgrade Parallelism**
```yaml
# For managed node groups (EKS example)
apiVersion: eksctl.io/v1alpha5
kind: ClusterConfig
nodeGroups:
  - name: workers
    maxUnavailable: 1  # Only upgrade 1 node at a time
    # or
    maxUnavailablePercentage: 25  # Max 25% nodes upgrading simultaneously
```

### 2. **Use Node Affinity to Prefer Fresh Nodes**
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
                values: ["m5.large"]  # Prefer newer instance types
          - weight: 50
            preference:
              matchExpressions:
              - key: topology.kubernetes.io/zone
                operator: In
                values: ["us-west-2a"]  # Distribute across zones
```

### 3. **Implement Strategic Node Labeling**
```bash
# Before starting upgrade, label nodes by upgrade phase
kubectl label node node-1 upgrade-phase=pending
kubectl label node node-2 upgrade-phase=pending
kubectl label node node-3 upgrade-phase=stable

# Use anti-affinity to avoid pending nodes
```

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
              - key: upgrade-phase
                operator: In
                values: ["stable", "completed"]
```

### 4. **Use PodDisruptionBudgets Strategically**
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: app-pdb
spec:
  minAvailable: 2  # Ensure minimum pods stay running
  selector:
    matchLabels:
      app: my-app
---
# For critical workloads, be more conservative
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: critical-app-pdb
spec:
  maxUnavailable: 0  # Prevent any voluntary disruptions
  selector:
    matchLabels:
      app: critical-app
```

### 5. **Implement a Custom Upgrade Script**
```bash
#!/bin/bash
# controlled-node-upgrade.sh

NODES=$(kubectl get nodes --no-headers -o custom-columns=":metadata.name")
NODE_COUNT=$(echo "$NODES" | wc -l)
MAX_UPGRADING=1  # Only upgrade 1 node at a time

for NODE in $NODES; do
    echo "Upgrading node: $NODE"
    
    # Label node as upgrading
    kubectl label node $NODE upgrade-phase=upgrading
    
    # Cordon and drain
    kubectl cordon $NODE
    kubectl drain $NODE --ignore-daemonsets --delete-emptydir-data --timeout=300s
    
    # Trigger node replacement (cloud-provider specific)
    # For EKS with ASG:
    INSTANCE_ID=$(kubectl get node $NODE -o jsonpath='{.spec.providerID}' | cut -d'/' -f5)
    aws autoscaling terminate-instance-in-auto-scaling-group \
        --instance-id $INSTANCE_ID --should-decrement-desired-capacity
    
    # Wait for new node to be ready
    echo "Waiting for replacement node..."
    while [[ $(kubectl get nodes --no-headers | grep "Ready" | wc -l) -lt $NODE_COUNT ]]; do
        sleep 30
    done
    
    # Label new nodes as stable
    NEW_NODES=$(kubectl get nodes --no-headers -l '!upgrade-phase' -o custom-columns=":metadata.name")
    for NEW_NODE in $NEW_NODES; do
        kubectl label node $NEW_NODE upgrade-phase=stable
    done
    
    echo "Node $NODE upgrade completed"
done
```

### 6. **Use Cluster Autoscaler Annotations**
```bash
# Prevent specific nodes from being scaled down during upgrade
kubectl annotate node <node-name> cluster-autoscaler/scale-down-disabled=true

# Remove annotation after upgrade
kubectl annotate node <node-name> cluster-autoscaler/scale-down-disabled-
```

### 7. **Configure Proper Startup/Readiness Probes**
```yaml
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
      - name: app
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 5
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        # Ensure graceful shutdown
        lifecycle:
          preStop:
            exec:
              command: ["/bin/sleep", "15"]
```

## Best Practices for Node Upgrades

### 1. **Pre-upgrade Checklist**
```bash
# Check cluster capacity
kubectl top nodes
kubectl describe nodes | grep -A5 "Allocated resources"

# Verify PodDisruptionBudgets
kubectl get pdb --all-namespaces

# Check for pods without proper affinity/anti-affinity
kubectl get pods --all-namespaces -o wide
```

### 2. **Monitor During Upgrade**
```bash
# Watch pod movements
kubectl get events --sort-by=.metadata.creationTimestamp --watch

# Monitor pending pods
watch "kubectl get pods --all-namespaces | grep Pending"

# Check node status
watch "kubectl get nodes -o wide"
```

### 3. **For Managed Services (EKS, GKE, AKS)**
```yaml
# EKS - Use launch templates for better control
apiVersion: eksctl.io/v1alpha5
kind: ClusterConfig
nodeGroups:
  - name: workers
    updateConfig:
      maxUnavailable: 1
      maxUnavailablePercentage: null
    # Use mixed instances for better availability
    instancesDistribution:
      maxPrice: 0.20
      instanceTypes: ["m5.large", "m5a.large", "m4.large"]
      onDemandBaseCapacity: 2
      onDemandPercentageAboveBaseCapacity: 50
```

The key is controlling the upgrade velocity and giving the scheduler better information about which nodes are safe landing spots. Start with reducing parallelism - it's the quickest fix that often solves 80% of the problem.