This is a classic node pool upgrade orchestration issue! The problem is that your upgrade process is likely draining nodes faster than pods can stabilize, and the scheduler doesn't know which nodes are "safe" vs "about to be drained."

## What's Happening

1. **Race condition**: Nodes are being marked for drain before pods finish relocating
2. **Scheduler blindness**: The scheduler sees old nodes as "available" until they're actually cordoned
3. **Upgrade velocity**: The upgrade process may be too aggressive

## Solutions

### 1. **Control Upgrade Velocity**

**For GKE:**
```yaml
# Configure surge settings
nodePool:
  upgradeSettings:
    maxSurge: 1        # Add only 1 new node at a time
    maxUnavailable: 0  # Don't drain until new node is ready
```

**For EKS:**
```yaml
# In your node group configuration
updateConfig:
  maxUnavailablePercentage: 25  # Conservative percentage
```

**For AKS:**
```bash
az aks nodepool update \
  --cluster-name myCluster \
  --resource-group myRG \
  --nodepool-name mypool \
  --max-surge 1
```

### 2. **Use Node Affinity to Prefer Upgraded Nodes**

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
              - key: kubernetes.io/arch
                operator: In
                values: ["amd64"]
              # Prefer nodes with newer kubelet version
          - weight: 50
            preference:
              matchExpressions:
              - key: node.kubernetes.io/instance-type
                operator: In
                values: ["your-new-instance-type"]
```

### 3. **Implement a Custom Drain Strategy**

```bash
#!/bin/bash
# Custom drain script with better timing

NODE_NAME=$1
TIMEOUT=300

echo "Pre-draining checks for $NODE_NAME"

# Wait for replacement nodes to be ready
kubectl wait --for=condition=Ready node -l pool=new-pool --timeout=600s

# Cordon the node first
kubectl cordon $NODE_NAME

# Wait a bit for scheduler to avoid it
sleep 30

# Graceful drain with longer timeout
kubectl drain $NODE_NAME \
  --ignore-daemonsets \
  --delete-emptydir-data \
  --force \
  --timeout=${TIMEOUT}s \
  --grace-period=60

echo "Node $NODE_NAME drained successfully"
```

### 4. **Use Pod Disruption Budgets**

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  minAvailable: 2  # Or use maxUnavailable: 1
  selector:
    matchLabels:
      app: my-app
---
# This slows down draining, giving pods time to land properly
```

### 5. **Node Pool Blue/Green Strategy**

```bash
# Create new node pool first
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-strategy
data:
  phase: "blue-green"
  current-pool: "old-pool"
  target-pool: "new-pool"
EOF

# Gradually taint old nodes instead of draining immediately
kubectl taint nodes -l pool=old-pool upgrade=in-progress:NoSchedule
sleep 60
kubectl taint nodes -l pool=old-pool upgrade=in-progress:NoExecute --overwrite
```

### 6. **Monitoring Script to Track Pod Movement**

```bash
#!/bin/bash
# Monitor pod churn during upgrade

watch -n 5 '
echo "=== Pod Distribution ==="
kubectl get pods -o wide | awk "{print \$7}" | sort | uniq -c

echo "=== Node Status ==="
kubectl get nodes -o custom-columns=NAME:.metadata.name,STATUS:.status.conditions[-1].type,SCHEDULABLE:.spec.unschedulable

echo "=== Recent Pod Events ==="
kubectl get events --sort-by=.firstTimestamp | grep -E "(Killing|Scheduled|Failed)" | tail -10
'
```

### 7. **Kubernetes-Native Solution with Priorities**

```yaml
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: high-priority-upgrade
value: 1000
globalDefault: false
description: "High priority for pods during upgrades"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: critical-app
spec:
  template:
    spec:
      priorityClassName: high-priority-upgrade
      # These pods get scheduled first on new nodes
```

## Best Practices

1. **Upgrade during low traffic**: Reduces impact of pod shuffling
2. **Monitor resource usage**: Ensure new nodes can handle the load
3. **Use readiness probes**: Prevent traffic to pods still starting up
4. **Set appropriate resource requests**: Helps scheduler make better decisions

The key is controlling the pace of the upgrade and giving the scheduler better information about which nodes are "safe" targets for pod placement.