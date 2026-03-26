This is a common GKE upgrade issue. Let's diagnose and fix it step by step:

## 1. Check Current Upgrade Status

```bash
# Check cluster and node pool status
kubectl get nodes -o wide
gcloud container clusters describe CLUSTER_NAME --zone=us-east1 --format="value(status)"
gcloud container node-pools describe NODE_POOL_NAME --cluster=CLUSTER_NAME --zone=us-east1
```

## 2. Identify Pod Drainage Issues

The most common cause is pods that can't be evicted. Check for:

```bash
# Check pods that might be blocking drainage
kubectl get pods --all-namespaces --field-selector=status.phase=Running

# Look for pods without proper disruption budgets
kubectl get pdb --all-namespaces

# Check for pods with local storage or specific node selectors
kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.nodeName}{"\t"}{.spec.volumes[*].hostPath.path}{"\n"}{end}'
```

## 3. Common Blocking Issues & Solutions

### A. PodDisruptionBudgets (PDBs) Too Restrictive
```bash
# Check PDBs
kubectl get pdb --all-namespaces -o wide

# Temporarily relax restrictive PDBs
kubectl patch pdb PDB_NAME -n NAMESPACE -p '{"spec":{"minAvailable":0}}'
```

### B. Pods with Local Storage
```bash
# Find pods with hostPath or emptyDir volumes
kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.volumes[*]}{"\n"}{end}' | grep -E "(hostPath|emptyDir)"

# These may need manual intervention - consider if data can be lost
kubectl delete pod POD_NAME -n NAMESPACE --force --grace-period=0
```

### C. DaemonSets or System Pods
```bash
# Check for problematic DaemonSets
kubectl get ds --all-namespaces

# System pods in kube-system that might be stuck
kubectl get pods -n kube-system --field-selector=status.phase!=Running
```

## 4. Force Resolution

### Option 1: Manual Pod Cleanup
```bash
# Identify nodes being upgraded
kubectl get nodes -l cloud.google.com/gke-nodepool=NODE_POOL_NAME

# Force delete stuck pods (be cautious!)
kubectl get pods --all-namespaces --field-selector spec.nodeName=NODE_NAME
kubectl delete pod POD_NAME -n NAMESPACE --force --grace-period=0
```

### Option 2: Pause and Resume Upgrade
```bash
# Cancel current upgrade (if needed)
gcloud container clusters upgrade CLUSTER_NAME --zone=us-east1 --cancel

# Wait a few minutes, then retry
gcloud container node-pools upgrade NODE_POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=us-east1 \
    --node-version=1.32
```

### Option 3: Surge Upgrade Settings
```bash
# Check current surge settings
gcloud container node-pools describe NODE_POOL_NAME --cluster=CLUSTER_NAME --zone=us-east1 --format="value(upgradeSettings)"

# Increase surge capacity for faster upgrades
gcloud container node-pools update NODE_POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=us-east1 \
    --max-surge=3 \
    --max-unavailable=1
```

## 5. Monitor Progress

```bash
# Watch the upgrade progress
watch -n 30 'kubectl get nodes -o wide'

# Monitor events
kubectl get events --sort-by='.lastTimestamp' -A | tail -20

# Check GKE operations
gcloud container operations list --filter="targetLink:CLUSTER_NAME"
```

## 6. Prevention for Future Upgrades

```bash
# Set appropriate PDBs
cat <<EOF | kubectl apply -f -
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: app-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: your-app
EOF

# Configure surge settings before upgrades
gcloud container node-pools update NODE_POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=us-east1 \
    --max-surge=2 \
    --max-unavailable=1
```

## Immediate Action Plan:

1. **First**, check for restrictive PDBs and temporarily relax them
2. **Then**, look for pods with local storage that need manual deletion
3. **If still stuck**, consider canceling and restarting the upgrade with better surge settings
4. **Monitor** events and node status throughout

Start with checking PDBs - that's the most common culprit for stuck upgrades. Let me know what you find!