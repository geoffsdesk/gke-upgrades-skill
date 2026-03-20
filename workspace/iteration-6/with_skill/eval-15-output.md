I'll help you diagnose and fix your stuck node pool upgrade. Since the control plane is already at 1.30 and you're partially through the node upgrade, we need to identify what's blocking the remaining 12 nodes.

## Immediate Diagnostic Steps

Run these commands to identify the issue:

```bash
# Check current operation status
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES"

# Identify which nodes are stuck
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep NODE_POOL_NAME

# Check for pods preventing drain
kubectl get pods -A | grep -v Running | grep -v Completed

# Look for PDB blocking drain (most common cause)
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0
```

## Most Likely Causes & Fixes

### 1. PDB Blocking Drain (90% of stuck upgrades)

If you see PDBs with `ALLOWED DISRUPTIONS = 0`:

```bash
# Identify the blocking PDB
kubectl describe pdb PDB_NAME -n NAMESPACE

# Temporarily relax it
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

### 2. Resource Constraints

If pods are Pending due to insufficient resources:

```bash
# Check for pending pods
kubectl get events -A --field-selector reason=FailedScheduling

# Increase surge capacity temporarily
gcloud container node-pools update MAIN_WORKLOAD_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

### 3. Bare Pods

```bash
# Find bare pods (no owner references)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Delete them (they can't reschedule anyway)
kubectl delete pod POD_NAME -n NAMESPACE
```

## Resume the Upgrade

Once you've cleared the blocking issue:

```bash
# The upgrade should automatically resume, but you can trigger it manually
gcloud container node-pools upgrade MAIN_WORKLOAD_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

## Next Steps for Remaining Pools

After the main pool completes successfully:

1. **Apply lessons learned** - If PDBs were the issue, review their configuration before upgrading the other pools
2. **Stagger the remaining upgrades** - Don't upgrade both remaining pools simultaneously
3. **Use the same fix preemptively** - If you had to relax PDBs, do it before starting the next pool upgrade

## Validation Commands

```bash
# Confirm main pool upgrade completion
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# Check workload health
kubectl get deployments -A
kubectl get pods -A | grep -v Running | grep -v Completed

# Verify no stuck operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=5
```

What error message are you seeing in the GKE console or operation logs? And can you share the output of the PDB check? That will help me give you the exact fix for your specific situation.