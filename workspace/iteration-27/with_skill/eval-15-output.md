You have a **partially upgraded node pool** - this is a common scenario and your cluster is in a **valid, functional state**. Let me walk you through your options and the recommended approach.

## Current Cluster State
- ✅ Control plane: 1.32 (upgraded successfully)
- 🔄 Main workload pool: Mixed state (8 nodes at 1.32, 12 nodes at old version)
- ⏸️ Other two pools: Still at old version (waiting)
- 🟢 **Cluster functionality**: Fully operational - mixed node versions are supported

## Recommended Approach: Fix and Retry

**Option A: Identify root cause and resume upgrade (recommended)**

First, diagnose why the upgrade stopped:

```bash
# Check the failed operation details
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES"

# Look for stuck/problematic pods
kubectl get pods -A | grep -E "Pending|Terminating|CrashLoop"

# Check PDBs that might be blocking drain
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# Check for resource constraints
kubectl get events -A --field-selector reason=FailedScheduling | tail -10
kubectl top nodes
```

Common fixes based on the root cause:

**If PDBs are blocking:**
```bash
# Temporarily relax overly restrictive PDBs
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

**If resource constraints:**
```bash
# Reduce surge to fit quota
gcloud container node-pools update MAIN_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Resume the upgrade:**
```bash
gcloud container node-pools upgrade MAIN_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

## Alternative: Complete Rollback (if target version has critical issues)

**Option B: Rollback to uniform old version (only if necessary)**

⚠️ **Note**: You cannot downgrade the 8 already-upgraded nodes in-place. Rollback requires manual node pool replacement:

```bash
# 1. Create new pool at old version
gcloud container node-pools create MAIN_POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version OLD_VERSION \
  --num-nodes 20 \
  --machine-type MACHINE_TYPE

# 2. Cordon the mixed pool
kubectl get nodes -l cloud.google.com/gke-nodepool=MAIN_POOL_NAME -o name | xargs kubectl cordon

# 3. Drain workloads to new pool
kubectl get nodes -l cloud.google.com/gke-nodepool=MAIN_POOL_NAME -o name | \
  xargs -I {} kubectl drain {} --ignore-daemonsets --delete-emptydir-data --grace-period=300

# 4. Delete old mixed pool
gcloud container node-pools delete MAIN_POOL_NAME --cluster CLUSTER_NAME --zone ZONE
```

## Next Steps After Main Pool Recovery

Once your main workload pool is resolved:

**Upgrade remaining pools:**
```bash
# Upgrade the other two pools
gcloud container node-pools upgrade POOL_2_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

gcloud container node-pools upgrade POOL_3_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

## Monitoring Progress

```bash
# Watch node versions converge
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Verify workload health
kubectl get pods -A | grep -v Running | grep -v Completed
kubectl get deployments -A
```

## Why Retry is Usually Better

- ✅ **Simpler recovery** - just fix the issue and resume
- ✅ **Faster** - no need to recreate/migrate entire pool  
- ✅ **Less disruptive** - workloads stay running during retry
- ✅ **Reaches target state** - all nodes end up at 1.32

**Recommendation**: Go with Option A (fix and retry) unless you've discovered a critical issue with version 1.32 that requires rollback. The mixed node state isn't a problem - it's designed to work this way during upgrades.

What error message did you see when the upgrade stopped? That will help me give you the specific fix for your situation.