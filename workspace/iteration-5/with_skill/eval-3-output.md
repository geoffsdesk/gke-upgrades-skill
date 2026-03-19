# GKE Node Pool Upgrade Troubleshooting

Your node pool upgrade is stuck because pods aren't draining from the remaining 9 nodes. Let's diagnose and fix this systematically.

## Immediate Diagnosis Commands

Run these commands in order to identify the root cause:

### 1. Check for PDB blocking drain (most common cause)
```bash
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# If you see PDBs with 0 allowed disruptions, check which pods they're protecting:
kubectl describe pdb PDB_NAME -n NAMESPACE
```

### 2. Check for resource constraints
```bash
# Look for pending pods that can't be scheduled on the 3 upgraded nodes
kubectl get pods -A | grep Pending
kubectl get events -A --field-selector reason=FailedScheduling --sort-by='.lastTimestamp' | tail -20

# Check if upgraded nodes have capacity
kubectl top nodes
```

### 3. Check for bare pods (can't be rescheduled)
```bash
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

### 4. Check current upgrade operation status
```bash
gcloud container operations list --cluster CLUSTER_NAME --zone us-east1-c --filter="operationType=UPGRADE_NODES" --limit=5

# Check which nodes are being drained
kubectl get nodes -l cloud.google.com/gke-nodepool=NODE_POOL_NAME -o wide
```

## Most Likely Fix: PDB Issue

Based on your symptoms (pods not draining), this is almost certainly a PodDisruptionBudget blocking the drain. Here's how to fix it:

### Temporarily relax the problematic PDB:
```bash
# First, back up the current PDB
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup-$(date +%s).yaml

# Then allow disruptions temporarily
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%","minAvailable":null}}'
```

**Important:** Save the original PDB config and restore it after the upgrade completes.

## If PDB isn't the issue, try these fixes:

### Resource constraints fix:
```bash
# Increase surge capacity to give more room for pod rescheduling
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1-c \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

### Bare pods fix:
```bash
# Delete bare pods (they won't reschedule anyway)
kubectl delete pod POD_NAME -n NAMESPACE --force --grace-period=0
```

### Long termination periods fix:
```bash
# Check for pods with very long termination grace periods
kubectl get pods -A -o json | \
  jq '.items[] | select(.spec.terminationGracePeriodSeconds > 300) | {ns:.metadata.namespace, name:.metadata.name, grace:.spec.terminationGracePeriodSeconds}'

# If found, consider reducing terminationGracePeriodSeconds in the deployment
```

## Monitor Progress

After applying the fix:
```bash
# Watch node upgrade progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "Ready|NotReady|SchedulingDisabled"'

# Monitor pod movement
watch 'kubectl get pods -A | grep -E "Terminating|Pending|ContainerCreating"'

# Check upgrade operation status
gcloud container operations describe OPERATION_ID --zone us-east1-c
```

## If Still Stuck After 30 Minutes

If the upgrade remains stuck after fixing PDBs and pod issues:

1. **Contact GKE Support** with:
   - Cluster name
   - Zone: us-east1-c  
   - Operation ID from the operations list
   - Screenshots of the stuck state

2. **Emergency bypass** (use with caution):
```bash
# Force drain specific nodes if absolutely necessary
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --force --grace-period=0
```

## Prevention for Next Time

```bash
# Configure more conservative surge settings for this workload type
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1-c \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Review and tune PDBs to allow reasonable disruptions (e.g., maxUnavailable: 1 instead of 0)
```

**Start with the PDB check first** - that's the cause of 80% of stuck node pool upgrades. Let me know what you find and I can provide more specific guidance!