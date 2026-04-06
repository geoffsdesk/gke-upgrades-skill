This is a common GKE upgrade issue. Here's how to diagnose and fix the stuck node pool upgrade:

## 1. Check Current Status

First, get detailed information about the upgrade:

```bash
# Check cluster and node pool status
gcloud container clusters describe CLUSTER_NAME --region us-east1

# Check node pool upgrade status
gcloud container node-pools describe NODE_POOL_NAME \
  --cluster CLUSTER_NAME --region us-east1

# Check node conditions
kubectl get nodes -o wide
kubectl describe nodes
```

## 2. Identify Pod Drainage Issues

Check what's preventing pods from draining:

```bash
# Check pods stuck in terminating state
kubectl get pods --all-namespaces | grep Terminating

# Check PodDisruptionBudgets (common culprit)
kubectl get pdb --all-namespaces

# Check for pods without controllers
kubectl get pods --all-namespaces --field-selector=status.phase=Running | \
  grep -v "ReplicaSet\|DaemonSet\|StatefulSet"
```

## 3. Common Causes & Solutions

### PodDisruptionBudgets (Most Common)
```bash
# List PDBs that might be blocking
kubectl get pdb --all-namespaces -o yaml

# Temporarily relax restrictive PDBs
kubectl patch pdb PDB_NAME -n NAMESPACE -p '{"spec":{"minAvailable":0}}'
```

### Stuck Pods
```bash
# Force delete stuck terminating pods
kubectl delete pod POD_NAME -n NAMESPACE --force --grace-period=0

# Check for finalizers preventing deletion
kubectl get pod POD_NAME -n NAMESPACE -o yaml | grep finalizers -A5
```

### Local Storage Issues
```bash
# Check for pods using local storage/hostPath
kubectl get pods --all-namespaces -o yaml | grep -i "hostPath\|local"
```

## 4. Force Progress (If Safe)

If pods are safe to forcibly remove:

```bash
# Cordon and drain specific nodes manually
kubectl cordon NODE_NAME
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --force
```

## 5. Resume/Restart Upgrade

If the upgrade is completely stuck:

```bash
# Cancel current upgrade (if necessary)
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME --region us-east1 \
  --node-version 1.31

# Then restart the upgrade
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME --region us-east1 \
  --node-version 1.32
```

## 6. Prevention for Next Time

```bash
# Use surge upgrades for faster, less disruptive upgrades
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME --region us-east1 \
  --max-surge-upgrade 3 --max-unavailable-upgrade 1
```

## Quick Emergency Actions

If you need to unblock immediately:

1. **Identify blocking PDBs**: `kubectl get pdb --all-namespaces`
2. **Temporarily disable them**: `kubectl delete pdb BLOCKING_PDB -n NAMESPACE`
3. **Force delete stuck pods**: `kubectl delete pod --force --grace-period=0`
4. **The upgrade should resume automatically**

## What to Check Right Now

Run these commands in order:
```bash
kubectl get pdb --all-namespaces
kubectl get pods --all-namespaces | grep Terminating
kubectl get events --sort-by='.lastTimestamp' | tail -20
```

The most likely culprit is a PodDisruptionBudget preventing the required number of pods from being terminated simultaneously. Let me know what you find from these commands!