I'll help you diagnose and fix the stuck node pool upgrade. Since your control plane is on 1.32 and only the main workload pool is stuck, we need to identify what's blocking the remaining 12 nodes.

## Immediate Diagnostic Steps

Run these commands to identify the root cause:

```bash
# Check current node status and versions
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool

# Get the stuck upgrade operation details
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES" --limit=5

# Look for pods that can't be evicted (most common cause)
kubectl get pods -A | grep -E "Terminating|Pending"

# Check for PDBs blocking eviction
kubectl get pdb -A -o wide
```

## Most Likely Causes & Fixes

### 1. PDB Blocking Drain (Most Common)
If you see PDBs with `ALLOWED DISRUPTIONS = 0`:

```bash
# Identify problematic PDBs
kubectl get pdb -A -o wide | grep " 0 "

# Temporarily relax the restrictive PDB
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"1"}}'
```

### 2. Resource Constraints
If pods are stuck `Pending` due to insufficient resources:

```bash
# Increase surge capacity to provide more room
gcloud container node-pools update MAIN_WORKLOAD_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

### 3. Bare Pods (Can't Reschedule)
```bash
# Find bare pods (no owner references)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Delete them (they won't reschedule anyway)
kubectl delete pod POD_NAME -n NAMESPACE
```

## Resume the Upgrade

Once you've addressed the blocking issue:

```bash
# The upgrade should automatically resume, but you can retry if needed
gcloud container node-pools upgrade MAIN_WORKLOAD_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

## Handle Your Other Node Pools

**Important:** Don't start the other two pools until the main pool completes. GKE handles one pool at a time for stability.

Once the main pool finishes, upgrade the remaining pools:

```bash
# For each remaining pool
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

## Quick Validation

After addressing the issue:

```bash
# Confirm no stuck operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=3

# Verify workload health
kubectl get pods -A | grep -v Running | grep -v Completed

# Check all nodes eventually reach 1.32
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.nodeInfo.kubeletVersion}{"\n"}{end}'
```

**Next Steps:** Share the output of the diagnostic commands above, and I can provide more specific guidance based on what's actually blocking your upgrade. The most common fix is relaxing a restrictive PDB that's preventing pod eviction.