You're in a mixed-version state (8 nodes at 1.32, 12 nodes at the previous version), which is **completely valid and functional**. Your cluster is running fine - workloads can run on either version within the 2-minor-version skew policy.

Here's your recovery plan:

## Immediate Assessment

First, let's diagnose why the upgrade stopped:

```bash
# Check the failed operation details
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES"

# Look at the most recent operation for error details
gcloud container operations describe OPERATION_ID --zone ZONE

# Check for common blocking issues
kubectl get pdb -A -o wide  # Look for ALLOWED DISRUPTIONS = 0
kubectl get pods -A | grep -E "Pending|Terminating"
kubectl get events -A --field-selector type=Warning | head -20
```

## Recovery Options

**Option A - Retry (Recommended)**
This is usually the best approach. Fix the root cause, then resume:

```bash
# Once you've fixed the blocking issue, retry the upgrade
gcloud container node-pools upgrade POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

**Option B - Rollback (Only if needed)**
If the target version has critical defects or the root cause can't be fixed:

```bash
# Create a new pool at the previous version
gcloud container node-pools create POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version PREVIOUS_VERSION \
  --num-nodes 20 \
  --machine-type MACHINE_TYPE

# Cordon the partially-upgraded pool and migrate workloads
kubectl cordon -l cloud.google.com/gke-nodepool=POOL_NAME
# Then drain and delete the mixed pool after workloads migrate
```

## Most Likely Root Causes & Fixes

**1. PDB blocking drain (most common)**
```bash
kubectl get pdb -A -o wide
# If ALLOWED DISRUPTIONS = 0, temporarily relax:
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

**2. Resource constraints**
```bash
kubectl get pods -A | grep Pending
# If pods can't reschedule, reduce surge:
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 1 --max-unavailable-upgrade 0
```

**3. Bare pods**
```bash
# Find pods without controllers (won't reschedule)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
# Delete them - they won't reschedule anyway
```

## Next Steps for Remaining Pools

After fixing the main pool, upgrade your other two pools:

```bash
# Upgrade remaining pools one at a time
gcloud container node-pools upgrade POOL_NAME_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

## Key Points

- **No urgency**: Mixed-version state is safe - your cluster works normally
- **Retry is simpler**: Fixing the root cause and retrying is usually faster than rollback
- **One pool at a time**: GKE upgrades node pools sequentially by default

What error message are you seeing in the operation details? That will help pinpoint the exact fix needed.