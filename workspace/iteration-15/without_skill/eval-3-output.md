This is a common GKE upgrade issue. Let's diagnose and fix the stuck node pool upgrade systematically:

## Immediate Diagnostics

First, check the upgrade status and any error messages:

```bash
# Check upgrade status
gcloud container operations list --filter="operationType=UPGRADE_NODES" --limit=5

# Get detailed operation info
gcloud container operations describe OPERATION_ID --zone=us-east1

# Check node pool status
kubectl get nodes -o wide
kubectl describe nodes | grep -A 5 -B 5 "SchedulingDisabled\|cordoned"
```

## Common Causes & Solutions

### 1. **PodDisruptionBudgets (PDBs) Blocking Drainage**

This is the most common cause:

```bash
# Check PDBs
kubectl get pdb --all-namespaces
kubectl describe pdb --all-namespaces

# Look for PDBs with 0 allowed disruptions
kubectl get pdb --all-namespaces -o custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name,MIN-AVAILABLE:.spec.minAvailable,MAX-UNAVAILABLE:.spec.maxUnavailable,ALLOWED-DISRUPTIONS:.status.disruptionsAllowed
```

**Fix:** Temporarily adjust restrictive PDBs:
```bash
# Edit problematic PDBs
kubectl patch pdb PDB_NAME -n NAMESPACE --type merge -p '{"spec":{"maxUnavailable":"50%"}}'
```

### 2. **Pods with No Controllers (Naked Pods)**

```bash
# Find naked pods
kubectl get pods --all-namespaces --field-selector spec.nodeName=NODE_NAME -o json | jq '.items[] | select(.metadata.ownerReferences == null) | {name: .metadata.name, namespace: .metadata.namespace, node: .spec.nodeName}'
```

**Fix:** These must be manually deleted:
```bash
kubectl delete pod POD_NAME -n NAMESPACE --force --grace-period=0
```

### 3. **DaemonSets or System Pods**

```bash
# Check for problematic DaemonSets
kubectl get ds --all-namespaces
kubectl get pods --all-namespaces --field-selector spec.nodeName=NODE_NAME | grep -E "(DaemonSet|kube-system)"
```

### 4. **Pods with Long Termination Grace Periods**

```bash
# Check termination grace periods
kubectl get pods --all-namespaces -o custom-columns=NAME:.metadata.name,NAMESPACE:.metadata.namespace,GRACE:.spec.terminationGracePeriodSeconds,NODE:.spec.nodeName | grep NODE_NAME
```

## Quick Resolution Steps

### Option 1: Force Complete the Upgrade
```bash
# If safe to do so, force delete stuck pods
kubectl get pods --all-namespaces --field-selector spec.nodeName=STUCK_NODE_NAME
kubectl delete pod POD_NAME -n NAMESPACE --force --grace-period=0

# Or drain the node manually
kubectl drain STUCK_NODE_NAME --ignore-daemonsets --delete-emptydir-data --force --grace-period=0
```

### Option 2: Temporarily Relax Constraints
```bash
# Scale down problematic deployments temporarily
kubectl scale deployment DEPLOYMENT_NAME --replicas=0 -n NAMESPACE

# Or increase maxUnavailable on PDBs
kubectl patch pdb PDB_NAME -n NAMESPACE --type merge -p '{"spec":{"maxUnavailable":"100%"}}'
```

### Option 3: Cancel and Restart (Last Resort)
```bash
# Cancel the current operation (if supported)
gcloud container operations cancel OPERATION_ID --zone=us-east1

# Then restart with different strategy
gcloud container clusters upgrade CLUSTER_NAME --node-pool=POOL_NAME --cluster-version=1.32 --zone=us-east1 --max-surge-upgrade=2 --max-unavailable-upgrade=1
```

## Monitor Progress

```bash
# Watch the upgrade progress
watch 'kubectl get nodes -o wide && echo "=== Upgrade Status ===" && gcloud container operations list --limit=3'

# Check events for issues
kubectl get events --sort-by='.lastTimestamp' | tail -20
```

## Prevention for Future Upgrades

1. **Audit PDBs before upgrades:**
   ```bash
   kubectl get pdb --all-namespaces -o custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name,ALLOWED-DISRUPTIONS:.status.disruptionsAllowed | grep " 0"
   ```

2. **Use surge upgrades:** `--max-surge-upgrade=1 --max-unavailable-upgrade=0`

3. **Upgrade during maintenance windows** when you can temporarily relax PDB constraints

**Most likely culprit:** Check your PDBs first - they're responsible for 80% of stuck upgrades. Look for any with `disruptionsAllowed: 0`.

Would you like me to help you investigate any specific error messages you're seeing?