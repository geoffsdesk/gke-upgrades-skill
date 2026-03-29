This is a common GKE upgrade issue. Here's a systematic approach to diagnose and fix the stuck node pool upgrade:

## 1. Check Current Upgrade Status

```bash
# Get detailed upgrade status
kubectl get nodes -o wide
gcloud container operations list --filter="operationType=UPGRADE_NODES"

# Check for stuck operations
gcloud container operations describe [OPERATION_ID] --zone=us-east1
```

## 2. Identify Pod Drainage Issues

The most common cause is pods that can't be evicted. Check for:

```bash
# Look for pods with issues
kubectl get pods --all-namespaces --field-selector=status.phase!=Running,status.phase!=Succeeded

# Check for PodDisruptionBudgets that might be blocking drainage
kubectl get pdb --all-namespaces

# Look for pods without proper disruption budgets
kubectl get pods --all-namespaces -o wide | grep -E "old-node-names"
```

## 3. Common Blocking Issues

**PodDisruptionBudgets (PDBs):**
```bash
# Check if PDBs are too restrictive
kubectl get pdb --all-namespaces -o yaml

# Temporarily relax PDBs if safe:
kubectl patch pdb [PDB_NAME] -n [NAMESPACE] --type merge -p '{"spec":{"minAvailable":0}}'
```

**DaemonSets or StatefulSets:**
```bash
# Check for problematic workloads
kubectl get ds --all-namespaces
kubectl get sts --all-namespaces
```

**Local storage or hostPath volumes:**
```bash
# Look for pods with local storage
kubectl get pods --all-namespaces -o yaml | grep -A 5 -B 5 "hostPath\|local"
```

## 4. Force Resolution Options

**Option A: Manual Pod Eviction**
```bash
# Identify nodes being upgraded
kubectl get nodes | grep SchedulingDisabled

# Force delete stuck pods (use carefully)
kubectl delete pod [POD_NAME] -n [NAMESPACE] --force --grace-period=0
```

**Option B: Temporarily Adjust PDBs**
```bash
# For each problematic PDB:
kubectl patch pdb [PDB_NAME] -n [NAMESPACE] --type merge -p '{"spec":{"minAvailable":1}}'
```

**Option C: Cancel and Retry Upgrade**
```bash
# Cancel current upgrade
gcloud container operations cancel [OPERATION_ID] --zone=us-east1

# Start upgrade with surge settings
gcloud container node-pools update [NODE_POOL_NAME] \
    --cluster=[CLUSTER_NAME] \
    --zone=us-east1 \
    --max-surge=2 \
    --max-unavailable=1
```

## 5. Prevention for Future Upgrades

**Configure surge settings before upgrading:**
```bash
gcloud container node-pools update [NODE_POOL_NAME] \
    --cluster=[CLUSTER_NAME] \
    --zone=us-east1 \
    --max-surge=3 \
    --max-unavailable=1
```

**Review PDBs beforehand:**
```bash
# Ensure PDBs allow for at least 1 pod disruption
kubectl get pdb --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{" "}{.metadata.name}{" "}{.spec.minAvailable}{" "}{.spec.maxUnavailable}{"\n"}{end}'
```

## 6. If Still Stuck

**Check GKE-specific issues:**
```bash
# Look for node conditions
kubectl describe nodes | grep -A 10 Conditions

# Check cluster events
kubectl get events --sort-by='.lastTimestamp' | tail -20
```

**Contact support preparation:**
```bash
# Gather diagnostics
kubectl get events --all-namespaces --sort-by='.lastTimestamp' > events.log
kubectl get pods --all-namespaces -o wide > pods.log
gcloud container operations list > operations.log
```

## Quick Fix Priority:

1. **Check PDBs first** - this causes 80% of stuck upgrades
2. **Look for DaemonSets with issues**
3. **Check for pods with local storage**
4. **Consider temporary PDB relaxation**
5. **Use manual eviction as last resort**

What specific error messages are you seeing in the pod events or operation description?