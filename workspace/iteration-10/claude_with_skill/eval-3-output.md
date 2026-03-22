# GKE Node Pool Upgrade Stuck - Diagnostic Runbook

Your upgrade is likely blocked by pod eviction issues. Let's diagnose systematically:

## 1. Check PodDisruptionBudgets (Most Common Cause)

```bash
# Find PDBs blocking eviction
kubectl get pdb -A -o wide

# Look for ALLOWED DISRUPTIONS = 0, then investigate:
kubectl describe pdb PDB_NAME -n NAMESPACE
```

**What to look for:** PDBs with `minAvailable` too high or `maxUnavailable` too low, preventing any pods from being evicted.

**Quick fix:**
```bash
# Temporarily relax the most restrictive PDB
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"100%"}}'
```

## 2. Check for Bare Pods (Can't Reschedule)

```bash
# Find pods without controllers
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

**Fix:** Delete bare pods - they won't reschedule anyway:
```bash
kubectl delete pod POD_NAME -n NAMESPACE
```

## 3. Check Resource Constraints

```bash
# Look for pods that can't be scheduled elsewhere
kubectl get pods -A | grep Pending
kubectl get events -A --field-selector reason=FailedScheduling | tail -20

# Check node resource usage
kubectl top nodes
```

**Fix if pods can't fit on other nodes:**
```bash
# Increase surge to create more capacity
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1-a \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

## 4. Check Current Drain Status

```bash
# See which nodes are being drained
kubectl get nodes -o wide | grep SchedulingDisabled

# Check what pods are stuck on draining nodes
kubectl get pods -A --field-selector spec.nodeName=NODE_NAME
```

## 5. Check for Stuck Terminating Pods

```bash
# Find pods stuck in Terminating state
kubectl get pods -A | grep Terminating

# Check their termination grace periods
kubectl get pods -A -o json | \
  jq '.items[] | select(.metadata.deletionTimestamp != null) | {ns:.metadata.namespace, name:.metadata.name, grace:.spec.terminationGracePeriodSeconds}'
```

## 6. Check GKE Operation Status

```bash
# Verify the upgrade operation is still active
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --zone us-east1-a \
  --filter="operationType=UPGRADE_NODES" \
  --limit=3
```

## Most Likely Quick Fixes

**For PDB issues (90% of stuck upgrades):**
1. Back up the PDB: `kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup.yaml`
2. Temporarily allow more disruptions: `kubectl patch pdb PDB_NAME -n NAMESPACE -p '{"spec":{"maxUnavailable":"50%"}}'`
3. Restore after upgrade: `kubectl apply -f pdb-backup.yaml`

**For resource constraints:**
```bash
# Add surge capacity to help with rescheduling
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1-a \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

## Monitor Progress

```bash
# Watch node upgrade progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Monitor stuck pods
watch 'kubectl get pods -A | grep -E "Terminating|Pending"'
```

## If Still Stuck After 30 Minutes

Contact GKE support with:
- Cluster name and zone
- Current operation ID from `gcloud container operations list`
- Output of the PDB and events checks above

The upgrade should resume once pod eviction blockers are resolved. GKE will continue from where it left off - no need to restart the operation.