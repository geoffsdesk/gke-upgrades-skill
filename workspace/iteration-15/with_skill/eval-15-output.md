Based on your situation, you have a partially upgraded node pool (8/20 nodes at 1.32, 12 at the previous version). This is a **valid operational state** - GKE supports version skew within 2 minor versions, so your cluster will continue running normally.

Here's your recovery plan:

## Current State Assessment

First, let's verify the cluster state:

```bash
# Check node versions
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool

# Check for any stuck pods
kubectl get pods -A | grep -v Running | grep -v Completed

# Find the failed upgrade operation
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES"
```

## Recommended Approach: Fix and Retry

**This is usually the best path forward** - simpler than rollback and gets you to a consistent state.

### Step 1: Diagnose the Root Cause

Most common causes of partial failures:

```bash
# Check for PDBs blocking drain
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# Check for resource constraints
kubectl get pods -A | grep Pending
kubectl get events -A --field-selector reason=FailedScheduling

# Check for bare pods (can't be rescheduled)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

### Step 2: Apply the Fix

**If PDBs are blocking (most common):**
```bash
# Temporarily relax the restrictive PDB
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"100%"}}'
```

**If resource constraints:**
```bash
# Reduce surge or switch to drain-first
gcloud container node-pools update MAIN_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**If bare pods exist:**
```bash
# Delete them (they won't reschedule anyway)
kubectl delete pod POD_NAME -n NAMESPACE
```

### Step 3: Resume the Upgrade

```bash
# Retry the failed node pool upgrade
gcloud container node-pools upgrade MAIN_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

### Step 4: Complete Remaining Pools

Once your main pool completes:

```bash
# Upgrade remaining node pools
gcloud container node-pools upgrade POOL_2_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

gcloud container node-pools upgrade POOL_3_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

## Alternative: Rollback (Only if unfixable)

If the root cause can't be resolved or the target version has critical issues:

```bash
# Create new pool at previous version
gcloud container node-pools create MAIN_POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version PREVIOUS_VERSION \
  --num-nodes 20 \
  --machine-type MACHINE_TYPE

# Cordon the mixed-version pool
kubectl cordon -l cloud.google.com/gke-nodepool=MAIN_POOL_NAME

# Drain workloads to new pool (this takes time)
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data

# Delete old pool when migration complete
gcloud container node-pools delete MAIN_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE
```

## Important Notes

- **No urgency required** - your cluster is stable in the mixed-version state
- **Workloads continue running** on both old and new nodes
- **Fix-and-retry is usually faster** than rollback
- **Restore PDBs** to original settings after upgrade completes

What error message did you see when the upgrade failed? That will help pinpoint the exact root cause.