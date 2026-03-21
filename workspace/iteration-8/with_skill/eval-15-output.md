I'll help you diagnose and fix the stuck node pool upgrade. Let's work through this systematically.

## Immediate Diagnostic Steps

First, let's understand what's blocking the upgrade:

```bash
# Check current upgrade operation status
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES"

# Look for the specific error message in the operation details
gcloud container operations describe OPERATION_ID --zone ZONE

# Check node status - identify which nodes are upgraded vs stuck
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool

# Look for pods that might be blocking drain
kubectl get pods -A | grep -E "Terminating|Pending|Evicted"
```

## Most Common Causes & Fixes

Work through these in order:

### 1. PDB Blocking Drain (Most Likely)
```bash
# Check for overly restrictive PDBs
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# If you find blocking PDBs, temporarily relax them:
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"100%"}}'
```

### 2. Resource Constraints
```bash
# Check if pending pods can't be scheduled
kubectl get events -A --field-selector reason=FailedScheduling | tail -10

# If resource constrained, increase surge capacity:
gcloud container node-pools update MAIN_WORKLOAD_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

### 3. Bare Pods or Long-Running Jobs
```bash
# Find bare pods (no controller managing them)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Delete bare pods - they won't reschedule anyway
kubectl delete pod POD_NAME -n NAMESPACE
```

## Resume the Upgrade

Once you've cleared the blocking issue:

```bash
# The upgrade should automatically resume, but you can also retry:
gcloud container node-pools upgrade MAIN_WORKLOAD_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

## Next Steps for Remaining Node Pools

After the main workload pool completes:

```bash
# Configure appropriate surge settings for each pool before upgrading
# For stateless workloads:
gcloud container node-pools update NODE_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# Then upgrade
gcloud container node-pools upgrade NODE_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

## If the Operation is Truly Stuck

If clearing pod-level issues doesn't help and the operation shows no progress for >2 hours:

```bash
# Get the operation details for support
gcloud container operations describe OPERATION_ID --zone ZONE --format="yaml" > stuck-operation.yaml
```

Contact GKE support with:
- Cluster name and zone
- Operation ID from the operations list
- The error message from the operation description
- Timeline of when it stopped progressing

## Validation After Fix

```bash
# Confirm all nodes in the pool are upgraded
gcloud container node-pools describe MAIN_WORKLOAD_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --format="value(version)"

# Check workload health
kubectl get pods -A | grep -v Running | grep -v Completed
```

**Key point:** Node pool upgrades can be resumed after fixing blocking issues. You don't need to start over - GKE will continue from where it left off once the obstruction is cleared.

What error message are you seeing in the operation details? That will help me give you the exact fix.