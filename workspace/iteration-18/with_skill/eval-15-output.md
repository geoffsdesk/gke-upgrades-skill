You're in a mixed-version state (8 nodes at 1.32, 12 nodes at the old version), which is **valid and functional** - your cluster will continue operating normally. Here's your recovery plan:

## Current State Assessment

**Cluster Status:** ✅ Operational
- Control plane: 1.32 ✅
- Main workload pool: Mixed (8/20 upgraded) ⚠️
- Other pools: Old version (untouched) ✅

**No immediate action required** - workloads run on whichever nodes they're scheduled to. GKE allows nodes within 2 minor versions of the control plane.

## Recovery Options

### Option A: Fix and Retry (Recommended)

This is typically faster and simpler than rollback.

**1. Diagnose the root cause:**
```bash
# Check the failed operation details
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES" --limit=3

# Most common causes - check in this order:
kubectl get pdb -A -o wide  # Look for ALLOWED DISRUPTIONS = 0
kubectl get pods -A | grep Pending  # Resource constraints
kubectl get events -A --field-selector reason=FailedScheduling --sort-by='.lastTimestamp' | tail -10
```

**2. Apply the fix based on diagnosis:**
```bash
# If PDB blocking (most common):
kubectl patch pdb PDB_NAME -n NAMESPACE -p '{"spec":{"maxUnavailable":"50%"}}'

# If resource constraints:
gcloud container node-pools update POOL_NAME --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 1 --max-unavailable-upgrade 0  # Reduce surge pressure

# If bare pods blocking:
kubectl get pods -A -o json | jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
# Delete any bare pods found
```

**3. Resume the upgrade:**
```bash
gcloud container node-pools upgrade POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

**4. Monitor progress:**
```bash
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep POOL_NAME'
```

### Option B: Rollback (Only if unfixable or critical version defect)

**Warning:** Cannot downgrade already-upgraded nodes in-place. Requires manual migration.

```bash
# 1. Create new pool at old version
gcloud container node-pools create POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version OLD_VERSION \
  --num-nodes 20 \
  --machine-type ORIGINAL_MACHINE_TYPE

# 2. Cordon the mixed pool
kubectl cordon -l cloud.google.com/gke-nodepool=POOL_NAME

# 3. Drain workloads to new pool
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --grace-period=300
# Repeat for each node in the mixed pool

# 4. Delete mixed pool
gcloud container node-pools delete POOL_NAME --cluster CLUSTER_NAME --zone ZONE
```

## Recommended Approach

**Go with Option A (fix and retry)** unless:
- You've identified a critical defect in version 1.32
- The root cause cannot be resolved
- You're under extreme time pressure

## Next Steps for Other Pools

Once the main pool is resolved:
1. Apply the same fix to prevent the same issue
2. Consider **skip-level upgrades** for the remaining pools (old_version → 1.32 directly) to save time
3. Use the lessons learned to adjust surge settings before upgrading

## Commands to Run Right Now

```bash
# 1. Check what failed
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=3

# 2. Quick PDB check (most likely culprit)
kubectl get pdb -A -o wide

# 3. Verify cluster is still functional
kubectl get pods -A | grep -v Running | grep -v Completed
```

What error message did you see when the upgrade failed? That will help pinpoint the exact fix needed.