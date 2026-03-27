# Node Pool Upgrade Recovery Plan

## Current State Assessment

Your cluster is in a **mixed-version state** with:
- ✅ Control plane: 1.32 (upgraded successfully)  
- ⚠️ Main workload pool: 8 nodes at 1.32, 12 nodes at previous version (failed partway)
- 🔄 Other pools: Still at previous version (not started)

**Important:** This mixed state is **valid and functional**. Your workloads continue running normally across all nodes. No immediate action required for service continuity.

## Recommended Recovery: Option A - Retry (Fix & Resume)

This is the cleanest path forward in most cases.

### Step 1: Diagnose the Root Cause

```bash
# Check current node versions
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool

# Look for stuck/pending pods
kubectl get pods -A | grep -E "Pending|Terminating|ContainerCreating"

# Check recent events for clues
kubectl get events -A --sort-by='.lastTimestamp' | tail -20

# Check PDBs blocking drain
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# Check for resource constraints
kubectl top nodes
kubectl get events -A --field-selector reason=FailedScheduling
```

### Step 2: Common Fixes

**If PDBs are blocking:**
```bash
# Temporarily relax the restrictive PDB
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

**If resource constraints (no room for surge nodes):**
```bash
# Reduce surge to 1 node at a time
gcloud container node-pools update MAIN_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**If quota exhausted:**
```bash
# Switch to drain-first (no extra quota needed)
gcloud container node-pools update MAIN_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

### Step 3: Resume the Upgrade

```bash
# Resume the failed node pool upgrade
gcloud container node-pools upgrade MAIN_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

### Step 4: Complete Remaining Pools

Once the main pool completes:
```bash
# Upgrade the other two pools (can run in parallel if desired)
gcloud container node-pools upgrade POOL_2_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE &

gcloud container node-pools upgrade POOL_3_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE &
```

## Alternative: Option B - Rollback (Only if Necessary)

Use this if the root cause is unfixable or version 1.32 has critical defects.

**⚠️ Warning:** You cannot downgrade already-upgraded nodes in-place. This requires manual blue-green migration.

```bash
# 1. Create new pool at previous version
gcloud container node-pools create MAIN_POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version PREVIOUS_VERSION \
  --num-nodes 20 \
  --machine-type SAME_MACHINE_TYPE

# 2. Cordon the mixed pool
kubectl cordon -l cloud.google.com/gke-nodepool=MAIN_POOL_NAME

# 3. Drain workloads to new pool
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --grace-period=300

# 4. Delete old pool when empty
gcloud container node-pools delete MAIN_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE
```

## Validation Checklist

After either approach:

```bash
# ✅ All nodes at target version
kubectl get nodes -o wide

# ✅ All workloads healthy  
kubectl get pods -A | grep -v Running | grep -v Completed

# ✅ No stuck operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE

# ✅ Application health checks passing
# (Run your specific smoke tests here)
```

## Prevention for Next Time

```bash
# Set conservative surge settings before upgrading
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# Review PDBs aren't overly restrictive
kubectl get pdb -A -o yaml | grep -A 3 -B 3 "minAvailable\|maxUnavailable"
```

**Recommendation:** Start with Option A (fix and retry). It's faster and results in a cleaner final state. Only consider rollback if you discover a critical issue with version 1.32 itself.

What specific error message did you see when the upgrade stopped? This will help pinpoint the exact fix needed.