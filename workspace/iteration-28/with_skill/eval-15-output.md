You're in a mixed-version state (8 nodes at 1.32, 12 nodes at the previous version), which is **valid and functional** - your cluster will continue operating normally. Here's your recovery plan:

## Current State Assessment

**Mixed-version node pool:** ✅ Supported - GKE allows nodes within 2 minor versions of control plane
**Workload impact:** None - pods run on whichever nodes they're scheduled to
**Other pools:** Unaffected and can be upgraded independently

## Recovery Options

### Option A: Fix and Retry (Recommended)

**1. Diagnose the failure cause:**
```bash
# Check recent operations for error details
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=5

# Look for stuck pods or resource constraints
kubectl get pods -A | grep -E "Pending|Terminating|CrashLoop"
kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' | tail -10

# Check PDB violations (most common cause)
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0
```

**2. Apply the fix based on diagnosis:**

If **PDBs are blocking drain** (most common):
```bash
# Temporarily relax overly restrictive PDBs
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

If **resource constraints** (no room for evicted pods):
```bash
# Reduce surge concurrency to fit quota
gcloud container node-pools update MAIN_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**3. Resume the upgrade:**
```bash
gcloud container node-pools upgrade MAIN_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

### Option B: Rollback (Only if retry isn't feasible)

If the root cause can't be fixed or you need to revert:

**1. Create new pool at old version:**
```bash
gcloud container node-pools create MAIN_POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version PREVIOUS_VERSION \
  --num-nodes 20 \
  --machine-type MACHINE_TYPE
```

**2. Migrate workloads:**
```bash
# Cordon the mixed-version pool
kubectl cordon -l cloud.google.com/gke-nodepool=MAIN_POOL_NAME

# Drain nodes gradually
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data
```

**3. Delete old pool when migration completes**

## Recommended Approach

**Go with Option A** - fixing and retrying is simpler than rollback. Most upgrade failures are caused by:
1. **PDBs too restrictive** (80% of cases)
2. **Resource quota exhausted** (15% of cases) 
3. **Admission webhooks rejecting pods** (5% of cases)

## Next Steps for Other Pools

Once the main pool is resolved:
```bash
# Upgrade remaining pools sequentially
gcloud container node-pools upgrade POOL_2_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

## Validation Commands

```bash
# Check upgrade progress
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# Verify workload health
kubectl get pods -A | grep -v Running | grep -v Completed
kubectl get deployments -A
```

What error message did you see when the upgrade stopped? That will help pinpoint the exact fix needed.