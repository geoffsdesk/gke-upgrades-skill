I'll walk you through diagnosing and fixing this stuck node pool upgrade. Since pods aren't draining, let's check the most common causes systematically.

## Immediate Diagnosis

Run these commands to identify what's blocking the drain:

### 1. Check PDBs (most common cause)
```bash
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# For any PDBs with 0 allowed disruptions:
kubectl describe pdb PDB_NAME -n NAMESPACE
```

### 2. Check for pods that can't be rescheduled
```bash
# Pending pods (resource constraints)
kubectl get pods -A | grep Pending
kubectl get events -A --field-selector reason=FailedScheduling | tail -10

# Bare pods (won't reschedule)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

### 3. Check node and resource status
```bash
# Which nodes are being drained
kubectl get nodes -o wide | grep SchedulingDisabled

# Resource availability
kubectl top nodes
kubectl describe nodes | grep -A 5 "Allocated resources"
```

### 4. Check for admission webhook issues
```bash
kubectl get events -A --field-selector type=Warning | grep -i webhook
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations
```

## Quick Fixes by Root Cause

### If PDBs are blocking (most likely):
```bash
# Temporarily relax the restrictive PDB
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'

# Or if it's completely blocking:
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"100%"}}'
```

### If resource constraints (pods pending):
```bash
# Reduce surge parallelism to fit available quota
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region us-east1 \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Or use drain-first mode if no surge quota available
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region us-east1 \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

### If bare pods exist:
```bash
# Delete them (they won't reschedule anyway)
kubectl delete pod POD_NAME -n NAMESPACE
```

### If webhooks are rejecting pod creation:
```bash
# Temporarily disable problematic webhook
kubectl patch validatingwebhookconfigurations WEBHOOK_NAME \
  -p '{"webhooks":[{"name":"WEBHOOK_NAME","failurePolicy":"Ignore"}]}'
```

## Resume the Upgrade

After fixing the blocking issue:

```bash
# The upgrade should resume automatically within 5-10 minutes
# Monitor progress:
watch 'kubectl get nodes -o wide'

# Check GKE operation status:
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --region us-east1 \
  --filter="operationType=UPGRADE_NODES" \
  --limit=1
```

## If Still Stuck After 30 Minutes

If the upgrade doesn't resume after fixing pod-level issues:

```bash
# Get the operation ID and contact GKE support
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --region us-east1 \
  --filter="operationType=UPGRADE_NODES" \
  --format="value(name)"
```

## Post-Fix Cleanup

Once the upgrade completes successfully:

1. **Restore original PDBs** if you modified them:
```bash
# Restore from backup or reset to original values
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"minAvailable":"ORIGINAL_VALUE","maxUnavailable":null}}'
```

2. **Re-enable webhooks** if disabled:
```bash
kubectl patch validatingwebhookconfigurations WEBHOOK_NAME \
  -p '{"webhooks":[{"name":"WEBHOOK_NAME","failurePolicy":"Fail"}]}'
```

## Prevention for Future Upgrades

To avoid this in future upgrades:
- Review PDB settings before upgrades - ensure they allow at least 1 disruption
- Test upgrades in dev/staging first to catch webhook compatibility issues
- Consider using maintenance windows during off-peak hours when resource pressure is lower

Start with checking the PDBs - that's the cause in ~80% of stuck drain scenarios. Let me know what you find and I can help with the specific fix!