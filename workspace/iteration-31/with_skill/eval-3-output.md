I'll help you diagnose and fix this stuck node pool upgrade. Let's work through the most common causes systematically.

## Immediate Diagnosis Commands

Run these commands to identify what's blocking the drain:

### 1. Check PodDisruptionBudgets (most common cause)
```bash
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# For any PDBs showing 0 allowed disruptions:
kubectl describe pdb PDB_NAME -n NAMESPACE
```

### 2. Check for pods that can't be rescheduled
```bash
# Pending pods (resource constraints)
kubectl get pods -A | grep Pending

# Check scheduling failures
kubectl get events -A --field-selector reason=FailedScheduling --sort-by='.lastTimestamp' | tail -10

# Bare pods (won't be rescheduled)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

### 3. Check resource availability
```bash
kubectl top nodes
kubectl describe nodes | grep -A 5 "Allocated resources"
```

### 4. Check for admission webhook issues
```bash
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations
kubectl get events -A --field-selector type=Warning | grep webhook
```

## Most Likely Fixes

### Fix #1: Temporarily relax overly restrictive PDBs
If you find PDBs with 0 allowed disruptions:
```bash
# Back up the original PDB first
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup-$(date +%s).yaml

# Temporarily allow disruptions
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

### Fix #2: Delete bare pods (if any found)
```bash
# These won't reschedule anyway and just block the drain
kubectl delete pod POD_NAME -n NAMESPACE
```

### Fix #3: Scale down non-critical workloads temporarily
If resource constraints are the issue:
```bash
# Scale down test/dev workloads to free quota
kubectl scale deployment NON_CRITICAL_DEPLOYMENT --replicas=0 -n NAMESPACE
```

### Fix #4: Adjust upgrade settings for resource constraints
```bash
# Reduce surge to use minimal extra quota
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region us-east1 \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Or switch to drain-first (no extra quota needed)
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region us-east1 \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

## Monitor Progress

After applying fixes:
```bash
# Watch node upgrade progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check operation status
gcloud container operations list --cluster CLUSTER_NAME --region us-east1 --limit=1

# Verify no pods are stuck
kubectl get pods -A | grep -E "Terminating|Pending|ContainerCreating"
```

## Restore After Upgrade

Once the upgrade completes:
```bash
# Restore original PDBs
kubectl apply -f pdb-backup-*.yaml

# Scale workloads back up
kubectl scale deployment DEPLOYMENT_NAME --replicas=ORIGINAL_COUNT -n NAMESPACE
```

## If Still Stuck After 30 Minutes

If the upgrade doesn't resume after addressing pod-level issues:
1. Check the GKE operation status for error details
2. Contact Google Cloud Support with cluster name, region, and operation ID
3. The operation may need to be manually resumed by GKE support

**Start with checking PDBs** - that's the #1 cause of stuck drains. Let me know what you find and I can help you with the specific fix!