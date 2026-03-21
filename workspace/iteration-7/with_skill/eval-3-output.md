I'll help you diagnose and fix this stuck node pool upgrade. Let's work through the most common causes systematically.

## Immediate Diagnosis Steps

Run these commands to identify what's blocking the drain:

### 1. Check for PDB blocking drain (most common cause)
```bash
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# If you see any PDBs with 0 allowed disruptions:
kubectl describe pdb PDB_NAME -n NAMESPACE
```

### 2. Check for pods that can't be evicted
```bash
# Find pods stuck in terminating state
kubectl get pods -A | grep Terminating

# Check for scheduling failures on new nodes
kubectl get pods -A | grep Pending
kubectl get events -A --field-selector reason=FailedScheduling --sort-by='.lastTimestamp' | tail -10
```

### 3. Check for bare pods (not managed by controllers)
```bash
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

### 4. Check current upgrade operation status
```bash
gcloud container operations list --cluster CLUSTER_NAME --zone us-east1 --filter="operationType=UPGRADE_NODES" --limit=3
```

## Most Likely Fixes

Based on the symptoms, here are the fixes in order of probability:

### Fix 1: Temporarily relax PDBs
If step 1 found PDBs with 0 allowed disruptions:

```bash
# Back up the original PDB
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup.yaml

# Temporarily allow all disruptions
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"100%"}}'
```

### Fix 2: Delete bare pods
If step 3 found bare pods (they won't reschedule anyway):

```bash
kubectl delete pod POD_NAME -n NAMESPACE --force --grace-period=0
```

### Fix 3: Increase surge capacity
If nodes are resource-constrained and can't fit replacement pods:

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1 \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

### Fix 4: Force drain stuck nodes (nuclear option)
If other fixes don't work, manually drain the stuck nodes:

```bash
# Identify which nodes aren't draining
kubectl get nodes -o wide

# Force drain (replace NODE_NAME with actual stuck node)
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --force --grace-period=0
```

## Validation

After applying fixes, monitor progress:

```bash
# Watch upgrade progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check for any remaining stuck pods
kubectl get pods -A | grep -E "Terminating|Pending"

# Monitor the upgrade operation
gcloud container operations list --cluster CLUSTER_NAME --zone us-east1 --limit=1
```

## Post-Fix Cleanup

Once the upgrade completes successfully:

1. **Restore original PDBs** (if you modified them):
```bash
kubectl apply -f pdb-backup.yaml
```

2. **Reset surge settings** (if you increased them):
```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1 \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

## Escalation Path

If the upgrade remains stuck after trying these fixes for 30+ minutes, contact Google Cloud Support with:
- Cluster name and zone
- Node pool name  
- Current operation ID (from the operations list command)
- Screenshots of the diagnostic command outputs

The fact that 3/12 nodes upgraded successfully suggests the process is working but something is blocking the drain of the remaining 9 nodes. The diagnostic steps above will identify the specific blocker.

**Start with checking PDBs first** - that's the cause in ~80% of stuck drain scenarios.