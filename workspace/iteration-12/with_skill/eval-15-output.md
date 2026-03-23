# GKE Node Pool Upgrade Recovery

Your cluster is in a partially upgraded state - this is recoverable. Let's diagnose the stuck upgrade and get you back on track.

## Immediate Assessment

**Check current cluster state:**
```bash
# See which nodes are on which versions
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool

# Check operation status and error details
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --filter="operationType=UPGRADE_NODES" \
  --limit=5

# Get the failed operation details
gcloud container operations describe OPERATION_ID \
  --zone ZONE
```

**Version skew check:**
```bash
# Confirm control plane is on 1.32
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"

# Check node pool versions
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE
```

## Common Causes & Fixes

### 1. PDB Blocking Pod Eviction (Most Likely)

**Diagnose:**
```bash
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# Check for pods that can't be evicted
kubectl get pods -A | grep Terminating
```

**Fix - temporarily relax PDB:**
```bash
# Back up the problematic PDB first
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup.yaml

# Temporarily allow more disruptions
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

### 2. Resource Constraints

**Diagnose:**
```bash
kubectl get pods -A | grep Pending
kubectl top nodes
```

**Fix - increase surge capacity:**
```bash
gcloud container node-pools update MAIN_WORKLOAD_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

### 3. Bare Pods Blocking Drain

**Diagnose:**
```bash
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

**Fix:** Delete bare pods (they won't reschedule):
```bash
kubectl delete pod POD_NAME -n NAMESPACE
```

## Resume the Upgrade

Once you've addressed the blocking issue:

```bash
# The upgrade should automatically resume, but you can trigger it manually
gcloud container node-pools upgrade MAIN_WORKLOAD_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

## Post-Recovery Steps

**After the main pool completes:**

1. **Restore original PDBs:**
```bash
kubectl apply -f pdb-backup.yaml
```

2. **Upgrade remaining node pools:**
```bash
gcloud container node-pools upgrade NODE_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

gcloud container node-pools upgrade NODE_POOL_3 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

3. **Validate cluster health:**
```bash
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed
```

## If the Issue Persists

If the upgrade remains stuck after addressing pod-level issues:

1. **Check for admission webhooks:**
```bash
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations
```

2. **Contact GKE support** with:
   - Cluster name and zone
   - Failed operation ID
   - Error message from the operation describe output

The key insight: **GKE node pool upgrades are resumable.** Your 8 upgraded nodes will stay on 1.32, and the upgrade will continue from where it left off once the blocking issue is resolved. You don't need to start over or touch the already-upgraded nodes.