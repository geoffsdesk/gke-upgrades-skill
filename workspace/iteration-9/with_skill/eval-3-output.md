# GKE Node Pool Upgrade - Troubleshooting Stuck Drain

Your upgrade is stuck because pods can't be evicted from the remaining 9 nodes. Let's diagnose the root cause systematically.

## Immediate Diagnosis Commands

Run these in order to identify what's blocking the drain:

### 1. Check for PDB blocking drain (most common cause)
```bash
kubectl get pdb -A -o wide
```
Look for any PDBs showing `ALLOWED DISRUPTIONS = 0`. If you see this:

```bash
# Get details on the blocking PDB
kubectl describe pdb PDB_NAME -n NAMESPACE
```

### 2. Check for stuck/pending pods
```bash
kubectl get pods -A | grep -E "Pending|Terminating"
kubectl get events -A --field-selector reason=FailedScheduling --sort-by='.lastTimestamp' | tail -10
```

### 3. Check for bare pods (no controllers)
```bash
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

### 4. Check current upgrade operation status
```bash
gcloud container operations list --cluster CLUSTER_NAME --zone us-east1-b --filter="operationType=UPGRADE_NODES" --limit=5
```

## Most Likely Fixes

### Fix 1: PDB Too Restrictive (80% of stuck upgrades)
If you found PDBs with 0 allowed disruptions, temporarily relax them:

```bash
# Backup the PDB first
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup-$(date +%Y%m%d).yaml

# Temporarily allow disruptions
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

### Fix 2: Delete Bare Pods
If you found bare pods, delete them (they won't reschedule anyway):

```bash
kubectl delete pod POD_NAME -n NAMESPACE --force --grace-period=0
```

### Fix 3: Increase Surge Capacity
If pods are pending due to resource constraints:

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1-b \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

This adds more new nodes before draining old ones.

## Monitor Progress

After applying fixes, monitor the upgrade:

```bash
# Watch node status
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check operation progress
gcloud container operations describe OPERATION_ID --zone us-east1-b
```

## If Still Stuck After 30 Minutes

1. **Collect operation ID:**
```bash
gcloud container operations list --cluster CLUSTER_NAME --zone us-east1-b --limit=1
```

2. **Check for admission webhooks blocking pod creation:**
```bash
kubectl get validatingwebhookconfigurations -o name
kubectl get mutatingwebhookconfigurations -o name
```

3. **If webhooks are present, temporarily disable problematic ones:**
```bash
# Check if any webhook is rejecting pod scheduling
kubectl describe validatingwebhookconfigurations WEBHOOK_NAME
```

## Emergency Workaround

If the upgrade remains completely stuck (no progress for 3+ hours after fixes):

```bash
# Cancel the current upgrade operation (this is safe)
# GKE will complete the current node being upgraded, then stop

# Then restart with different surge settings
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 1

gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1-b \
  --cluster-version 1.32
```

## Post-Fix Cleanup

Once the upgrade completes successfully:

1. **Restore original PDBs:**
```bash
kubectl apply -f pdb-backup-$(date +%Y%m%d).yaml
```

2. **Verify all nodes upgraded:**
```bash
gcloud container node-pools list --cluster CLUSTER_NAME --zone us-east1-b
kubectl get nodes -o wide
```

**Start with the PDB check first** - this resolves 80% of stuck node pool upgrades. The upgrade should resume within 10-15 minutes after fixing PDB issues.