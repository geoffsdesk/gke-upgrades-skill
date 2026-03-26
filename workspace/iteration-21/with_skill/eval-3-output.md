I'll help you diagnose and fix this stuck node pool upgrade. Let's work through the most common causes systematically.

## Immediate Diagnosis Steps

Run these commands to identify what's blocking the drain:

### 1. Check for PDB violations (most likely cause)
```bash
# Look for PDBs with 0 allowed disruptions
kubectl get pdb -A -o wide

# Check for specific PDB blocking events
kubectl get events -A --field-selector reason=EvictionBlocked --sort-by='.lastTimestamp'
```

### 2. Check for pending pods that can't reschedule
```bash
# Find pending pods
kubectl get pods -A | grep Pending

# Check scheduling failures
kubectl get events -A --field-selector reason=FailedScheduling --sort-by='.lastTimestamp'
```

### 3. Check for bare pods (won't reschedule)
```bash
# Find pods without owner references
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

### 4. Check current node status
```bash
# See which nodes are being drained
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool

# Check for pods stuck in terminating
kubectl get pods -A | grep Terminating
```

## Most Likely Fixes

### Fix #1: PDB Too Restrictive
If you find PDBs with 0 allowed disruptions:

```bash
# Temporarily relax the problematic PDB
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'

# Or if it's critical, allow at least 1 disruption
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"minAvailable":"2"}}'  # assuming 3+ replicas
```

### Fix #2: Resource Constraints
If pods are pending due to insufficient resources:

```bash
# Reduce surge to 1 node at a time (slower but needs less quota)
gcloud container node-pools update YOUR_NODE_POOL \
  --cluster YOUR_CLUSTER \
  --zone us-east1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

Or temporarily scale down non-critical workloads:
```bash
kubectl scale deployment NON_CRITICAL_APP --replicas=0 -n NAMESPACE
```

### Fix #3: Delete Bare Pods
If you found bare pods (they won't reschedule anyway):
```bash
kubectl delete pod POD_NAME -n NAMESPACE --grace-period=0 --force
```

### Fix #4: Long Termination Grace Periods
Check for pods with excessive termination periods:
```bash
kubectl get pods -A -o json | \
  jq '.items[] | select(.spec.terminationGracePeriodSeconds > 300) | {ns:.metadata.namespace, name:.metadata.name, grace:.spec.terminationGracePeriodSeconds}'
```

If found, consider reducing the grace period in the workload spec.

## Monitor Progress

After applying fixes, monitor the upgrade:

```bash
# Watch node upgrade progress
watch 'kubectl get nodes -o wide'

# Check for remaining stuck pods
kubectl get pods -A | grep -E "Terminating|Pending"

# Verify upgrade operation is progressing
gcloud container operations list --cluster YOUR_CLUSTER --zone us-east1-b --limit=1
```

## If Still Stuck After 30 Minutes

1. **Check admission webhooks** that might be rejecting pod recreation:
```bash
kubectl get validatingwebhookconfigurations
kubectl get events -A --field-selector reason=FailedCreate
```

2. **Force complete problematic pods**:
```bash
kubectl delete pod STUCK_POD -n NAMESPACE --grace-period=0 --force
```

3. **Contact GKE Support** if the operation shows no progress after resolving pod-level issues. Provide:
   - Cluster name and zone
   - Operation ID from `gcloud container operations list`
   - Timeline of when it got stuck

## Prevention for Next Time

After this upgrade completes:

1. **Review PDB settings** - ensure they allow at least 1 disruption
2. **Set appropriate surge settings** based on your quota:
   - Small pools (≤20 nodes): `maxSurge=1`
   - Larger pools: `maxSurge=5%` of pool size
3. **Schedule upgrades during off-peak hours** when resource usage is lower

Let me know what you find with the diagnostic commands and I can provide more specific guidance!