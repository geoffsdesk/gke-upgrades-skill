# GKE Node Pool Upgrade Stuck - Troubleshooting Guide

Your upgrade is likely stuck due to pod eviction issues. Let's diagnose systematically:

## Immediate Diagnostic Commands

Run these in order to identify the root cause:

### 1. Check PDBs (most common cause)
```bash
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# Get details on restrictive PDBs
kubectl get pdb -A -o json | jq -r '.items[] | select(.status.disruptionsAllowed == 0) | "\(.metadata.namespace)/\(.metadata.name): \(.status.currentHealthy)/\(.status.desiredHealthy) healthy, \(.status.disruptionsAllowed) disruptions allowed"'
```

### 2. Check for bare pods
```bash
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

### 3. Check resource constraints
```bash
kubectl get pods -A | grep Pending
kubectl get events -A --field-selector reason=FailedScheduling --sort-by='.lastTimestamp' | tail -10
```

### 4. Check terminating pods
```bash
kubectl get pods -A | grep Terminating
```

## Most Likely Fixes

### If PDBs are blocking (90% chance this is your issue):

**Identify the problematic PDB:**
```bash
# Find PDBs with 0 disruptions allowed
kubectl describe pdb -A | grep -A 10 -B 2 "Disruptions allowed.*0"
```

**Temporary fix - relax the PDB:**
```bash
# Replace NAMESPACE and PDB_NAME with actual values
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'

# Or allow more disruptions:
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"minAvailable":1}}'
```

### If bare pods exist:
```bash
# Delete bare pods (they won't reschedule anyway)
kubectl delete pod POD_NAME -n NAMESPACE --force
```

### If resource constraints:
```bash
# Increase surge capacity
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1-b \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

## Monitor Progress

After applying fixes, monitor the upgrade:

```bash
# Watch node upgrade progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check upgrade operation status
gcloud container operations list --cluster CLUSTER_NAME --zone us-east1-b --limit=1

# Verify no stuck pods
kubectl get pods -A | grep -E "Terminating|Pending"
```

## Get Upgrade Operation Details

```bash
# List recent operations
gcloud container operations list --cluster CLUSTER_NAME --zone us-east1-b --filter="operationType=UPGRADE_NODES"

# Get specific operation details
gcloud container operations describe OPERATION_ID --zone us-east1-b
```

## If Still Stuck After 30 Minutes

1. **Escalate to Google Support** with:
   - Cluster name and zone
   - Operation ID from the commands above
   - PDB configurations that were blocking

2. **Force pod eviction** (use cautiously):
```bash
# Drain specific nodes manually with shorter timeout
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --timeout=300s --force
```

## Prevention for Future Upgrades

```bash
# Review PDB settings before next upgrade
kubectl get pdb -A -o yaml > pdb-backup.yaml

# Configure appropriate surge settings
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1-b \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

**Most likely scenario:** You have a PDB with `minAvailable` set too high (like 100% of replicas) or `maxUnavailable: 0`. The fix is to temporarily relax it to allow 1-2 disruptions, let the upgrade complete, then restore the original PDB settings.

Run the PDB diagnostic first - that's the cause in 90% of stuck upgrades.