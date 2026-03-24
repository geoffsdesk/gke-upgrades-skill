This is a common GKE upgrade issue. Here's a systematic approach to diagnose and fix the stuck node pool upgrade:

## 1. Check Current Upgrade Status

```bash
# Check the upgrade operation status
gcloud container operations list --region=us-east1

# Get detailed info about the stuck operation
gcloud container operations describe OPERATION_ID --region=us-east1

# Check node pool status
kubectl get nodes -o wide
```

## 2. Identify Why Pods Aren't Draining

The most common cause is Pod Disruption Budgets (PDBs) or pods that can't be evicted:

```bash
# Check for problematic PDBs
kubectl get pdb --all-namespaces

# Look for pods that might be blocking drainage
kubectl get pods --all-namespaces --field-selector=status.phase=Running

# Check for DaemonSets or static pods
kubectl get daemonsets --all-namespaces
```

## 3. Common Issues and Fixes

### A. Restrictive Pod Disruption Budgets
```bash
# Check PDB details
kubectl describe pdb --all-namespaces

# Temporarily relax PDBs if safe to do so
kubectl patch pdb YOUR_PDB_NAME -p '{"spec":{"minAvailable":0}}'
```

### B. Pods with No Disruption Budget
```bash
# Look for single-replica deployments without PDBs
kubectl get deployments --all-namespaces -o jsonpath='{range .items[?(@.spec.replicas==1)]}{.metadata.namespace}{" "}{.metadata.name}{"\n"}{end}'
```

### C. Local Storage or HostPath Volumes
```bash
# Check for pods using local storage
kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{" "}{.metadata.name}{" "}{.spec.volumes[*].hostPath.path}{"\n"}{end}' | grep -v "^[^[:space:]]*[[:space:]]*[^[:space:]]*[[:space:]]*$"
```

## 4. Force the Upgrade to Continue

If you've identified and resolved the blocking issues:

```bash
# Cancel the current upgrade operation
gcloud container operations cancel OPERATION_ID --region=us-east1

# Start a new upgrade with surge settings for better reliability
gcloud container node-pools update YOUR_NODE_POOL \
  --cluster=YOUR_CLUSTER \
  --region=us-east1 \
  --node-version=1.32 \
  --max-surge-upgrade=2 \
  --max-unavailable-upgrade=0
```

## 5. Alternative: Manual Node Cordoning/Draining

If the automatic upgrade is still stuck:

```bash
# Identify nodes that need upgrading
kubectl get nodes -l cloud.google.com/gke-nodepool=YOUR_NODE_POOL

# Manually cordon and drain problematic nodes
kubectl cordon NODE_NAME
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --force --grace-period=300
```

## 6. Emergency Fixes for Common Blockers

### Temporarily Scale Down Problematic Workloads
```bash
# Scale down single-replica deployments temporarily
kubectl scale deployment DEPLOYMENT_NAME --replicas=0 -n NAMESPACE
```

### Delete Completed/Failed Pods
```bash
# Clean up completed pods that might be causing issues
kubectl delete pods --field-selector=status.phase=Succeeded --all-namespaces
kubectl delete pods --field-selector=status.phase=Failed --all-namespaces
```

## 7. Prevention for Future Upgrades

```bash
# Set better surge settings for the node pool
gcloud container node-pools update YOUR_NODE_POOL \
  --cluster=YOUR_CLUSTER \
  --region=us-east1 \
  --max-surge-upgrade=3 \
  --max-unavailable-upgrade=1
```

## 8. Monitor Progress

```bash
# Watch the upgrade progress
watch kubectl get nodes
watch gcloud container operations list --region=us-east1
```

Start with checking the operation details and PDBs - these are usually the culprits. If you need immediate relief and it's safe for your workload, temporarily relaxing PDBs or scaling down problematic single-replica deployments often unblocks the upgrade.

Would you like me to help you investigate any specific errors you're seeing in the operation details?