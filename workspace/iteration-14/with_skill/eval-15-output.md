# GKE Node Pool Partial Upgrade Recovery

## Current situation assessment
- **Control plane**: Successfully upgraded to 1.32 ✓
- **Main workload pool**: 8/20 nodes at 1.32, 12 nodes at previous version (mixed state)
- **Other pools**: Not yet upgraded
- **Cluster health**: Functional - GKE supports nodes within 2 minor versions of control plane

Your cluster is **operationally safe** in this mixed-version state. No immediate action required to keep services running.

## Recommended approach: Retry (Option A)

This is the simplest path - fix the root cause and resume the upgrade.

### 1. Diagnose the failure
```bash
# Check for common blocking issues
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

kubectl get pods -A | grep Pending
kubectl get events -A --field-selector reason=FailedScheduling --sort-by='.lastTimestamp'

# Check for bare pods (can't be rescheduled)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

### 2. Apply the appropriate fix

**If PDB is blocking (most common):**
```bash
# Temporarily relax overly restrictive PDBs
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"50%"}}'
```

**If resource constraints:**
```bash
# Scale down non-critical workloads temporarily
kubectl scale deployment NON_CRITICAL_APP --replicas=0

# Or adjust surge settings
gcloud container node-pools update MAIN_WORKLOAD_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 1
```

**If bare pods exist:**
```bash
# Delete bare pods (they won't reschedule anyway)
kubectl delete pod POD_NAME -n NAMESPACE
```

### 3. Resume the upgrade
```bash
gcloud container node-pools upgrade MAIN_WORKLOAD_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

### 4. Continue with remaining pools
Once the main pool completes successfully:
```bash
# Upgrade remaining pools one at a time
gcloud container node-pools upgrade POOL_2_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

## Alternative: Rollback (Option B - only if retry isn't viable)

Only choose this if the root cause can't be fixed or the target version has critical defects.

⚠️ **Note**: Already-upgraded nodes can't be downgraded in-place. This requires manual blue-green migration.

```bash
# 1. Create new pool at previous version
gcloud container node-pools create main-workload-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version PREVIOUS_VERSION \
  --num-nodes 20 \
  --machine-type EXISTING_MACHINE_TYPE

# 2. Cordon the partially-upgraded pool
kubectl cordon -l cloud.google.com/gke-nodepool=MAIN_WORKLOAD_POOL

# 3. Migrate workloads and verify
# 4. Delete old pool
gcloud container node-pools delete MAIN_WORKLOAD_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE
```

## Post-resolution checklist
```
- [ ] All node pools at 1.32
- [ ] All nodes Ready: `kubectl get nodes`
- [ ] No pending/stuck pods: `kubectl get pods -A | grep -v Running`
- [ ] Restore original PDB settings
- [ ] Application smoke tests passing
- [ ] Document root cause and resolution
```

**Recommendation**: Go with Option A (retry). It's faster, simpler, and gets your cluster to a consistent state. The mixed-version scenario is normal during upgrades and doesn't require emergency action.

What error message did you see when the upgrade stopped? This will help pinpoint the exact fix needed.