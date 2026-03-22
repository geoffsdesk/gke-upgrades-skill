I'll help you diagnose and fix this stuck node pool upgrade. Let's work through this systematically.

## Immediate Diagnostic Steps

First, let's identify what's blocking the upgrade:

```bash
# Check current operation status
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES"

# Check node status
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool
# Look for nodes in NotReady state or version mismatches

# Check for stuck pods preventing drain
kubectl get pods -A | grep -E "Terminating|Pending|ContainerCreating"

# Check events for specific errors
kubectl get events -A --field-selector reason=FailedScheduling --sort-by='.lastTimestamp' | tail -20
```

## Most Likely Causes & Fixes

### 1. PDB blocking drain (most common)
```bash
# Check for restrictive PDBs
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# If you find blocking PDBs, temporarily relax them:
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

### 2. Resource constraints (no room for pods)
```bash
# Check for pending pods due to resource constraints
kubectl describe pods -A | grep -A 5 "Insufficient cpu\|Insufficient memory"

# If resource constrained, increase surge capacity:
gcloud container node-pools update WORKLOAD_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

### 3. Bare pods blocking drain
```bash
# Find bare pods (not managed by controllers)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Delete bare pods (they won't reschedule anyway)
kubectl delete pod POD_NAME -n NAMESPACE
```

## Resume the Upgrade

Once you've addressed the blocking issue, the upgrade should resume automatically. If not:

```bash
# Check if operation is still running
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=3

# If no active operation, restart the node pool upgrade
gcloud container node-pools upgrade WORKLOAD_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

## Monitor Progress

```bash
# Watch node upgrade progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "NAME|workload-pool"'

# Monitor pod rescheduling
kubectl get pods -A | grep -v Running | grep -v Completed
```

## Next Steps for Other Node Pools

After your main workload pool completes:

1. **Apply lessons learned** - if you had to adjust PDBs or surge settings, do the same for the other pools before upgrading them
2. **Upgrade remaining pools sequentially** to avoid resource contention:
   ```bash
   gcloud container node-pools upgrade POOL_2_NAME --cluster CLUSTER_NAME --zone ZONE --cluster-version 1.32
   # Wait for completion, then:
   gcloud container node-pools upgrade POOL_3_NAME --cluster CLUSTER_NAME --zone ZONE --cluster-version 1.32
   ```

## Validation After Completion

```bash
# Verify all pools at 1.32
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# Check workload health
kubectl get deployments -A
kubectl get pods -A | grep -v Running | grep -v Completed

# Restore original PDBs if you modified them
kubectl apply -f pdb-backup.yaml  # if you backed them up
```

What's the output from the first diagnostic commands? That will help me give you the specific fix for your situation.