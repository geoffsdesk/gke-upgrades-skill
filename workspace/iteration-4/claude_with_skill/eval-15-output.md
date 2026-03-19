Let me help you diagnose and fix this stuck node pool upgrade. Since you have 8 out of 20 nodes upgraded, we need to identify why the remaining 12 are stuck.

## Immediate Diagnosis

Run these commands to understand what's blocking the upgrade:

```bash
# Check current node status and versions
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep WORKLOAD_POOL_NAME

# Look for the specific upgrade error
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES" --limit=5

# Check for pods that can't be evicted (most common cause)
kubectl get pods -A | grep -E "Terminating|Pending"

# Check PDB restrictions
kubectl get pdb -A -o wide
```

## Most Likely Causes & Fixes

### 1. PDB Blocking Pod Eviction (80% of cases)

**Check:** Look for PDBs with `ALLOWED DISRUPTIONS = 0`

**Fix:** Temporarily relax the restrictive PDB:
```bash
# Identify the blocking PDB
kubectl describe pdb PDB_NAME -n NAMESPACE

# Back up and temporarily allow more disruptions
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup.yaml
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

### 2. Insufficient Surge Capacity

**Check:** Are new pods stuck `Pending` due to resource constraints?

**Fix:** Increase surge capacity:
```bash
gcloud container node-pools update WORKLOAD_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

### 3. Bare Pods or Long Termination

**Check:** Find bare pods or pods with excessive grace periods:
```bash
# Bare pods (no owner references)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Long grace periods
kubectl get pods -A -o json | \
  jq '.items[] | select(.spec.terminationGracePeriodSeconds > 120) | {ns:.metadata.namespace, name:.metadata.name, grace:.spec.terminationGracePeriodSeconds}'
```

**Fix:** Delete bare pods manually (they won't reschedule anyway).

## Resume the Upgrade

Once you've addressed the blocking issue, the upgrade should automatically resume. Monitor progress:

```bash
# Watch node upgrade progress
watch 'kubectl get nodes -L cloud.google.com/gke-nodepool | grep WORKLOAD_POOL_NAME'

# Monitor the operation
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=1
```

## If Still Stuck After 30 Minutes

Cancel and restart the upgrade:
```bash
# Note: This will complete the current node being upgraded, then stop
# You'll need to restart the upgrade for remaining nodes

# Check if there are additional blocking issues
kubectl get events -A --field-selector reason=FailedScheduling | tail -20
```

## After Main Pool Completes

Don't forget your other two node pools. Upgrade them one at a time:
```bash
gcloud container node-pools upgrade OTHER_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30
```

**Critical:** Don't leave node pools more than 2 minor versions behind the control plane (1.30). If they're currently at 1.27 or older, you must upgrade them soon.

What specific error message are you seeing in the operations list? That will help me give you a more targeted fix.