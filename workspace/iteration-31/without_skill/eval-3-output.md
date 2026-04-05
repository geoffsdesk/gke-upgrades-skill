This is a common issue with GKE node pool upgrades. Here's a systematic approach to diagnose and fix the problem:

## 1. Check Current Upgrade Status

```bash
# Get detailed upgrade status
kubectl get nodes -o wide

# Check node pool status
gcloud container node-pools describe [NODE_POOL_NAME] \
  --cluster=[CLUSTER_NAME] --zone=us-east1

# Check for stuck pods
kubectl get pods --all-namespaces --field-selector=status.phase=Pending
```

## 2. Identify Pod Drainage Issues

The most common causes for stuck upgrades:

### Check for PodDisruptionBudgets (PDBs)
```bash
# List all PDBs
kubectl get pdb --all-namespaces

# Check PDB status
kubectl describe pdb --all-namespaces
```

**Fix**: Temporarily adjust overly restrictive PDBs:
```bash
# Example: Allow more disruptions temporarily
kubectl patch pdb [PDB_NAME] -n [NAMESPACE] --type merge -p '{"spec":{"minAvailable":0}}'
```

### Check for StatefulSets or single-replica deployments
```bash
# Find StatefulSets
kubectl get statefulsets --all-namespaces

# Find single-replica deployments
kubectl get deployments --all-namespaces -o jsonpath='{range .items[?(@.spec.replicas==1)]}{.metadata.namespace}{" "}{.metadata.name}{"\n"}{end}'
```

## 3. Force Pod Eviction

If pods are stuck, you may need to force eviction:

```bash
# Check which nodes are being drained
kubectl get nodes --show-labels | grep SchedulingDisabled

# Force delete stuck pods (use carefully!)
kubectl delete pod [POD_NAME] -n [NAMESPACE] --force --grace-period=0
```

## 4. Check for Node Conditions

```bash
# Check for node issues
kubectl describe nodes | grep -E "(Conditions|Taints)"

# Look for specific issues
kubectl get events --sort-by='.lastTimestamp' | grep -i "failed\|error"
```

## 5. GKE-Specific Fixes

### Option 1: Increase upgrade timeout
```bash
gcloud container operations list --filter="targetLink:clusters/[CLUSTER_NAME]"

# If operation is still running, you can wait or proceed with other fixes
```

### Option 2: Temporarily scale down problematic workloads
```bash
# Scale down deployments that might be blocking drainage
kubectl scale deployment [DEPLOYMENT_NAME] -n [NAMESPACE] --replicas=0
```

### Option 3: Cancel and retry upgrade
```bash
# Cancel current upgrade (if absolutely necessary)
gcloud container operations cancel [OPERATION_ID] --zone=us-east1

# Then retry with surge settings
gcloud container node-pools update [NODE_POOL_NAME] \
  --cluster=[CLUSTER_NAME] --zone=us-east1 \
  --max-surge=2 --max-unavailable=0
```

## 6. Immediate Actions to Try

1. **Check and fix PDBs** - This is the #1 cause
2. **Scale down non-critical single-replica apps temporarily**
3. **Force delete any truly stuck pods**
4. **Increase surge capacity if possible**

## 7. Prevention for Future Upgrades

```bash
# Use surge upgrade settings
gcloud container node-pools update [NODE_POOL_NAME] \
  --cluster=[CLUSTER_NAME] --zone=us-east1 \
  --max-surge=3 --max-unavailable=0 \
  --node-version=1.32

# Set appropriate PDBs
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: app-pdb
spec:
  minAvailable: 50%  # Instead of absolute numbers
  selector:
    matchLabels:
      app: your-app
```

Start with checking PDBs and stuck pods - that resolves 80% of these issues. Let me know what you find and I can provide more specific guidance!