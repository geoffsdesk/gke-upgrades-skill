I'll walk you through diagnosing and fixing your stuck node pool upgrade. Let's work through the most common causes systematically.

## Immediate Diagnosis Commands

Run these commands in order to identify what's blocking the drain:

### 1. Check for PDB blocking drain (most common cause)
```bash
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# If you see any with 0 disruptions, check details:
kubectl describe pdb PDB_NAME -n NAMESPACE
```

### 2. Check for pending/stuck pods
```bash
kubectl get pods -A | grep -E "Terminating|Pending"
kubectl get events -A --field-selector reason=FailedScheduling | tail -20
```

### 3. Check for bare pods (common culprit)
```bash
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

### 4. Check resource constraints
```bash
kubectl top nodes
kubectl describe nodes | grep -A 5 "Allocated resources"
```

## Most Likely Fixes

Based on your symptoms, here are the fixes in order of likelihood:

### Fix #1: Temporarily relax overly restrictive PDBs
If you found PDBs with 0 allowed disruptions:
```bash
# Back up the original PDB first
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup.yaml

# Temporarily allow disruptions
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

### Fix #2: Delete bare pods
If you found bare pods (no owner references):
```bash
# These won't be rescheduled anyway, safe to delete
kubectl delete pod POD_NAME -n NAMESPACE --force --grace-period=0
```

### Fix #3: Increase surge capacity
If nodes are resource-constrained:
```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1-b \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

### Fix #4: Force drain stuck nodes
If specific nodes are stuck, you can manually drain them:
```bash
# Find which nodes are being upgraded
kubectl get nodes -o wide | grep -E "1.29|1.30"

# Manually drain the stuck node (replace NODE_NAME)
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --force --grace-period=0
```

## Monitor Progress
After applying fixes:
```bash
# Watch upgrade progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check GKE operation status
gcloud container operations list --cluster CLUSTER_NAME --zone us-east1-b --limit=3
```

## If Still Stuck After 30 Minutes

Check for admission webhooks blocking pod creation:
```bash
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations
kubectl get events -A --field-selector reason=FailedCreate | tail -10
```

## Restore After Upgrade Completes

Don't forget to restore your original PDBs:
```bash
kubectl apply -f pdb-backup.yaml
```

## Emergency Escalation

If none of these fixes work and the upgrade remains stuck after another hour, contact GKE support with:
- Cluster name and zone
- Operation ID from `gcloud container operations list`
- Output from the diagnostic commands above

**Start with checking PDBs and bare pods** - these cause 80% of stuck drain issues. Let me know what you find and I can provide more specific guidance!