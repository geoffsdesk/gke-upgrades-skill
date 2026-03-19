Let me help you diagnose and fix this stuck node pool upgrade. Since your control plane is already on 1.30, we need to get that workload pool completed before moving to the other pools.

## Immediate Diagnosis

Run these commands to identify what's blocking the upgrade:

```bash
# Check current upgrade operation status
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES"

# Look for pods that can't be evicted/rescheduled
kubectl get pods -A | grep -E "Terminating|Pending|Evicted"

# Check for PDB issues (most common cause)
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# Check node status - identify which nodes are old vs new
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool
```

## Most Likely Culprits & Fixes

### 1. PDB Blocking Drain
If you see PDBs with 0 allowed disruptions:

```bash
# Temporarily relax the problematic PDB
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"50%"}}'

# Then resume the upgrade - GKE should auto-continue
```

### 2. Resource Constraints
If pods are pending due to insufficient resources:

```bash
# Increase surge capacity to give more room
gcloud container node-pools update WORKLOAD_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

### 3. Bare Pods or Long Grace Periods
```bash
# Find bare pods (no controller)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Delete them - they won't reschedule anyway
kubectl delete pod POD_NAME -n NAMESPACE

# Check for excessive termination grace periods
kubectl get pods -A -o json | \
  jq '.items[] | select(.spec.terminationGracePeriodSeconds > 300) | {ns:.metadata.namespace, name:.metadata.name, grace:.spec.terminationGracePeriodSeconds}'
```

## Recovery Steps

1. **Fix the blocking issue** using the commands above
2. **Monitor progress** - GKE should automatically resume:
   ```bash
   watch 'kubectl get nodes -L cloud.google.com/gke-nodepool | grep WORKLOAD_POOL_NAME'
   ```

3. **If upgrade doesn't auto-resume after 10-15 minutes**, restart it:
   ```bash
   gcloud container node-pools upgrade WORKLOAD_POOL_NAME \
     --cluster CLUSTER_NAME \
     --zone ZONE \
     --cluster-version 1.30
   ```

## Validation Checklist
Once the workload pool completes:

```
- [ ] All 20 nodes in workload pool show version 1.30: `kubectl get nodes -L cloud.google.com/gke-nodepool`
- [ ] All pods running normally: `kubectl get pods -A | grep -v Running | grep -v Completed`
- [ ] Workloads responding to health checks
- [ ] No stuck operations: `gcloud container operations list --cluster CLUSTER_NAME --zone ZONE`
```

## Next Steps - Other Node Pools

Once your main workload pool is stable, upgrade the remaining two pools **one at a time**:

```bash
# Upgrade second pool
gcloud container node-pools upgrade SECOND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30

# Wait for completion, then third pool
gcloud container node-pools upgrade THIRD_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30
```

**What specific error message are you seeing?** And can you run the first diagnostic command above to show the operation status? That will help me give you the exact fix for your situation.