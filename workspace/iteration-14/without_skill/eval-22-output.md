You're experiencing the classic "pod pinball" problem during rolling upgrades! This happens because Kubernetes doesn't coordinate pod placement with your upgrade strategy by default. Here's what's going wrong and how to fix it:

## Root Causes

1. **No upgrade-aware scheduling** - The scheduler doesn't know which nodes are next to be drained
2. **Default anti-affinity rules** - Pods might prefer spreading across "old" nodes
3. **Resource constraints** - New nodes might not be ready or have sufficient resources
4. **Timing issues** - Nodes are cordoned/drained faster than new ones come online

## Solutions

### 1. **Control the Upgrade Sequence**

Add node labels to control which nodes get upgraded when:

```bash
# Label nodes by upgrade wave
kubectl label nodes node-1 node-2 node-3 upgrade-wave=1
kubectl label nodes node-4 node-5 node-6 upgrade-wave=2

# Upgrade wave 1 first, ensure wave 2 is ready before proceeding
```

### 2. **Use Pod Disruption Budgets (PDBs)**

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
# This slows down draining, giving new nodes time to be ready
```

### 3. **Node Affinity for Upgraded Nodes**

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
                values: ["new-instance-type"] # Target upgraded nodes
          - weight: 50
            preference:
              matchExpressions:
              - key: upgrade-wave
                operator: NotIn
                values: ["1"] # Avoid nodes in current upgrade wave
```

### 4. **Taint New Nodes During Upgrade**

```bash
# Taint old nodes to repel new pods
kubectl taint nodes old-node-1 upgrading=true:NoSchedule

# Remove taint after upgrade
kubectl taint nodes new-node-1 upgrading=true:NoSchedule-
```

### 5. **Pre-scale and Controlled Draining**

```bash
#!/bin/bash
# Upgrade script with proper coordination

# 1. Scale up new nodes first
kubectl scale nodepool new-pool --replicas=6

# 2. Wait for new nodes to be ready
kubectl wait --for=condition=Ready node -l nodepool=new-pool --timeout=300s

# 3. Drain old nodes one by one with delays
for node in $(kubectl get nodes -l nodepool=old-pool -o name); do
    echo "Draining $node"
    kubectl drain $node --ignore-daemonsets --delete-emptydir-data --grace-period=300
    
    # Wait for pods to reschedule and stabilize
    sleep 60
    
    # Check pod status before continuing
    kubectl get pods --all-namespaces --field-selector=status.phase=Pending
done
```

### 6. **Deployment Strategy Adjustments**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 50%        # Allow extra pods during upgrade
      maxUnavailable: 25%  # Limit disruption
  template:
    spec:
      terminationGracePeriodSeconds: 30  # Faster pod shutdown
      tolerations:
      - key: "upgrading"
        operator: "Equal"
        value: "true"
        effect: "NoSchedule"
        tolerationSeconds: 60  # Temporary tolerance
```

### 7. **Monitoring and Alerting**

```bash
# Monitor pod churn during upgrades
kubectl get events --sort-by='.lastTimestamp' | grep -E "(Evicted|FailedScheduling|Killing)"

# Check for pending pods
kubectl get pods --all-namespaces --field-selector=status.phase=Pending

# Monitor node readiness
kubectl get nodes -o wide --sort-by='.metadata.creationTimestamp'
```

### 8. **Cluster Autoscaler Configuration**

```yaml
# Cluster autoscaler deployment adjustment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cluster-autoscaler
spec:
  template:
    spec:
      containers:
      - name: cluster-autoscaler
        command:
        - ./cluster-autoscaler
        - --scale-down-delay-after-add=10m     # Wait before scaling down
        - --scale-down-unneeded-time=10m       # Longer evaluation period
        - --max-node-provision-time=15m        # Allow time for node prep
```

## Best Practices for Future Upgrades

1. **Upgrade during low-traffic periods**
2. **Use blue-green node pool strategy when possible**
3. **Pre-warm new nodes** with DaemonSets and system pods
4. **Test upgrade procedures** in staging environment
5. **Monitor resource utilization** to ensure new nodes have capacity

The key is coordinating the timing between draining old nodes and ensuring new nodes are truly ready to accept workloads, not just in "Ready" state.