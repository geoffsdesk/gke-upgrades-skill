Let me walk you through diagnosing this stuck node pool upgrade systematically. Since pods aren't draining from the remaining 9 nodes, this is typically a pod-level blockage.

## Immediate Diagnosis - Run These Commands

### 1. Check for PDB violations (most common cause)
```bash
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# Check for PDB violation events
kubectl get events -A --field-selector reason=EvictionBlocked --sort-by='.lastTimestamp' | tail -10
```

### 2. Check for stuck/pending pods
```bash
kubectl get pods -A | grep -E "Pending|Terminating"
kubectl get events -A --field-selector reason=FailedScheduling --sort-by='.lastTimestamp' | tail -10
```

### 3. Check for bare pods (won't reschedule)
```bash
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

### 4. Check current upgrade operation status
```bash
gcloud container operations list --cluster CLUSTER_NAME --zone us-east1 --filter="operationType=UPGRADE_NODES" --limit=1
```

## Most Likely Fixes

### Fix 1: PDB Too Restrictive (90% of stuck upgrades)
If `kubectl get pdb -A` shows `ALLOWED DISRUPTIONS = 0`:

```bash
# Temporarily relax the blocking PDB
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'

# Or backup and edit manually
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup.yaml
# Edit minAvailable to allow 1-2 disruptions, then apply
```

### Fix 2: Delete Bare Pods
If bare pods are found:
```bash
# These won't reschedule anyway - safe to delete
kubectl delete pod POD_NAME -n NAMESPACE
```

### Fix 3: Resource Constraints
If pods are Pending due to insufficient resources:
```bash
# Reduce maxSurge to 1 (slower but needs less quota)
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1 \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Or scale down non-critical workloads temporarily
kubectl scale deployment NON_CRITICAL_DEPLOYMENT --replicas=0
```

## Monitor Progress After Fix
```bash
# Watch nodes upgrade
watch 'kubectl get nodes -L cloud.google.com/gke-nodepool | grep -E "Ready|NotReady|1.31|1.32"'

# Check for remaining stuck pods
kubectl get pods -A | grep -E "Terminating|Pending" | wc -l
```

## If Still Stuck After 30 Minutes

1. **Check admission webhooks** that might be rejecting pod recreation:
```bash
kubectl get validatingwebhookconfigurations
kubectl get events -A --field-selector reason=FailedCreate
```

2. **Force complete the current batch** (last resort):
```bash
# Contact Google Cloud Support with:
# - Cluster name and zone
# - Operation ID from operations list
# - Output of the diagnostic commands above
```

## Prevention for Next Time

Once this upgrade completes, review your PDBs:
```bash
# Check all PDBs for being too restrictive
kubectl get pdb -A -o custom-columns=NAME:.metadata.name,NAMESPACE:.metadata.namespace,MIN-AVAILABLE:.spec.minAvailable,MAX-UNAVAILABLE:.spec.maxUnavailable
```

**Key insight:** GKE respects PDBs for up to 1 hour, then force-evicts. If your upgrade has been stuck for 2 hours, it's likely that pods are being recreated but immediately failing due to PDBs, resource constraints, or admission webhooks - creating a retry loop.

Start with the PDB check - that resolves 90% of stuck upgrades. Let me know what you find!