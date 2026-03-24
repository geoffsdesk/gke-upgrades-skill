Let me help you diagnose this stuck node pool upgrade. Since pods aren't draining from the remaining nodes, we need to work through the most common causes systematically.

## Immediate Diagnosis Steps

Run these commands to identify what's blocking the drain:

### 1. Check PDBs (most likely culprit)
```bash
kubectl get pdb -A -o wide
# Look for PDBs with ALLOWED DISRUPTIONS = 0

# For any restrictive PDBs, get details:
kubectl describe pdb PDB_NAME -n NAMESPACE
```

### 2. Check for bare pods
```bash
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

### 3. Check resource constraints
```bash
kubectl get pods -A | grep Pending
kubectl get events -A --field-selector reason=FailedScheduling | tail -10
kubectl top nodes
```

### 4. Check admission webhooks
```bash
kubectl get validatingwebhookconfigurations
kubectl get events -A --field-selector reason=FailedCreate | tail -10
```

### 5. Check current upgrade operation status
```bash
gcloud container operations list --cluster CLUSTER_NAME --zone us-east1 --filter="operationType=UPGRADE_NODES" --limit=1
```

## Most Likely Fixes

Based on your symptoms, here are the fixes in order of probability:

### Fix 1: Temporarily relax restrictive PDBs
If you found PDBs with 0 allowed disruptions:
```bash
# Back up the original PDB
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup.yaml

# Temporarily allow more disruptions
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'

# Or if it's really stuck, allow all disruptions temporarily:
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"100%"}}'
```

### Fix 2: Delete bare pods
If you found bare pods (they won't reschedule anyway):
```bash
kubectl delete pod POD_NAME -n NAMESPACE --grace-period=0 --force
```

### Fix 3: Reduce surge settings if resource-constrained
```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1 \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### Fix 4: Temporarily disable problematic webhooks
If webhooks are rejecting pod creation:
```bash
kubectl patch validatingwebhookconfigurations WEBHOOK_NAME \
  -p '{"webhooks":[{"name":"WEBHOOK","failurePolicy":"Ignore"}]}'
```

## Monitor Progress

After applying fixes, monitor the upgrade:
```bash
# Watch node upgrade progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check for stuck pods
kubectl get pods -A | grep -E "Terminating|Pending|ContainerCreating"

# Verify upgrade operation is progressing
gcloud container operations describe OPERATION_ID --zone us-east1
```

## If Still Stuck After 30 Minutes

If the upgrade doesn't resume after applying these fixes:

1. **Check GKE disruption event notifications** in Cloud Logging:
   ```bash
   gcloud logging read 'resource.type="gke_cluster" jsonPayload.reason=~"(POD_PDB_VIOLATION|POD_NOT_ENOUGH_PDB|EvictionBlocked)"' --limit=20
   ```

2. **Consider canceling and retrying** (only if fixes don't work):
   ```bash
   # This will complete currently draining nodes but stop further upgrades
   gcloud container operations cancel OPERATION_ID --zone us-east1
   
   # Then retry with adjusted settings
   gcloud container node-pools upgrade NODE_POOL_NAME \
     --cluster CLUSTER_NAME \
     --zone us-east1 \
     --cluster-version 1.32
   ```

## Post-Fix Cleanup

Once the upgrade completes successfully:
```bash
# Restore original PDBs
kubectl apply -f pdb-backup.yaml

# Re-enable webhooks if disabled
kubectl patch validatingwebhookconfigurations WEBHOOK_NAME \
  -p '{"webhooks":[{"name":"WEBHOOK","failurePolicy":"Fail"}]}'

# Verify all nodes at target version
kubectl get nodes -o wide
```

**Start with checking PDBs first** — that's the most common cause of drain failures. Let me know what you find and I can provide more specific guidance based on your cluster's configuration.