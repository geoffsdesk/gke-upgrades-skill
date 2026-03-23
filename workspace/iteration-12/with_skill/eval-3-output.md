# GKE Node Pool Upgrade Troubleshooting

Let me walk you through diagnosing and fixing your stuck upgrade. Since pods aren't draining from the remaining nodes, this is typically a pod-level issue blocking the upgrade process.

## Immediate Diagnosis Steps

Run these commands in order to identify what's blocking the drain:

### 1. Check for PDB issues (most common cause)
```bash
# Look for PDBs with 0 allowed disruptions
kubectl get pdb -A -o wide

# Get detailed info on problematic PDBs
kubectl describe pdb -A | grep -A 10 -B 5 "ALLOWED.*0"
```
**What to look for:** Any PDB showing `ALLOWED DISRUPTIONS: 0`

### 2. Check for pods that can't be evicted
```bash
# Find pending/stuck pods
kubectl get pods -A | grep -E "Pending|Terminating|Evicted"

# Check recent eviction failures
kubectl get events -A --sort-by='.lastTimestamp' | grep -i "evict\|drain\|pdb"
```

### 3. Identify bare pods (can't be rescheduled)
```bash
# Find pods without owner references (bare pods)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

### 4. Check resource constraints
```bash
# See if there's room for rescheduled pods
kubectl top nodes
kubectl get pods -A | grep Pending
kubectl get events -A --field-selector reason=FailedScheduling --sort-by='.lastTimestamp' | tail -10
```

## Most Likely Fixes

Based on your symptoms, here are the fixes in order of likelihood:

### Fix 1: Relax restrictive PDBs temporarily
If you found PDBs with 0 allowed disruptions:

```bash
# Back up the current PDB first
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup-$(date +%s).yaml

# Allow disruptions temporarily (replace PDB_NAME and NAMESPACE)
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

### Fix 2: Delete bare pods
If you found bare pods:
```bash
# Delete them (they won't reschedule anyway)
kubectl delete pod POD_NAME -n NAMESPACE --force
```

### Fix 3: Increase surge capacity
If nodes are resource-constrained:
```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region us-east1 \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

### Fix 4: Check for stuck terminating pods
```bash
# Force delete pods stuck in terminating state
kubectl delete pod POD_NAME -n NAMESPACE --force --grace-period=0
```

## Monitor Progress

After applying fixes, monitor the upgrade:

```bash
# Watch node upgrade progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "Ready|NotReady"'

# Check upgrade operation status
gcloud container operations list --cluster CLUSTER_NAME --region us-east1 --limit=3

# Verify no pods are blocking
kubectl get pods -A | grep -E "Terminating|Pending|Evicted" | wc -l
```

## Expected Timeline

- After fixing pod-level issues, you should see progress within 10-15 minutes
- Each node typically takes 5-10 minutes to drain and replace
- Your remaining 9 nodes should complete in 45-90 minutes total

## Restore Original Settings

After upgrade completes, restore any PDBs you modified:
```bash
# Restore from backup
kubectl apply -f pdb-backup-TIMESTAMP.yaml
```

## If Still Stuck

If no progress after 30 minutes post-fix:
1. Check the GKE operation logs in Cloud Console
2. Look for `UpgradeInfoEvent` notifications in Cloud Logging
3. Contact GKE support with your cluster name, region, and operation ID

**What's the output of the PDB check?** That's the most likely culprit for your drain issue.