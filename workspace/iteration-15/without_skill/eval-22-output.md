This is a classic node pool upgrade orchestration issue! You're experiencing this because the upgrade process isn't coordinating pod placement with the upgrade sequence. Here's what's happening and how to fix it:

## Root Cause Analysis

**Why this happens:**
- Kubernetes scheduler picks available nodes based on current capacity/affinity rules
- The scheduler doesn't know which nodes are "next in line" for draining
- Default upgrade strategies often drain multiple nodes simultaneously
- Pod disruption budgets may force placement on soon-to-be-drained nodes

## Immediate Solutions

### 1. Control Upgrade Parallelism
```yaml
# For managed clusters (GKE example)
gcloud container node-pools update POOL_NAME \
  --cluster=CLUSTER_NAME \
  --max-surge=1 \
  --max-unavailable=0
```

```yaml
# For cluster-autoscaler managed upgrades
apiVersion: v1
kind: ConfigMap
metadata:
  name: cluster-autoscaler-status
data:
  max-node-provision-time: "15m"
  scale-down-delay-after-add: "10m"
```

### 2. Use Node Selectors/Affinity for Critical Workloads
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: critical-app
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
                values: ["newer-instance-type"]
          - weight: 50
            preference:
              matchExpressions:
              - key: kubernetes.io/arch
                operator: In
                values: ["amd64"]
```

### 3. Implement Strategic Node Labeling
```bash
# Pre-label nodes by upgrade wave
kubectl label nodes node-1 node-2 node-3 upgrade-wave=1
kubectl label nodes node-4 node-5 node-6 upgrade-wave=2
kubectl label nodes node-7 node-8 node-9 upgrade-wave=3

# Update deployments to prefer later waves
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
              - key: upgrade-wave
                operator: In
                values: ["3", "2"]  # Prefer nodes upgraded later
```

## Better Long-term Approaches

### 1. Custom Upgrade Controller
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: controlled-upgrade
spec:
  template:
    spec:
      containers:
      - name: upgrade-controller
        image: your-registry/upgrade-controller:latest
        env:
        - name: UPGRADE_STRATEGY
          value: "sequential"
        - name: WAIT_FOR_PODS
          value: "true"
        - name: MAX_PARALLEL_NODES
          value: "1"
```

### 2. Use Pod Topology Spread Constraints
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
            app: your-app
      - maxSkew: 2
        topologyKey: kubernetes.io/hostname
        whenUnsatisfiable: ScheduleAnyway
        labelSelector:
          matchLabels:
            app: your-app
```

### 3. Implement Pre-Upgrade Node Preparation
```bash
#!/bin/bash
# upgrade-orchestrator.sh

# Phase 1: Ensure new nodes are ready
kubectl get nodes -l node-pool=new --no-headers | wc -l
if [ $? -lt 3 ]; then
  echo "Waiting for minimum new nodes..."
  exit 1
fi

# Phase 2: Taint nodes to be upgraded
kubectl taint nodes -l node-pool=old upgrade=in-progress:NoSchedule

# Phase 3: Drain one node at a time
OLD_NODES=$(kubectl get nodes -l node-pool=old -o name)
for node in $OLD_NODES; do
  echo "Draining $node"
  kubectl drain $node --ignore-daemonsets --delete-emptydir-data
  
  # Wait for pods to be rescheduled
  sleep 60
  
  # Verify pods are stable before next node
  kubectl get pods --all-namespaces --field-selector spec.nodeName="" | grep -v "Completed"
  if [ $? -eq 0 ]; then
    echo "Waiting for pod scheduling to stabilize..."
    sleep 120
  fi
done
```

## Cloud-Specific Solutions

### GKE
```bash
# Use surge upgrade with careful settings
gcloud container node-pools update POOL_NAME \
  --cluster=CLUSTER_NAME \
  --zone=ZONE \
  --max-surge=1 \
  --max-unavailable=0 \
  --upgrade-settings='{"maxSurge": 1, "maxUnavailable": 0, "strategy": "SURGE"}'
```

### EKS
```yaml
# managed-node-group.yaml
apiVersion: eks.aws.crossplane.io/v1alpha1
kind: NodeGroup
spec:
  updateConfig:
    maxUnavailable: 1
    maxUnavailablePercentage: null
  scalingConfig:
    desiredSize: 6
    maxSize: 9  # Allow surge during upgrade
    minSize: 3
```

### AKS
```bash
az aks nodepool upgrade \
  --resource-group myResourceGroup \
  --cluster-name myCluster \
  --name mynodepool \
  --max-surge 1 \
  --no-wait
```

## Monitoring and Validation

### Track Pod Movement
```bash
# Monitor pod churn during upgrade
kubectl get events --sort-by='.lastTimestamp' | grep -E "(Killing|Created|Scheduled)"

# Watch for pods stuck in pending
kubectl get pods --all-namespaces --field-selector status.phase=Pending -w
```

### Upgrade Health Check Script
```bash
#!/bin/bash
# upgrade-health.sh

echo "=== Upgrade Health Check ==="
echo "Nodes by version:"
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion

echo -e "\nPods in non-Running state:"
kubectl get pods --all-namespaces --field-selector status.phase!=Running,status.phase!=Succeeded

echo -e "\nNode pressure conditions:"
kubectl get nodes -o custom-columns=NAME:.metadata.name,READY:.status.conditions[?(@.type==\"Ready\")].status,PRESSURE:.status.conditions[?(@.type==\"MemoryPressure\")].status
```

The key is to **control the upgrade tempo** and **guide pod placement** rather than letting the default scheduler make uninformed decisions. Start with reducing parallelism and adding node preferences, then consider implementing a more sophisticated upgrade orchestration if you do this frequently.