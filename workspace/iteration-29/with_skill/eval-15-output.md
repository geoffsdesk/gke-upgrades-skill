You're in a valid mixed-version state that GKE fully supports - 8 nodes at 1.32, 12 at the previous version. Your cluster is operational and there's no forced action needed. Here's how to proceed:

## Current Status Assessment

```bash
# Verify cluster state
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=5

# Check what's blocking the upgrade
kubectl get pods -A | grep -E "Terminating|Pending|Error"
kubectl get pdb -A -o wide | grep "0.*0"  # Look for restrictive PDBs
```

## Recommended Path: Fix and Retry

**This is simpler than rollback and gets you to a consistent end state.**

### Step 1: Diagnose the failure cause
Most common issues:
- **PDB blocking drain**: `kubectl get pdb -A` - look for ALLOWED DISRUPTIONS = 0
- **Resource constraints**: `kubectl get events -A --field-selector reason=FailedScheduling`
- **Bare pods**: Check for pods not managed by controllers
- **Admission webhooks**: Rejecting pod recreation

### Step 2: Apply the fix
For PDBs (most common):
```bash
# Temporarily relax the blocking PDB
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

For resource constraints:
```bash
# Reduce surge to minimal quota usage
gcloud container node-pools update MAIN_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### Step 3: Resume the upgrade
```bash
gcloud container node-pools upgrade MAIN_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

## Alternative: Rollback (only if retry fails)

If the root cause can't be fixed or 1.32 has critical issues:

1. **Create new pool at old version**:
```bash
gcloud container node-pools create MAIN_POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version OLD_VERSION \
  --num-nodes 20 \
  --machine-type MACHINE_TYPE
```

2. **Migrate workloads**:
```bash
# Cordon mixed-version pool
kubectl cordon -l cloud.google.com/gke-nodepool=MAIN_POOL_NAME
# Let pods reschedule naturally or force with drain
```

3. **Delete old pool** once workloads are stable

## Complete the remaining pools

After your main pool is consistent:
```bash
# Upgrade the other two pools
gcloud container node-pools upgrade POOL_2_NAME \
  --cluster CLUSTER_NAME --zone ZONE --cluster-version 1.32

gcloud container node-pools upgrade POOL_3_NAME \
  --cluster CLUSTER_NAME --zone ZONE --cluster-version 1.32
```

**What specific error message did you see?** This will help me give you the exact fix for your situation.