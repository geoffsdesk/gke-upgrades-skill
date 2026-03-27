I'll help you diagnose and fix your stuck node pool upgrade. Let's work through the most common causes systematically.

## Immediate Diagnostic Steps

Run these commands to identify what's blocking the drain:

### 1. Check for PDB violations (most common cause)
```bash
# Look for PDBs with zero allowed disruptions
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# Check recent events for PDB blocks
kubectl get events -A --field-selector reason=EvictionBlocked --sort-by='.lastTimestamp'
```

### 2. Check for resource constraints
```bash
# Look for pending pods (can't reschedule due to lack of capacity)
kubectl get pods -A | grep Pending

# Check node resource utilization
kubectl top nodes
kubectl describe nodes | grep -A 5 "Allocated resources"
```

### 3. Check for bare pods (won't reschedule)
```bash
# Find pods without owner references
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

### 4. Check for admission webhook issues
```bash
# Look for webhook rejections in events
kubectl get events -A --field-selector type=Warning | grep webhook

# List webhook configurations
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations
```

## Most Likely Fixes

### Fix #1: PDB blocking drain (90% of cases)
If you see PDBs with 0 allowed disruptions:

```bash
# Temporarily relax the problematic PDB
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"100%"}}'

# Or back up and edit
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup.yaml
# Edit minAvailable/maxUnavailable to allow at least 1 disruption
kubectl apply -f pdb-backup.yaml
```

### Fix #2: Resource constraints
If pods are pending due to insufficient capacity:

```bash
# Reduce maxSurge to use less extra capacity
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region us-east1 \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Or temporarily scale down non-critical workloads
kubectl scale deployment NON_CRITICAL_DEPLOYMENT --replicas=0
```

### Fix #3: Delete bare pods
If you found bare pods:
```bash
# These won't reschedule anyway, safe to delete
kubectl delete pod POD_NAME -n NAMESPACE
```

## Monitor Progress After Fix

```bash
# Watch node upgrade progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check for stuck pods
kubectl get pods -A | grep -E "Terminating|Pending"

# Monitor upgrade operation
gcloud container operations list --cluster CLUSTER_NAME --region us-east1 --limit=1
```

## If Still Stuck After 30 Minutes

Check the GKE operation status:
```bash
gcloud container operations describe OPERATION_ID --region us-east1
```

If the operation shows no progress after resolving pod-level issues, you may need to contact Google Cloud Support with:
- Cluster name
- Region (us-east1)  
- Operation ID
- Timeline of what you've tried

## Prevention for Future Upgrades

1. **Review PDBs before upgrading**: Ensure they're not overly restrictive
2. **Use percentage-based maxSurge**: `maxSurge=5%` of pool size scales better than fixed numbers
3. **Schedule during off-peak hours**: More capacity available for surge nodes
4. **Test in staging first**: Validate PDB settings and resource constraints

Start with checking PDBs - that's the cause in 90% of stuck upgrades. Let me know what you find and I can help with the specific fix!