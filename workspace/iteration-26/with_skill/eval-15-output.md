I'll help you recover from this partial node pool upgrade. Your cluster is currently in a **mixed-version state**, which is normal and functional - GKE allows this within the 2-minor-version skew policy.

## Current Cluster State Assessment

**Status:** Partially upgraded and stable
- Control plane: 1.32 ✓
- Main workload pool: 8/20 nodes at 1.32, 12/20 at previous version
- Other pools: Untouched at previous version
- **Your services are still running normally** - this mixed state doesn't break functionality

## Recovery Options

I recommend **Option A (Retry)** in most cases - it's simpler and gets you to a consistent state faster.

### Option A: Fix and Retry (Recommended)

**Step 1: Diagnose the failure**
```bash
# Check current upgrade status
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES" --limit=3

# Look for stuck/failing pods
kubectl get pods -A | grep -E "Pending|Terminating|CrashLoop"

# Check for PDB issues (most common cause)
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# Check resource constraints
kubectl get events -A --field-selector reason=FailedScheduling | tail -10
kubectl top nodes
```

**Step 2: Fix the root cause**

Most common issues and fixes:

**If PDB is blocking drain:**
```bash
# Temporarily relax the restrictive PDB
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

**If resource constraints (no room for pods):**
```bash
# Reduce surge to minimum
gcloud container node-pools update MAIN_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**If bare pods exist:**
```bash
# Find and delete them (they won't reschedule anyway)
kubectl get pods -A -o json | jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

**Step 3: Resume the upgrade**
```bash
# This continues from where it left off
gcloud container node-pools upgrade MAIN_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

**Step 4: Monitor progress**
```bash
watch 'kubectl get nodes -L cloud.google.com/gke-nodepool | grep MAIN_POOL_NAME'
```

### Option B: Rollback (Only if retry won't work)

Use this only if the root cause can't be fixed or if version 1.32 has a critical defect.

**Note:** You cannot downgrade the 8 already-upgraded nodes in-place. This requires a full pool recreation:

```bash
# Create new pool at previous version
gcloud container node-pools create MAIN_POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version PREVIOUS_VERSION \
  --num-nodes 20 \
  --machine-type ORIGINAL_MACHINE_TYPE \
  --disk-size ORIGINAL_DISK_SIZE

# Cordon the mixed-version pool
kubectl cordon -l cloud.google.com/gke-nodepool=MAIN_POOL_NAME

# Drain workloads to new pool (this will take time)
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --grace-period=300

# Delete old mixed pool once drained
gcloud container node-pools delete MAIN_POOL_NAME --cluster CLUSTER_NAME --zone ZONE
```

## Next Steps After Recovery

1. **Upgrade remaining pools** (once main pool is stable):
```bash
gcloud container node-pools upgrade POOL_2_NAME --cluster CLUSTER_NAME --zone ZONE --cluster-version 1.32
gcloud container node-pools upgrade POOL_3_NAME --cluster CLUSTER_NAME --zone ZONE --cluster-version 1.32
```

2. **Restore any temporary PDB changes**

3. **Document the lesson learned** - what caused the failure and how to prevent it

## Immediate Next Action

Run the diagnostic commands above to identify why the upgrade stopped. The most likely culprit is a PDB with `minAvailable` set too high, preventing pods from being evicted during drain.

**Which option do you prefer?** Most customers choose retry since it's faster and simpler. Let me know what the diagnostic commands show and I can give you the specific fix.