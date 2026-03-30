Let me walk you through diagnosing this stuck node pool upgrade systematically. A 2-hour stall with pods not draining typically indicates one of a few common issues.

## Immediate Diagnosis Steps

Run these commands in order to identify the root cause:

### 1. Check PodDisruptionBudgets (most common cause)
```bash
# Look for PDBs with ALLOWED DISRUPTIONS = 0
kubectl get pdb -A -o wide

# Get details on any restrictive PDBs
kubectl describe pdb PDB_NAME -n NAMESPACE
```
**What to look for:** PDBs showing 0 allowed disruptions are blocking drain.

### 2. Check for pods that can't be evicted
```bash
# Find pods stuck in Terminating state
kubectl get pods -A | grep Terminating

# Check for drain-blocking events
kubectl get events -A --field-selector reason=EvictionBlocked --sort-by='.lastTimestamp' | tail -20

# Look for PDB violation events specifically
kubectl get events -A --field-selector reason=FailedScheduling --sort-by='.lastTimestamp' | tail -10
```

### 3. Identify bare pods (can't be rescheduled)
```bash
# Find pods without controllers (won't reschedule)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

### 4. Check resource constraints
```bash
# See if pods are pending due to no room
kubectl get pods -A | grep Pending
kubectl describe nodes | grep -A 5 "Allocated resources"
```

## Most Likely Fixes

### If PDBs are blocking (90% of cases):

**Temporary fix - relax the restrictive PDB:**
```bash
# Back up the original PDB first
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup.yaml

# Temporarily allow more disruptions
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

**For database/stateful workloads:**
- Don't set maxUnavailable too high - you need to maintain quorum
- For 3-node databases: use `maxUnavailable: 1`  
- For larger clusters: use percentage like `maxUnavailable: "33%"`

### If bare pods are blocking:

```bash
# Delete bare pods (they won't reschedule anyway)
kubectl delete pod POD_NAME -n NAMESPACE --grace-period=0 --force
```

### If resource constraints are the issue:

```bash
# Reduce surge parallelism to fit available capacity
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

## Resume the Upgrade

After fixing the blocking issue, the upgrade should automatically resume. Monitor progress:

```bash
# Watch node upgrade progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -v Ready || echo "Checking..."'

# Monitor the upgrade operation
gcloud container operations list --cluster CLUSTER_NAME --zone us-east1-a --filter="operationType=UPGRADE_NODES"
```

## Preventive Measures

**Restore original PDB after upgrade completes:**
```bash
kubectl apply -f pdb-backup.yaml
```

**For future upgrades, review PDBs beforehand:**
```bash
# Check for overly restrictive PDBs
kubectl get pdb -A -o custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name,MIN_AVAILABLE:.spec.minAvailable,MAX_UNAVAILABLE:.spec.maxUnavailable
```

## If Still Stuck After 30 Minutes

If the upgrade doesn't resume after applying these fixes:

1. **Check the operation status:**
   ```bash
   gcloud container operations describe OPERATION_ID --zone us-east1-a
   ```

2. **Contact GKE Support** with:
   - Cluster name and zone
   - Operation ID from the operations list
   - Timeline of when it got stuck
   - What fixes you've already tried

The most common issue is overly restrictive PDBs on critical workloads. Start there, and you'll likely resolve it quickly. Let me know what you find with the PDB check!