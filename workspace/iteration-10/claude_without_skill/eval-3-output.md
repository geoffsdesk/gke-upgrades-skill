This is a common issue with GKE node pool upgrades. Here's a systematic approach to diagnose and fix the stuck upgrade:

## 1. **Check Upgrade Status and Logs**

```bash
# Check current upgrade status
gcloud container operations list --filter="zone:us-east1"

# Get detailed operation info
gcloud container operations describe [OPERATION_ID] --zone=us-east1

# Check node pool status
kubectl get nodes -o wide
kubectl describe nodepool [NODE_POOL_NAME]
```

## 2. **Identify Pod Drainage Issues**

The most common cause is pods that can't be evicted:

```bash
# Check for pods that are blocking drainage
kubectl get pods --all-namespaces --field-selector=status.phase!=Succeeded,status.phase!=Failed

# Look for pods with disruption issues
kubectl get pdb --all-namespaces

# Check for pods stuck in terminating state
kubectl get pods --all-namespaces | grep Terminating
```

## 3. **Common Blocking Issues to Check**

**PodDisruptionBudgets (PDBs):**
```bash
# List all PDBs
kubectl get pdb --all-namespaces -o wide

# Check if PDBs are too restrictive
kubectl describe pdb [PDB_NAME] -n [NAMESPACE]
```

**DaemonSets:**
```bash
# Check for DaemonSets that might be preventing drainage
kubectl get daemonsets --all-namespaces
```

**StatefulSets with persistent storage:**
```bash
kubectl get statefulsets --all-namespaces
kubectl get pvc --all-namespaces
```

## 4. **Immediate Fixes**

**Option A: Temporarily relax PDBs**
```bash
# Edit restrictive PDBs temporarily
kubectl patch pdb [PDB_NAME] -n [NAMESPACE] --type merge -p '{"spec":{"minAvailable":0}}'

# Or increase maxUnavailable
kubectl patch pdb [PDB_NAME] -n [NAMESPACE] --type merge -p '{"spec":{"maxUnavailable":"50%"}}'
```

**Option B: Force delete stuck pods**
```bash
# Identify stuck pods on nodes being upgraded
kubectl get pods --all-namespaces -o wide | grep [NODE_NAME]

# Force delete if necessary (last resort)
kubectl delete pod [POD_NAME] -n [NAMESPACE] --grace-period=0 --force
```

**Option C: Manually cordon and drain problematic nodes**
```bash
# Cordon the node
kubectl cordon [NODE_NAME]

# Drain with more aggressive settings
kubectl drain [NODE_NAME] --ignore-daemonsets --delete-emptydir-data --force --grace-period=0
```

## 5. **Resume or Restart the Upgrade**

If the upgrade is completely stuck:

```bash
# Cancel current upgrade (if needed)
gcloud container clusters upgrade [CLUSTER_NAME] --zone=us-east1 --cancel

# Restart the upgrade with different strategy
gcloud container node-pools upgrade [NODE_POOL_NAME] \
  --cluster=[CLUSTER_NAME] \
  --zone=us-east1 \
  --max-surge=2 \
  --max-unavailable=1
```

## 6. **Prevention for Future Upgrades**

```bash
# Use surge upgrade strategy
gcloud container node-pools update [NODE_POOL_NAME] \
  --cluster=[CLUSTER_NAME] \
  --zone=us-east1 \
  --max-surge=3 \
  --max-unavailable=0

# Review and adjust PDBs before upgrades
kubectl get pdb --all-namespaces -o yaml > pdb-backup.yaml
```

## 7. **Monitor Progress**

```bash
# Watch the upgrade progress
watch -n 30 'kubectl get nodes'

# Monitor pod movements
kubectl get events --sort-by='.lastTimestamp' | grep -i drain
```

## Quick Emergency Actions:

1. **Check for restrictive PDBs** - This is the #1 cause
2. **Look for pods with local storage** that can't be moved
3. **Identify any stuck Terminating pods** and force delete them
4. **Temporarily increase surge settings** to speed up the process

Start with checking PDBs and stuck pods - these resolve 80% of stuck upgrade issues. Let me know what you find and I can provide more specific guidance!