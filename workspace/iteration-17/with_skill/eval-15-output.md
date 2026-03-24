You're in a valid but mixed-version state - 8 nodes at 1.32, 12 nodes at the previous version. This is completely functional since GKE allows nodes within 2 minor versions of the control plane. Your workloads will continue running normally.

## Current State Assessment

First, let's diagnose why the upgrade stopped:

```bash
# Check the failed operation details
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES" --limit=5

# Look for specific error details
gcloud container operations describe OPERATION_ID --zone ZONE

# Check for common blocking issues
kubectl get pdb -A -o wide  # Look for ALLOWED DISRUPTIONS = 0
kubectl get pods -A | grep -E "Pending|Terminating"
kubectl get events -A --field-selector reason=FailedScheduling --sort-by='.lastTimestamp' | tail -10
```

## Recommended Approach: Retry (Most Common)

**Option A - Fix and Resume (Recommended)**

Most partial failures are due to fixable issues like restrictive PDBs or resource constraints:

```bash
# 1. Fix the root cause (examples):
# If PDB is blocking:
kubectl patch pdb PDB_NAME -n NAMESPACE -p '{"spec":{"maxUnavailable":"50%"}}'

# If resource constrained, reduce surge:
gcloud container node-pools update MAIN_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# 2. Resume the upgrade
gcloud container node-pools upgrade MAIN_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# 3. Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

## Alternative: Rollback (If Retry Won't Work)

**Option B - Create New Pool and Migrate (Complex)**

Only if the root cause can't be fixed or 1.32 has critical defects:

```bash
# 1. Create replacement pool at previous version
gcloud container node-pools create main-pool-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version PREVIOUS_VERSION \
  --num-nodes 20 \
  --machine-type MACHINE_TYPE \
  --disk-size DISK_SIZE

# 2. Cordon the mixed-version pool
kubectl cordon -l cloud.google.com/gke-nodepool=MAIN_POOL_NAME

# 3. Drain workloads to new pool
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --grace-period=300

# 4. Delete old pool once migration complete
gcloud container node-pools delete MAIN_POOL_NAME --cluster CLUSTER_NAME --zone ZONE
```

## Next Steps for Other Pools

After resolving the main pool:

1. **Apply lessons learned** - if it was a PDB or surge setting issue, configure the other pools appropriately
2. **Upgrade remaining pools** - the other two pools can be upgraded normally once main pool is resolved
3. **Consider skip-level upgrades** - if the other pools are more than 1 version behind, they can jump directly to 1.32 in one operation

## Most Likely Root Causes to Check

1. **PDB too restrictive** (most common) - allows 0 disruptions
2. **Resource constraints** - not enough capacity for surge nodes  
3. **Bare pods** - pods without controllers can't be rescheduled
4. **Admission webhooks** - blocking pod creation on new nodes

**I'd start with the retry approach** - it's simpler and usually succeeds once the blocking issue is resolved. What error details do you see in the operation logs?