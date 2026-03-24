# Stuck Node Pool Upgrade Diagnosis & Fix

Your node pool upgrade is stuck with pods not draining. Let's diagnose and fix this systematically.

## Immediate Diagnosis

Run these commands to identify the root cause:

### 1. Check PDBs (Most Common Cause)
```bash
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# Get details on blocking PDBs
kubectl get pdb -A -o json | \
  jq '.items[] | select(.status.disruptionsAllowed == 0) | {name: .metadata.name, namespace: .metadata.namespace, minAvailable: .spec.minAvailable, maxUnavailable: .spec.maxUnavailable, currentHealthy: .status.currentHealthy}'
```

### 2. Check for Bare Pods
```bash
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

### 3. Check Resource Constraints
```bash
kubectl get pods -A | grep Pending
kubectl get events -A --field-selector reason=FailedScheduling | tail -10
kubectl top nodes
```

### 4. Check Pods on Old Nodes
```bash
# See which pods are on non-upgraded nodes
kubectl get nodes -o wide | grep 1.31
kubectl get pods -A -o wide --field-selector spec.nodeName=NODE_NAME_HERE
```

## Most Likely Fixes

### Fix 1: Temporarily Relax PDBs (if PDBs are blocking)
```bash
# Back up the problematic PDB first
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup.yaml

# Temporarily allow all disruptions
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"100%"}}'
```

### Fix 2: Delete Bare Pods (if found)
```bash
# Delete bare pods - they won't reschedule anyway
kubectl delete pod POD_NAME -n NAMESPACE
```

### Fix 3: Increase Surge Capacity (if resource-constrained)
```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region us-east1 \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

### Fix 4: Scale Down Non-Critical Workloads
```bash
# Temporarily reduce replicas to free up capacity
kubectl scale deployment NON_CRITICAL_APP --replicas=0 -n NAMESPACE
```

## Monitor Progress After Fix

```bash
# Watch upgrade progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check operation status
gcloud container operations list \
  --region us-east1 \
  --filter="operationType=UPGRADE_NODES" \
  --limit=1

# Verify no stuck pods
kubectl get pods -A | grep -E "Terminating|Pending"
```

## Post-Upgrade Cleanup

Once the upgrade completes:

1. **Restore PDBs** (if you modified them):
```bash
kubectl apply -f pdb-backup.yaml
```

2. **Scale back up** any workloads you scaled down:
```bash
kubectl scale deployment APP_NAME --replicas=ORIGINAL_COUNT -n NAMESPACE
```

## If Still Stuck After 30 Minutes

Contact GKE support with:
- Cluster name and region
- Operation ID from `gcloud container operations list`
- Output from the diagnostic commands above

The most common cause is overly restrictive PDBs. Start there and work through the other checks systematically.