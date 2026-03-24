This is a common GKE upgrade issue. Let's diagnose and resolve it step by step.

## 1. Check Current Upgrade Status

First, get detailed information about the stuck upgrade:

```bash
# Check cluster and node pool status
kubectl get nodes -o wide
gcloud container operations list --filter="operationType=UPGRADE_NODES" --limit=5

# Check specific node pool status
gcloud container node-pools describe [NODE_POOL_NAME] --cluster=[CLUSTER_NAME] --zone=us-east1
```

## 2. Identify Why Pods Aren't Draining

The most common causes are PodDisruptionBudgets (PDBs) and pods that can't be evicted:

```bash
# Check for restrictive PDBs
kubectl get pdb --all-namespaces
kubectl describe pdb --all-namespaces

# Check for pods that might be blocking drainage
kubectl get pods --all-namespaces --field-selector=spec.nodeName=[STUCK_NODE_NAME]

# Look for pods without proper controllers (bare pods)
kubectl get pods --all-namespaces -o wide | grep -v "Completed\|Running.*1/1"
```

## 3. Common Issues and Fixes

### Fix PodDisruptionBudgets
If PDBs are too restrictive (minAvailable too high or maxUnavailable too low):

```bash
# Temporarily relax or delete problematic PDBs
kubectl patch pdb [PDB_NAME] -n [NAMESPACE] --type merge -p '{"spec":{"minAvailable":1}}'

# Or delete temporarily (recreate after upgrade)
kubectl delete pdb [PDB_NAME] -n [NAMESPACE]
```

### Handle Stuck Pods
```bash
# Force delete stuck pods (use cautiously)
kubectl delete pod [POD_NAME] -n [NAMESPACE] --force --grace-period=0

# Check for local storage that might prevent drainage
kubectl describe pod [POD_NAME] -n [NAMESPACE] | grep -i volume
```

## 4. Manual Node Cordoning and Draining

If needed, manually assist the process:

```bash
# Cordon nodes to prevent new pods
kubectl cordon [NODE_NAME]

# Drain nodes manually with appropriate flags
kubectl drain [NODE_NAME] \
  --ignore-daemonsets \
  --delete-emptydir-data \
  --force \
  --grace-period=300 \
  --timeout=600s
```

## 5. Check for Daemonsets Issues

Daemonsets can sometimes block drainage:

```bash
# List daemonsets
kubectl get ds --all-namespaces

# Check if any daemonsets have update strategies that might conflict
kubectl get ds --all-namespaces -o yaml | grep -A 5 updateStrategy
```

## 6. If All Else Fails - Recovery Options

### Option A: Resume/Retry the Upgrade
```bash
# Sometimes just waiting longer helps, or check if you can cancel and restart
gcloud container clusters upgrade [CLUSTER_NAME] --node-pool=[NODE_POOL_NAME] --cluster-version=1.32 --zone=us-east1
```

### Option B: Manual Node Replacement (Last Resort)
```bash
# Scale up the node pool temporarily
gcloud container clusters resize [CLUSTER_NAME] --node-pool=[NODE_POOL_NAME] --num-nodes=[CURRENT+3] --zone=us-east1

# After new nodes join, cordon and drain old nodes manually
# Then scale back down once upgrade completes
```

## 7. Prevention for Future Upgrades

```bash
# Set proper PDBs before upgrades
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  maxUnavailable: 1
  selector:
    matchLabels:
      app: my-app
EOF
```

## Immediate Action Plan:

1. **Check PDBs first** - this is the #1 cause
2. **Look for bare pods** (pods not managed by deployments/replicasets)
3. **Temporarily relax or delete restrictive PDBs**
4. **Manually drain stuck nodes if necessary**
5. **Monitor the upgrade progress**

The upgrade should resume once the blocking conditions are resolved. Let me know what you find with the PDB and pod checks!