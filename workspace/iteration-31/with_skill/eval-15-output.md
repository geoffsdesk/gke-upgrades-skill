You're in a **mixed-version state** - some nodes at 1.32, others at the previous version. This is **valid and functional** - GKE allows nodes within 2 minor versions of the control plane, and your workloads will continue running normally.

## Immediate Status Check

First, let's diagnose what stopped the upgrade:

```bash
# Check current node versions
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,POOL:.metadata.labels.cloud\.google\.com/gke-nodepool

# Check recent upgrade operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=5

# Look for recent events that might explain the failure
kubectl get events -A --sort-by='.lastTimestamp' | tail -20
```

## Two Recovery Options

### Option A: Resume the Upgrade (Recommended)

This is usually the best path - fix the root cause and continue:

1. **Identify the root cause** (most common issues):
   ```bash
   # Check for PDB blocking drain
   kubectl get pdb -A -o wide
   # Look for ALLOWED DISRUPTIONS = 0
   
   # Check for resource constraints
   kubectl get pods -A | grep Pending
   kubectl get events -A --field-selector reason=FailedScheduling
   
   # Check for bare pods that can't reschedule
   kubectl get pods -A -o json | \
     jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
   ```

2. **Apply the fix** (examples):
   ```bash
   # If PDB is too restrictive - temporarily relax it
   kubectl patch pdb PDB_NAME -n NAMESPACE \
     -p '{"spec":{"maxUnavailable":"50%"}}'
   
   # If resource constrained - reduce surge or scale down non-critical workloads
   gcloud container node-pools update POOL_NAME \
     --cluster CLUSTER_NAME \
     --zone ZONE \
     --max-surge-upgrade 1 \
     --max-unavailable-upgrade 0
   ```

3. **Resume the upgrade**:
   ```bash
   gcloud container node-pools upgrade POOL_NAME \
     --cluster CLUSTER_NAME \
     --zone ZONE \
     --cluster-version 1.32
   ```

### Option B: Rollback (Only if target version has critical defects)

If you need to rollback due to a problem with 1.32 itself:

```bash
# Create new pool at previous version
gcloud container node-pools create POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version PREVIOUS_VERSION \
  --num-nodes 20 \
  --machine-type MACHINE_TYPE

# Cordon the mixed pool and migrate workloads
kubectl cordon -l cloud.google.com/gke-nodepool=POOL_NAME

# Drain workloads to new pool, then delete mixed pool
```

## My Recommendation

**Go with Option A** unless you've discovered a critical issue with 1.32. The mixed state isn't hurting you, and resuming is simpler than rolling back. Once you fix the root cause and complete this pool, you can upgrade your other two pools normally.

What error message did you see when the upgrade stopped? That will help us identify the specific fix needed.