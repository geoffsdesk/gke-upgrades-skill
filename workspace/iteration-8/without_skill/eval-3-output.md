This is a common GKE upgrade issue. Here's how to diagnose and fix the stuck node pool upgrade:

## 1. Check Node Pool Status and Events

```bash
# Check detailed node pool status
kubectl get nodes -o wide
gcloud container node-pools describe [NODE_POOL_NAME] --cluster=[CLUSTER_NAME] --zone=us-east1

# Check for events and conditions
kubectl get events --sort-by='.lastTimestamp' | grep -i drain
kubectl describe nodes | grep -A 10 -B 5 "Conditions"
```

## 2. Identify Pod Drainage Issues

The most common cause is pods that can't be evicted:

```bash
# Check for problematic pods
kubectl get pods --all-namespaces --field-selector=status.phase!=Running
kubectl get pods --all-namespaces -o wide | grep -E "(Pending|Terminating|Unknown)"

# Look for PodDisruptionBudgets that might be blocking drainage
kubectl get pdb --all-namespaces
kubectl describe pdb --all-namespaces
```

## 3. Common Blockers and Solutions

### A. PodDisruptionBudgets (PDBs)
```bash
# Check PDB status
kubectl get pdb --all-namespaces -o yaml

# Temporarily relax restrictive PDBs
kubectl patch pdb [PDB_NAME] -n [NAMESPACE] --type='merge' -p='{"spec":{"minAvailable":0}}'
```

### B. DaemonSets without proper tolerations
```bash
# Check DaemonSets
kubectl get daemonsets --all-namespaces
kubectl describe ds [DAEMONSET_NAME] -n [NAMESPACE]
```

### C. Pods with local storage or no replica sets
```bash
# Find pods without controllers (these need manual deletion)
kubectl get pods --all-namespaces --field-selector=status.phase=Running -o jsonpath='{range .items[?(@.metadata.ownerReferences[0].kind!="ReplicaSet")]}{.metadata.namespace}{"\t"}{.metadata.name}{"\n"}{end}'
```

## 4. Force Resolution

If pods are truly stuck:

```bash
# Force delete stuck terminating pods
kubectl delete pod [POD_NAME] -n [NAMESPACE] --grace-period=0 --force

# Or drain nodes manually (be very careful)
kubectl drain [NODE_NAME] --ignore-daemonsets --delete-emptydir-data --force --grace-period=0
```

## 5. Check Resource Constraints

```bash
# Verify cluster has capacity for rescheduled pods
kubectl top nodes
kubectl describe nodes | grep -A 5 "Allocated resources"

# Check if there are scheduling issues
kubectl get events --sort-by='.lastTimestamp' | grep -i "FailedScheduling"
```

## 6. GKE-Specific Checks

```bash
# Check cluster operation status
gcloud container operations list --filter="operationType:UPGRADE_NODES AND status:RUNNING"

# Get detailed operation info
gcloud container operations describe [OPERATION_ID] --zone=us-east1
```

## 7. Emergency Solutions

If the upgrade is critically stuck:

### Option A: Cancel and retry
```bash
# Note: This might not work if upgrade is too far along
gcloud container node-pools update [NODE_POOL_NAME] \
  --cluster=[CLUSTER_NAME] \
  --zone=us-east1 \
  --cancel-operation
```

### Option B: Create new node pool (safest)
```bash
# Create new node pool with 1.32
gcloud container node-pools create new-pool-132 \
  --cluster=[CLUSTER_NAME] \
  --zone=us-east1 \
  --node-version=1.32 \
  --num-nodes=4

# Gradually migrate workloads, then delete old pool
```

## 8. Prevention for Next Time

```bash
# Set up proper PDBs
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: my-app

# Use surge upgrades for faster updates
gcloud container node-pools update [NODE_POOL_NAME] \
  --max-surge-upgrade=3 \
  --max-unavailable-upgrade=1
```

Start with checking the events and PDBs - those are the most likely culprits. Let me know what you find and I can help with more specific solutions!