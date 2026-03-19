This is a common GKE upgrade issue. Let's diagnose and fix it step by step:

## 1. Check Pod Disruption Issues

First, identify what's preventing pod drainage:

```bash
# Check pods that can't be evicted
kubectl get pods --all-namespaces --field-selector=status.phase!=Succeeded,status.phase!=Failed

# Look for pods with disruption issues
kubectl get pdb --all-namespaces

# Check for pods stuck in terminating state
kubectl get pods --all-namespaces | grep Terminating
```

## 2. Common Blocking Issues

**PodDisruptionBudgets (PDBs):**
```bash
# List all PDBs
kubectl get pdb --all-namespaces -o wide

# Check if PDBs are too restrictive (minAvailable too high)
kubectl describe pdb <pdb-name> -n <namespace>
```

**DaemonSets or StatefulSets:**
```bash
# Check DaemonSets (these can block drainage)
kubectl get ds --all-namespaces

# Check StatefulSets
kubectl get sts --all-namespaces
```

## 3. Immediate Fixes

**Option A: Temporarily relax PDBs**
```bash
# Edit restrictive PDBs
kubectl patch pdb <pdb-name> -n <namespace> -p '{"spec":{"minAvailable":1}}'

# Or temporarily delete them (they'll be recreated)
kubectl delete pdb <problematic-pdb> -n <namespace>
```

**Option B: Force drain stuck nodes**
```bash
# Identify nodes being upgraded
kubectl get nodes -l cloud.google.com/gke-nodepool=<your-nodepool-name>

# Manually drain a stuck node (use with caution)
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data --force --grace-period=30
```

**Option C: Delete stuck terminating pods**
```bash
# Force delete pods stuck in terminating state
kubectl delete pod <pod-name> -n <namespace> --grace-period=0 --force
```

## 4. Check GKE-specific Issues

```bash
# Check upgrade status
gcloud container operations list --filter="operationType:UPGRADE_NODES"

# Get detailed operation info
gcloud container operations describe <operation-id> --zone=us-east1

# Check node pool status
gcloud container node-pools describe <nodepool-name> --cluster=<cluster-name> --zone=us-east1
```

## 5. If Still Stuck - Advanced Options

**Pause and resume upgrade:**
```bash
# This isn't directly available, but you can:
# 1. Let current nodes finish
# 2. Temporarily scale down problematic workloads
kubectl scale deployment <deployment-name> --replicas=0 -n <namespace>

# 3. Resume after pods clear
kubectl scale deployment <deployment-name> --replicas=<original-count> -n <namespace>
```

**Check for resource constraints:**
```bash
# Ensure remaining nodes have capacity for displaced pods
kubectl describe nodes
kubectl top nodes
```

## 6. Prevention for Future Upgrades

1. **Review PDBs before upgrading:**
   ```bash
   kubectl get pdb --all-namespaces -o custom-columns="NAMESPACE:.metadata.namespace,NAME:.metadata.name,MIN AVAILABLE:.spec.minAvailable,MAX UNAVAILABLE:.spec.maxUnavailable"
   ```

2. **Use surge upgrades:**
   ```bash
   gcloud container node-pools update <nodepool-name> \
     --cluster=<cluster-name> \
     --zone=us-east1 \
     --max-surge=2 \
     --max-unavailable=0
   ```

## Recommended Immediate Action:

1. Run the PDB check command above
2. Look for any PDBs with `minAvailable` set too high
3. Temporarily patch or delete restrictive PDBs
4. The upgrade should resume automatically within 5-10 minutes

Let me know what you find with the PDB check - that's the most common culprit for stuck upgrades!