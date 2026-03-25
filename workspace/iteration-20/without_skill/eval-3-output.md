This is a common issue with GKE node pool upgrades. Here's a systematic approach to diagnose and fix the stuck upgrade:

## 1. Check Current Status

First, get detailed information about the upgrade:

```bash
# Check node pool status
gcloud container node-pools describe NODEPOOL_NAME \
  --cluster=CLUSTER_NAME --zone=us-east1-c

# Check node conditions
kubectl get nodes -o wide
kubectl describe nodes | grep -A5 -B5 "SchedulingDisabled\|Unschedulable"
```

## 2. Identify Pod Drainage Issues

The most common cause is pods that can't be evicted:

```bash
# Check for pods with disruption issues
kubectl get pods --all-namespaces --field-selector=status.phase!=Running,status.phase!=Succeeded

# Look for PodDisruptionBudgets that might be blocking drainage
kubectl get pdb --all-namespaces

# Check for pods without proper disruption budgets
kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.spec.nodeName}{"\n"}{end}' | grep NODE_NAME
```

## 3. Common Blocking Issues and Fixes

### PodDisruptionBudgets (PDBs)
```bash
# Check restrictive PDBs
kubectl get pdb --all-namespaces -o yaml | grep -A5 -B5 "minAvailable\|maxUnavailable"

# Temporarily adjust overly restrictive PDBs
kubectl patch pdb PDB_NAME -n NAMESPACE --type merge -p '{"spec":{"minAvailable":0}}'
```

### DaemonSets
```bash
# Check for DaemonSets that might be problematic
kubectl get daemonsets --all-namespaces

# For stuck DaemonSet pods, you might need to delete them manually
kubectl delete pod POD_NAME -n NAMESPACE --grace-period=0 --force
```

### StatefulSets or Local Storage
```bash
# Check for StatefulSets or pods with local storage
kubectl get statefulsets --all-namespaces
kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.volumes[*].hostPath.path}{"\n"}{end}'
```

## 4. Force Progress on Stuck Nodes

If drainage is the issue:

```bash
# Manually drain problematic nodes
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --force --grace-period=30

# For very stuck pods, force delete them
kubectl delete pod POD_NAME -n NAMESPACE --grace-period=0 --force
```

## 5. Check Cluster Events

```bash
# Look for relevant events
kubectl get events --all-namespaces --sort-by='.lastTimestamp' | tail -20

# Check GKE operation logs
gcloud logging read 'resource.type="gke_cluster" AND resource.labels.cluster_name="CLUSTER_NAME"' --limit=50
```

## 6. Alternative Solutions

If the upgrade remains stuck:

### Option 1: Cancel and Retry
```bash
# Cancel current operation (if possible)
gcloud container operations cancel OPERATION_ID --zone=us-east1-c

# Then retry with different parameters
gcloud container node-pools upgrade NODEPOOL_NAME \
  --cluster=CLUSTER_NAME \
  --zone=us-east1-c \
  --max-surge=1 \
  --max-unavailable=0
```

### Option 2: Adjust Upgrade Settings
```bash
# Modify the upgrade strategy to be more conservative
gcloud container node-pools update NODEPOOL_NAME \
  --cluster=CLUSTER_NAME \
  --zone=us-east1-c \
  --max-surge=1 \
  --max-unavailable=0
```

## 7. Prevention for Future Upgrades

```bash
# Before next upgrade, ensure proper PDBs
kubectl get pdb --all-namespaces

# Set appropriate upgrade disruption settings
gcloud container node-pools update NODEPOOL_NAME \
  --cluster=CLUSTER_NAME \
  --zone=us-east1-c \
  --enable-autoupgrade \
  --max-surge=1 \
  --max-unavailable=0
```

## Immediate Action Plan:

1. Run the pod drainage check commands above
2. Look for restrictive PDBs and temporarily adjust them
3. Manually drain the stuck nodes
4. Force delete any persistently stuck pods
5. Monitor the upgrade progress

The upgrade should resume once the blocking pods are resolved. If you're still stuck after trying these steps, you may need to contact Google Cloud Support, especially for Standard clusters where you have less control over the underlying infrastructure.

Would you like me to help you run through any of these specific diagnostic steps?