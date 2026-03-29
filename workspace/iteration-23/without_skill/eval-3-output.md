This is a common GKE upgrade issue. Let's diagnose and fix it systematically:

## 1. First, check the upgrade status and identify stuck nodes

```bash
# Check cluster upgrade status
gcloud container clusters describe CLUSTER_NAME --zone=us-east1-b --format="value(currentNodeVersion,currentMasterVersion)"

# Check node pool upgrade status
gcloud container node-pools describe NODE_POOL_NAME --cluster=CLUSTER_NAME --zone=us-east1-b

# List nodes and their versions
kubectl get nodes -o wide
```

## 2. Identify problematic pods that won't drain

```bash
# Check for pods that are blocking drainage
kubectl get pods --all-namespaces --field-selector=status.phase!=Running,status.phase!=Succeeded

# Look for PodDisruptionBudgets that might be too restrictive
kubectl get pdb --all-namespaces

# Check for pods stuck in terminating state
kubectl get pods --all-namespaces | grep Terminating
```

## 3. Common culprits and fixes

### **PodDisruptionBudgets (Most common cause)**
```bash
# Check PDBs that might be blocking
kubectl get pdb --all-namespaces -o wide

# Temporarily relax restrictive PDBs
kubectl patch pdb PDB_NAME -n NAMESPACE --type='merge' -p='{"spec":{"minAvailable":0}}'
```

### **StatefulSets or persistent workloads**
```bash
# Check StatefulSets
kubectl get statefulsets --all-namespaces

# Check for pods with local storage
kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.spec.volumes[?(@.hostPath)]}{"\n"}{end}'
```

### **Daemonsets on specific nodes**
```bash
# Check DaemonSets
kubectl get ds --all-namespaces
```

## 4. Force the upgrade process

### **Option A: Manually drain problematic nodes**
```bash
# Identify which nodes are being upgraded
kubectl get nodes --sort-by=.metadata.creationTimestamp

# Manually drain stuck nodes (replace NODE_NAME)
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --force --grace-period=30

# If that doesn't work, try shorter grace period
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --force --grace-period=0
```

### **Option B: Temporarily scale down blocking workloads**
```bash
# Scale down deployments that might be causing issues
kubectl scale deployment DEPLOYMENT_NAME --replicas=0 -n NAMESPACE

# After upgrade completes, scale back up
kubectl scale deployment DEPLOYMENT_NAME --replicas=ORIGINAL_COUNT -n NAMESPACE
```

## 5. If still stuck, cancel and retry

```bash
# Cancel the current upgrade operation
gcloud container operations list --filter="operationType:UPGRADE_NODES" --format="value(name)"
gcloud container operations cancel OPERATION_NAME --zone=us-east1-b

# Wait a few minutes, then retry the upgrade
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster=CLUSTER_NAME \
  --zone=us-east1-b \
  --node-version=1.32
```

## 6. Prevention for future upgrades

```bash
# Before future upgrades, prepare your cluster:

# 1. Review and adjust PDBs
kubectl get pdb --all-namespaces -o yaml

# 2. Use surge upgrade settings for faster upgrades
gcloud container node-pools update NODE_POOL_NAME \
  --cluster=CLUSTER_NAME \
  --zone=us-east1-b \
  --max-surge-upgrade=2 \
  --max-unavailable-upgrade=1
```

## Quick troubleshooting checklist:

1. **Check PDBs first** - they're the #1 cause of stuck upgrades
2. **Look for StatefulSets** - they need special handling
3. **Check for local storage** - pods with hostPath volumes are sticky
4. **Review custom operators** - they might not handle disruptions well
5. **Check node cordoning** - ensure nodes are properly cordoned

Try the PDB check first - that resolves about 70% of stuck upgrade cases. Let me know what you find and I can provide more specific guidance!