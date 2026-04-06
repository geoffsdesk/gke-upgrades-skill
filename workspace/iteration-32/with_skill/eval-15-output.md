You're in a **mixed-version state** - some nodes at 1.32, others at the old version. This is **valid and functional** - GKE allows nodes within 2 minor versions of the control plane, and your workloads will continue running normally on whichever nodes they're scheduled to.

## Immediate Status Check

First, let's see exactly what happened:

```bash
# Check current node versions
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool

# Check for any stuck operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES"

# Look for error messages in the latest operation
gcloud container operations describe OPERATION_ID --zone ZONE
```

## Recommended Approach: Fix and Retry

**Option A** is usually best - fix the root cause and resume the upgrade:

### 1. Diagnose the failure cause
Most common causes in order:

```bash
# Check for PDB blocking drain (most likely)
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# Check for resource constraints
kubectl get pods -A | grep Pending
kubectl get events -A --field-selector reason=FailedScheduling

# Check for bare pods that can't reschedule
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

### 2. Apply the fix
For PDB issues (most common):
```bash
# Temporarily relax the blocking PDB
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

For resource constraints:
```bash
# Reduce surge to fit within quota
gcloud container node-pools update MAIN_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### 3. Resume the upgrade
```bash
gcloud container node-pools upgrade MAIN_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

### 4. Monitor progress
```bash
watch 'kubectl get nodes -o wide | grep MAIN_POOL_NAME'
```

## Alternative: Rollback (only if retry isn't viable)

If the root cause can't be fixed or the target version has critical issues:

### Create new pool at old version
```bash
gcloud container node-pools create MAIN_POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version OLD_VERSION \
  --num-nodes 20 \
  --machine-type MACHINE_TYPE
```

### Migrate workloads
```bash
# Cordon the mixed-version pool
kubectl cordon -l cloud.google.com/gke-nodepool=MAIN_POOL_NAME

# Drain workloads to the new pool
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data
```

**Note:** Rollback is more complex and slower than fixing and retrying.

## Next Steps for Other Pools

Once your main pool is resolved:
- **Wait** before upgrading the other two pools - validate the main pool is stable
- Apply the same fixes (PDB relaxation, surge settings) to prevent the same issue
- Consider upgrading them sequentially rather than simultaneously

## Key Points
- **No urgency** - mixed-version state is safe and supported
- **Services remain available** - workloads run normally during mixed state  
- **Retry is usually simpler** than rollback
- **Fix the root cause** to prevent the same issue on other pools

What error message are you seeing in the failed operation? That will help pinpoint the exact fix needed.