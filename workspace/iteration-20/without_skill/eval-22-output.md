You're experiencing a classic node pool upgrade timing issue! This "musical chairs" problem occurs when your upgrade strategy isn't properly coordinating node drainage with pod placement. Here's what's happening and how to fix it:

## Root Causes

1. **Parallel node upgrades** - Multiple nodes being drained simultaneously
2. **Pod anti-affinity not considering upgrade status** - Scheduler doesn't know which nodes are "safe"
3. **Insufficient upgraded capacity** - Not enough upgraded nodes available when pods are evicted

## Solutions

### 1. Control Upgrade Parallelism

**For managed Kubernetes (EKS, GKE, AKS):**

```yaml
# EKS - Update Config
apiVersion: eksctl.io/v1alpha5
kind: ClusterConfig
metadata:
  name: my-cluster
managedNodeGroups:
  - name: worker-nodes
    updateConfig:
      maxUnavailablePercentage: 25  # Only 25% of nodes upgrade at once
      # OR
      maxUnavailable: 1  # Only 1 node at a time
```

```bash
# GKE - Surge upgrade settings
gcloud container node-pools update POOL_NAME \
  --cluster=CLUSTER_NAME \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=0
```

### 2. Implement Staged Upgrades

Create a custom upgrade strategy:

```yaml
# staged-upgrade-script.sh
#!/bin/bash

NODES=$(kubectl get nodes -l node-pool=workers --no-headers -o name)
NODE_COUNT=$(echo "$NODES" | wc -l)
BATCH_SIZE=2

echo "$NODES" | while read -r node; do
    echo "Upgrading $node"
    
    # Cordon and drain
    kubectl cordon "$node"
    kubectl drain "$node" --ignore-daemonsets --delete-emptydir-data --force
    
    # Wait for pods to reschedule and stabilize
    sleep 30
    kubectl wait --for=condition=Ready pods --all --timeout=300s
    
    # Replace/upgrade the node (platform specific)
    # ... node replacement logic ...
    
    # Wait for new node to be ready
    kubectl wait --for=condition=Ready node "$node" --timeout=600s
    
    # Small delay before next node
    sleep 60
done
```

### 3. Use Node Affinity to Guide Placement

Label your upgraded nodes and use affinity:

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
              - key: node.kubernetes.io/upgraded
                operator: In
                values: ["true"]
          # Avoid nodes marked for upgrade
          - weight: 50
            preference:
              matchExpressions:
              - key: node.kubernetes.io/upgrade-pending
                operator: NotIn
                values: ["true"]
```

### 4. Pre-provision Upgraded Capacity

For cloud providers, add extra capacity before starting:

```yaml
# Temporarily scale up with new nodes
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-strategy
data:
  approach: |
    1. Add 2-3 new nodes with upgraded version
    2. Wait for them to be Ready
    3. Begin draining old nodes one by one
    4. Remove excess capacity after upgrade complete
```

### 5. Use PodDisruptionBudgets Strategically

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
# For critical services, be more restrictive
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: critical-app-pdb
spec:
  maxUnavailable: 0  # Forces very careful scheduling
  selector:
    matchLabels:
      app: critical-app
```

### 6. Monitor and Orchestrate with Custom Controller

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-orchestrator
data:
  script.sh: |
    #!/bin/bash
    
    # Function to check if pods have stable placement
    check_pod_stability() {
        # Wait for all pods to be running and ready
        kubectl wait --for=condition=Ready pods --all --timeout=300s
        
        # Check no pods are pending
        PENDING=$(kubectl get pods --field-selector=status.phase=Pending --no-headers | wc -l)
        if [ "$PENDING" -gt 0 ]; then
            echo "Warning: $PENDING pods still pending"
            return 1
        fi
        return 0
    }
    
    # Upgrade nodes one by one
    for node in $(kubectl get nodes -l upgrade-group=batch-1 -o name); do
        echo "Processing $node"
        
        # Check current pod distribution
        kubectl describe node "${node#node/}" | grep "Non-terminated Pods"
        
        # Cordon first
        kubectl cordon "$node"
        
        # Wait a bit for scheduler to prefer other nodes
        sleep 30
        
        # Drain with careful settings
        kubectl drain "$node" \
            --ignore-daemonsets \
            --delete-emptydir-data \
            --grace-period=300 \
            --timeout=600s
        
        # Verify pod stability before continuing
        if check_pod_stability; then
            echo "Pods stable, continuing with node replacement"
            # Replace node here
        else
            echo "Pods not stable, pausing upgrade"
            exit 1
        fi
    done
```

### 7. Blue-Green Node Pool Strategy

For zero-disruption upgrades:

```bash
# Create new node pool with upgraded version
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: blue-green-upgrade
data:
  strategy: |
    # Phase 1: Create green pool
    - Create new node pool (green) with target version
    - Wait for nodes to be Ready
    
    # Phase 2: Migrate workloads
    - Cordon all blue pool nodes
    - Pods will naturally reschedule to green nodes
    - Monitor pod distribution
    
    # Phase 3: Clean up
    - Once all workloads on green nodes, delete blue pool
EOF
```

## Quick Fix for Ongoing Upgrades

If you're in the middle of a problematic upgrade:

```bash
# 1. Pause the upgrade
kubectl patch nodepool NODEPOOL_NAME -p '{"spec":{"upgradePolicy":{"maxUnavailable":0}}}'

# 2. Let current disruptions settle
kubectl wait --for=condition=Ready pods --all --timeout=600s

# 3. Resume with conservative settings
kubectl patch nodepool NODEPOOL_NAME -p '{"spec":{"upgradePolicy":{"maxUnavailable":1}}}'
```

The key is controlling the upgrade velocity and ensuring pods have stable landing spots before continuing the upgrade process.