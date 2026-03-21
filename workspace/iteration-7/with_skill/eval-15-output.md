I'll help you diagnose and fix this stuck node pool upgrade. Let me walk you through the troubleshooting process systematically.

## Immediate Diagnostic Steps

First, let's identify what's blocking the upgrade:

```bash
# Check current node pool status
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# Get the specific upgrade operation details
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES" --limit=5

# Check for pods that can't be evicted (most common cause)
kubectl get pods -A | grep -E "Terminating|Pending|ContainerCreating"

# Look for PDB violations
kubectl get pdb -A -o wide
```

## Most Likely Causes (in order)

### 1. PDB Blocking Drain
This is the #1 cause of stuck upgrades. Check if any PodDisruptionBudgets are preventing pod eviction:

```bash
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0
kubectl describe pdb PDB_NAME -n NAMESPACE  # for any problematic PDBs
```

**Fix:** Temporarily relax the restrictive PDB:
```bash
# Back up the original PDB first
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup.yaml

# Allow disruptions temporarily
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

### 2. Resource Constraints
If pods can't reschedule due to lack of resources:

```bash
kubectl get events -A --field-selector reason=FailedScheduling | tail -20
kubectl top nodes
```

**Fix:** Increase surge capacity:
```bash
gcloud container node-pools update WORKLOAD_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

### 3. Bare Pods
Pods not managed by controllers can't be rescheduled:

```bash
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

**Fix:** Delete bare pods (they won't reschedule anyway):
```bash
kubectl delete pod POD_NAME -n NAMESPACE
```

## Resume the Upgrade

Once you've fixed the blocking issue, the upgrade should resume automatically within a few minutes. Monitor progress:

```bash
# Watch node upgrade progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Monitor the upgrade operation
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=1
```

## If It's Still Stuck After 30 Minutes

The upgrade operation itself may be in a bad state:

```bash
# Get the operation ID of the stuck upgrade
OPERATION_ID=$(gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES" --limit=1 --format="value(name)")

# Check operation status
gcloud container operations describe $OPERATION_ID --zone ZONE
```

**If the operation is truly stuck:** Contact Google Cloud Support with your cluster name, zone, and operation ID. They can safely restart the upgrade process.

## Plan for Remaining Node Pools

Once your main workload pool completes:

```bash
# Before upgrading the other pools, apply lessons learned
# Check their surge settings
gcloud container node-pools describe POOL_NAME --cluster CLUSTER_NAME --zone ZONE --format="value(upgradeSettings)"

# Configure appropriate surge settings based on workload type
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Then upgrade
gcloud container node-pools upgrade POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.XXXXX  # match your control plane version
```

## Quick Recovery Checklist

- [ ] Check PDBs for `ALLOWED DISRUPTIONS = 0`
- [ ] Look for Pending/Terminating pods 
- [ ] Verify sufficient cluster resources
- [ ] Check for bare pods blocking drain
- [ ] Monitor upgrade operation status
- [ ] If stuck >30min after fixes, contact support with operation ID

What specific error message are you seeing, and what do the PDB and pod status commands show? That will help me give you the exact fix.