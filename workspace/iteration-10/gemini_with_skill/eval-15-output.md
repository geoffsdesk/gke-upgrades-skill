A partially upgraded node pool is a common scenario when GKE encounters a workload that it cannot safely move. The good news is that your cluster is perfectly safe—GKE is designed to tolerate node version skew (having some nodes on 1.32 and some on your previous version) while you resolve the issue. 

When an upgrade stops partway through, it usually means GKE's cordon-and-drain process hit a roadblock and timed out (GKE waits up to 1 hour for pods to evict before aborting or force-proceeding, depending on the blocker).

Here is the step-by-step runbook to diagnose the failure, remove the blocker, and resume your upgrades.

### Phase 1: Identify the exact error

First, let's see exactly why GKE halted the operation.

```bash
# 1. Find the failed operation ID
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --location REGION_OR_ZONE \
  --filter="operationType=UPGRADE_NODES AND status=DONE" \
  --limit=5

# 2. Describe the failed operation to see the error message
gcloud container operations describe OPERATION_ID \
  --location REGION_OR_ZONE
```
*Look for errors mentioning "PodDisruptionBudget", "quota", "scheduling", or "eviction".*

---

### Phase 2: Troubleshoot the top 3 common blockers

Work through these diagnostics in order to find what stopped the remaining 12 nodes from draining.

#### 1. PodDisruptionBudgets (PDBs) blocking eviction (Most Common)
If an application has a restrictive PDB (e.g., `minAvailable: 100%` or `maxUnavailable: 0`) and doesn't have enough ready replicas to satisfy it, GKE will refuse to drain the node.

**Diagnose:**
```bash
# Look for PDBs where ALLOWED DISRUPTIONS = 0
kubectl get pdb -A
```
**Fix:**
Temporarily relax the PDB to allow the node to drain. 
```bash
# Back up the current PDB
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup.yaml

# Patch the PDB to allow disruption temporarily
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"100%"}}'
```

#### 2. Resource Constraints & Pending Pods
GKE might have cordoned a node to drain it, but the pods cannot schedule anywhere else because the cluster is out of CPU/Memory, or your surge nodes failed to provision due to Compute Engine quota limits.

**Diagnose:**
```bash
# Look for pods stuck in a Pending state
kubectl get pods -A | grep Pending

# Check WHY they are pending (look for insufficient CPU/Memory or volume binding issues)
kubectl describe pod POD_NAME -n NAMESPACE | tail -n 20
```
**Fix:**
If pods are pending due to resources, you may need to increase your node pool's `maxSurge` setting to give GKE more temporary capacity during the upgrade, or scale down non-critical workloads:
```bash
# Increase surge capacity to speed up/unblock scheduling
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --location REGION_OR_ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

#### 3. Bare Pods (Unmanaged Pods)
Pods that are not managed by a controller (like a Deployment, StatefulSet, or DaemonSet) cannot be rescheduled by GKE. GKE will block the upgrade rather than permanently deleting your pod.

**Diagnose:**
```bash
# Find pods with no owner references
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```
**Fix:**
Delete the bare pods manually so GKE can proceed. You should recreate these as part of a Deployment or Job later.
```bash
kubectl delete pod POD_NAME -n NAMESPACE
```

---

### Phase 3: Resume the Upgrade

Once you have resolved the blocking issue (relaxed the PDB, freed up resources, or deleted the bare pod), you simply tell GKE to run the upgrade command again. It will automatically detect the 8 already-upgraded nodes, skip them, and resume draining the remaining 12.

```bash
# Trigger the upgrade again targeting the 1.32 version
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --location REGION_OR_ZONE \
  --cluster-version 1.32.x-gke.x # (Replace with your exact target 1.32 version)

# Monitor the progress in a separate terminal
watch 'kubectl get nodes -o wide | grep -E "NAME|CURRENT_VERSION|TARGET_VERSION"'
```

---

### Phase 4: Upgrade the Remaining Node Pools

Once the main workload pool finishes, you can proceed with the remaining two pools. To prevent them from failing, **run a quick pre-flight check** based on what you learned:

- [ ] Ensure `kubectl get pdb -A` shows >0 allowed disruptions for apps running on these pools.
- [ ] Confirm no bare pods exist on those specific nodes.
- [ ] Check `gcloud compute project-info describe` or IAM quotas to ensure you have enough compute quota to support the surge nodes for these remaining pools.

```bash
# Upgrade the remaining pools one by one
gcloud container node-pools upgrade SECOND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --location REGION_OR_ZONE \
  --cluster-version 1.32.x-gke.x
```