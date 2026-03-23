This is a common GKE upgrade issue. Let me help you diagnose and fix the stuck node pool upgrade.

## Immediate Diagnostics

First, check what's blocking the pod drainage:

```bash
# Check node status and conditions
kubectl get nodes -o wide

# Look for pods that can't be evicted
kubectl get pods --all-namespaces --field-selector=status.phase!=Running

# Check for PodDisruptionBudgets that might be blocking drainage
kubectl get pdb --all-namespaces

# Check events for eviction errors
kubectl get events --all-namespaces --sort-by='.lastTimestamp' | grep -i evict
```

## Common Causes & Fixes

### 1. **PodDisruptionBudgets (PDBs) Too Restrictive**
```bash
# Find problematic PDBs
kubectl get pdb --all-namespaces -o wide

# Temporarily relax overly restrictive PDBs
kubectl patch pdb <pdb-name> -n <namespace> --type='merge' -p='{"spec":{"minAvailable":1}}'
```

### 2. **Pods with Local Storage or No Controller**
```bash
# Find pods without controllers (won't be recreated)
kubectl get pods --all-namespaces -o json | jq -r '.items[] | select(.metadata.ownerReferences == null) | "\(.metadata.namespace)/\(.metadata.name)"'

# Check for pods using local storage
kubectl get pods --all-namespaces -o json | jq -r '.items[] | select(.spec.volumes[]?.hostPath or .spec.volumes[]?.emptyDir) | "\(.metadata.namespace)/\(.metadata.name)"'
```

### 3. **Force Upgrade if Safe**
If pods are stuck and it's safe to proceed:

```bash
# Get your node pool name
gcloud container node-pools list --cluster=<cluster-name> --zone=us-east1

# Cancel and restart the upgrade with force flag
gcloud container clusters upgrade <cluster-name> \
    --node-pool=<node-pool-name> \
    --cluster-version=1.32 \
    --zone=us-east1 \
    --force
```

### 4. **Check Resource Constraints**
```bash
# Verify remaining nodes can handle the workload
kubectl describe nodes | grep -A 5 "Allocated resources"

# Check if new pods can be scheduled
kubectl get pods --all-namespaces | grep Pending
```

## Step-by-Step Resolution

1. **Identify blocking pods:**
```bash
kubectl get pods --all-namespaces --field-selector=status.phase=Running -o wide | grep <stuck-node-name>
```

2. **For each blocking pod, check:**
   - Does it have a PDB preventing eviction?
   - Is it managed by a controller (Deployment, StatefulSet, etc.)?
   - Does it use local storage that would be lost?

3. **Safe resolution options:**
```bash
# Option A: Manually delete blocking pods (if recreatable)
kubectl delete pod <pod-name> -n <namespace> --grace-period=30

# Option B: Temporarily scale down problematic deployments
kubectl scale deployment <deployment-name> --replicas=0 -n <namespace>

# Option C: Adjust PDB temporarily
kubectl patch pdb <pdb-name> -n <namespace> --type='merge' -p='{"spec":{"minAvailable":0}}'
```

4. **Monitor progress:**
```bash
# Watch the upgrade status
gcloud container operations list --filter="targetLink:node-pools/<node-pool-name>"

# Watch node status
watch kubectl get nodes
```

## Prevention for Future Upgrades

```bash
# Set proper PDBs before upgrades
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  minAvailable: 50%  # Allow some disruption
  selector:
    matchLabels:
      app: my-app
```

## Emergency Recovery

If the upgrade is completely stuck:

```bash
# Check operation status
gcloud container operations describe <operation-id> --zone=us-east1

# As last resort, you might need to:
# 1. Cordon the stuck nodes
kubectl cordon <node-name>

# 2. Manually drain with force
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data --force

# 3. Then let GKE continue the upgrade
```

**What's most likely happening:** Check your PDBs first - they're the most common cause of stuck upgrades. Also verify you have enough capacity on the upgraded nodes to handle the workload from nodes being drained.

Would you like me to help you investigate any specific aspect of these diagnostics?