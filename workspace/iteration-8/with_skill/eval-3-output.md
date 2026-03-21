I'll walk you through diagnosing and fixing your stuck node pool upgrade. Since pods aren't draining, this is likely a PDB or resource constraint issue.

## Immediate Diagnosis

Run these commands in order to identify the root cause:

### 1. Check PDBs (most common cause)
```bash
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# For any PDB showing 0 allowed disruptions:
kubectl describe pdb PDB_NAME -n NAMESPACE
```

### 2. Check pending pods (resource constraints)
```bash
kubectl get pods -A | grep Pending
kubectl get events -A --field-selector reason=FailedScheduling --sort-by='.lastTimestamp' | tail -10
```

### 3. Check bare pods (can't reschedule)
```bash
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

### 4. Check current surge settings
```bash
gcloud container node-pools describe NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1-* \
  --format="value(upgradeSettings.maxSurge,upgradeSettings.maxUnavailable)"
```

## Most Likely Fixes

### Fix 1: PDB is too restrictive
If you found PDBs with 0 allowed disruptions, temporarily relax them:

```bash
# Back up the current PDB first
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup.yaml

# Allow disruptions temporarily
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'

# Or if it's blocking everything:
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"100%"}}'
```

### Fix 2: Increase surge capacity (if pods are pending)
```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1-* \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

### Fix 3: Delete bare pods (they won't reschedule anyway)
```bash
# For each bare pod found:
kubectl delete pod POD_NAME -n NAMESPACE --grace-period=30
```

## Monitor Progress

After applying fixes, monitor the upgrade:

```bash
# Watch nodes upgrade
watch 'kubectl get nodes -o wide | grep -E "Ready|NotReady"'

# Check operation status
gcloud container operations list --cluster CLUSTER_NAME --zone us-east1-* --filter="operationType=UPGRADE_NODES" --limit=1

# Monitor pod movements
kubectl get pods -A | grep -E "Terminating|Pending|ContainerCreating"
```

## Restore After Upgrade

Once the upgrade completes:

```bash
# Restore original PDB settings
kubectl apply -f pdb-backup.yaml

# Verify all nodes at target version
kubectl get nodes -o wide
gcloud container node-pools list --cluster CLUSTER_NAME --zone us-east1-*
```

## If Still Stuck

If the upgrade remains stuck after trying these fixes:

1. **Check for admission webhooks** blocking pod creation:
   ```bash
   kubectl get validatingwebhookconfigurations
   kubectl get events -A --field-selector reason=FailedCreate
   ```

2. **Contact GKE Support** if the operation shows no progress for another hour. Include:
   - Cluster name and zone
   - Operation ID from `gcloud container operations list`
   - Output from the diagnostic commands above

Start with checking PDBs first - that's the most common cause of stuck drains. Let me know what you find and I can provide more specific guidance!