Based on your description, this is a classic node pool upgrade blockage. Let's diagnose systematically and get your upgrade moving.

## Immediate Diagnostic Steps

**1. Check for PDB blocking drain (most common cause):**
```bash
kubectl get pdb -A -o wide
```
Look for any PDBs showing `ALLOWED DISRUPTIONS = 0`. If you see any, run:
```bash
kubectl describe pdb PDB_NAME -n NAMESPACE
```

**2. Check for pods that can't be evicted:**
```bash
kubectl get pods -A | grep -E "Terminating|Pending"
kubectl get events -A --field-selector reason=Evicted --sort-by='.lastTimestamp' | tail -20
```

**3. Check for bare pods (won't reschedule):**
```bash
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

**4. Check resource constraints:**
```bash
kubectl get events -A --field-selector reason=FailedScheduling | tail -10
kubectl top nodes
```

## Most Likely Fixes

### If PDBs are blocking (90% of cases):

**Temporarily relax the restrictive PDB:**
```bash
# Back up the original first
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup.yaml

# Allow more disruptions temporarily
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

### If bare pods exist:

**Delete them (they won't reschedule anyway):**
```bash
kubectl delete pod POD_NAME -n NAMESPACE --grace-period=0 --force
```

### If resource constraints:

**Reduce surge pressure:**
```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

## Check Current Upgrade Status

```bash
# See which operation is running
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --zone us-east1-a \
  --filter="operationType=UPGRADE_NODES" \
  --limit=1

# Check node status
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool
```

## Monitor Progress After Fix

```bash
# Watch nodes upgrade
watch 'kubectl get nodes -o wide | grep -v "Ready.*1\.32"'

# Check for stuck pods
kubectl get pods -A | grep -E "Terminating|Pending|Evicted"
```

## If Still Stuck After 30 Minutes

The upgrade operation may need to be restarted:

```bash
# Cancel current operation (this is safe - already upgraded nodes stay upgraded)
gcloud container operations cancel OPERATION_ID \
  --zone us-east1-a

# Restart the upgrade
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1-a \
  --cluster-version 1.32
```

## Prevention for Next Time

After this completes, configure surge settings proactively:
```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1-a \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

**Start with step 1 (PDB check) - this resolves 90% of stuck drain situations.** Let me know what you find and I'll help you apply the specific fix!