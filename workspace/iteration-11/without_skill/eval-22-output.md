You've perfectly described the "musical chairs" problem during rolling node upgrades! This happens because the cluster scheduler doesn't know about your upgrade timeline and treats all schedulable nodes as equally valid targets. Here's what's happening and how to fix it:

## Root Cause
During rolling upgrades, pods get evicted from nodes being drained and land on nodes that haven't been upgraded yet - but those nodes are next in line to be drained, causing repeated evictions.

## Solutions

### 1. **Control Upgrade Batching and Timing**

```yaml
# For managed node groups (EKS example)
apiVersion: eksctl.io/v1alpha5
kind: ClusterConfig
nodeGroups:
  - name: workers
    updateConfig:
      maxUnavailable: 1  # Upgrade one node at a time
      # OR
      maxUnavailablePercentage: 25  # Upgrade 25% at a time
```

### 2. **Use Node Taints During Upgrades**

```bash
# Before draining, taint nodes that will be upgraded soon
kubectl taint nodes node-to-upgrade-soon scheduling=disabled:NoSchedule

# This prevents new pods from landing on nodes about to be upgraded
# Remove taint after upgrade:
kubectl taint nodes upgraded-node scheduling=disabled:NoSchedule-
```

### 3. **Implement Node Selectors for Critical Workloads**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: critical-app
spec:
  template:
    spec:
      nodeSelector:
        node.kubernetes.io/instance-type: "upgraded"  # Custom label
      # OR use node affinity for more control
      affinity:
        nodeAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            preference:
              matchExpressions:
              - key: node-upgrade-status
                operator: In
                values: ["completed"]
```

### 4. **Strategic Upgrade Sequencing**

```bash
#!/bin/bash
# Upgrade script with proper sequencing

NODES=($(kubectl get nodes -o name))
BATCH_SIZE=1

for ((i=0; i<${#NODES[@]}; i+=BATCH_SIZE)); do
    batch=("${NODES[@]:i:BATCH_SIZE}")
    
    echo "Upgrading batch: ${batch[*]}"
    
    # Taint nodes in next batch to prevent scheduling
    if [ $((i + BATCH_SIZE)) -lt ${#NODES[@]} ]; then
        next_batch=("${NODES[@]:$((i + BATCH_SIZE)):BATCH_SIZE}")
        for node in "${next_batch[@]}"; do
            kubectl taint node ${node#node/} upgrade-pending=true:NoSchedule
        done
    fi
    
    # Upgrade current batch
    for node in "${batch[@]}"; do
        kubectl drain ${node#node/} --ignore-daemonsets --delete-emptydir-data
        # Perform upgrade here
        kubectl uncordon ${node#node/}
        kubectl label ${node#node/} node-upgrade-status=completed
    done
    
    # Wait for pods to stabilize
    sleep 60
done
```

### 5. **Use Pod Disruption Budgets Strategically**

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: app-pdb
spec:
  minAvailable: 2  # Ensure minimum replicas during disruption
  selector:
    matchLabels:
      app: my-app
---
# Also ensure you have enough replicas spread across nodes
apiVersion: apps/v1
kind: Deployment
spec:
  replicas: 4  # More than your PDB minimum
  template:
    spec:
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchExpressions:
                - key: app
                  operator: In
                  values: ["my-app"]
              topologyKey: kubernetes.io/hostname
```

### 6. **Monitor and Validate During Upgrades**

```bash
# Watch pod movements during upgrade
kubectl get pods -o wide --watch

# Check for pods stuck in pending state
kubectl get pods --field-selector=status.phase=Pending

# Monitor node status
kubectl get nodes -o custom-columns="NAME:.metadata.name,STATUS:.status.conditions[-1].type,SCHEDULABLE:.spec.unschedulable"
```

### 7. **For Cloud-Managed Solutions**

```bash
# AWS EKS - use managed node group updates
aws eks update-nodegroup-version \
    --cluster-name my-cluster \
    --nodegroup-name my-nodegroup \
    --launch-template version='$Latest' \
    --update-config maxUnavailable=1

# GKE - control upgrade disruption
gcloud container node-pools update POOL_NAME \
    --cluster=CLUSTER_NAME \
    --max-surge=1 \
    --max-unavailable=1
```

## Best Practices Summary

1. **Always upgrade in small batches** (1 node or 25% max)
2. **Taint nodes before they're due for upgrade** to prevent scheduling
3. **Use pod disruption budgets** to control disruption impact
4. **Ensure sufficient replicas** spread across nodes
5. **Monitor the process** and be ready to pause if issues arise
6. **Label nodes** after successful upgrade for workload placement

The key is giving the scheduler better information about which nodes are "safe" for scheduling during the upgrade process!