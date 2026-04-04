# GKE Node Pool Upgrade Stuck - Diagnostic & Fix

Your node pool upgrade is stuck because pods aren't draining from the remaining 9 nodes. Let's diagnose and fix this systematically.

## Immediate Diagnosis Commands

Run these commands to identify the root cause:

### 1. Check for PDB blocking drain (most common cause)
```bash
kubectl get pdb -A -o wide
# Look for any PDB with ALLOWED DISRUPTIONS = 0

# If you find restrictive PDBs, get details:
kubectl describe pdb PDB_NAME -n NAMESPACE
```

### 2. Check for pods that can't be rescheduled
```bash
# Look for Pending pods (can't find nodes to land on)
kubectl get pods -A | grep Pending

# Check scheduling failures
kubectl get events -A --field-selector reason=FailedScheduling --sort-by='.lastTimestamp'
```

### 3. Check for bare pods (won't be rescheduled)
```bash
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

### 4. Check resource pressure
```bash
kubectl top nodes
kubectl describe nodes | grep -A 5 "Allocated resources"
```

### 5. Monitor the stuck upgrade operation
```bash
gcloud container operations list --cluster CLUSTER_NAME --zone us-east1 --filter="operationType=UPGRADE_NODES"
```

## Most Likely Fixes

### Fix #1: PDB Too Restrictive (90% of stuck upgrades)

If you found PDBs with 0 allowed disruptions:

**Temporary fix - relax the PDB:**
```bash
# Back up current PDB first
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup-$(date +%Y%m%d).yaml

# Allow 1 pod disruption temporarily
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":1}}'
```

**Restore after upgrade:**
```bash
kubectl apply -f pdb-backup-$(date +%Y%m%d).yaml
```

### Fix #2: Resource Constraints (pods can't land anywhere)

If you see Pending pods with "insufficient cpu/memory" errors:

**Option A - Reduce surge to fit quota:**
```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1 \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Option B - Scale down non-critical workloads:**
```bash
kubectl scale deployment NON_CRITICAL_APP --replicas=0 -n NAMESPACE
# Do this for 2-3 non-critical deployments to free capacity
```

### Fix #3: Bare Pods (can't be rescheduled)

If you found bare pods (pods without ownerReferences):
```bash
# These must be manually deleted - they won't reschedule anyway
kubectl delete pod POD_NAME -n NAMESPACE --grace-period=30
```

## Monitor Progress After Fix

```bash
# Watch nodes upgrade in real-time
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check no pods stuck in bad states
kubectl get pods -A | grep -E "Terminating|Pending|CrashLoopBackOff"

# Verify upgrade operation is progressing
gcloud container operations list --cluster CLUSTER_NAME --zone us-east1 --limit=1
```

## Prevention for Next Time

**Configure appropriate surge settings:**
```bash
# For stateless workloads
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1 \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# For stateful workloads
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1 \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Review PDBs before upgrading:**
```bash
# Check all PDBs allow at least 1 disruption
kubectl get pdb -A -o custom-columns=NAME:.metadata.name,NAMESPACE:.metadata.namespace,MIN_AVAILABLE:.spec.minAvailable,MAX_UNAVAILABLE:.spec.maxUnavailable,ALLOWED:.status.disruptionsAllowed
```

## If Still Stuck After 30 Minutes

Contact GKE support with:
- Cluster name and zone: `CLUSTER_NAME` in `us-east1`
- Current upgrade operation ID (from the operations list command above)
- Node pool name being upgraded
- Mention "node pool upgrade stuck at 3/12 nodes, pods not draining after applying PDB/resource fixes"

The upgrade should resume within 10-15 minutes after applying the appropriate fix above. PDB issues are the #1 cause of stuck upgrades, so start there first.