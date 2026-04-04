Let me walk you through diagnosing and fixing this stuck node pool upgrade. Since pods aren't draining, this is likely a pod-level blocking issue.

## Immediate Diagnosis

Run these commands to identify what's blocking the drain:

```bash
# 1. Check for overly restrictive PDBs (most common cause)
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# 2. Check for pending/stuck pods
kubectl get pods -A | grep -E "Pending|Terminating"
kubectl get events -A --field-selector reason=FailedScheduling --sort-by='.lastTimestamp' | tail -10

# 3. Check for bare pods (won't be rescheduled)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# 4. Check resource pressure
kubectl top nodes
kubectl describe nodes | grep -A 5 "Allocated resources"
```

## Most Likely Fixes

### Fix 1: PDB Blocking Drain
If you see PDBs with `ALLOWED DISRUPTIONS = 0`:

```bash
# Identify the problematic PDB
kubectl describe pdb PDB_NAME -n NAMESPACE

# Temporarily relax it
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

### Fix 2: Resource Constraints
If pods are Pending due to insufficient resources:

```bash
# Reduce concurrent surge nodes to fit within quota
gcloud container node-pools update YOUR_NODE_POOL_NAME \
  --cluster YOUR_CLUSTER_NAME \
  --region us-east1 \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### Fix 3: Delete Bare Pods
If you found bare pods (no controllers):

```bash
# Delete them (they won't reschedule anyway)
kubectl delete pod POD_NAME -n NAMESPACE
```

## Monitor Progress

After applying fixes, monitor the upgrade:

```bash
# Watch node versions change
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Monitor the GKE operation
gcloud container operations list --cluster YOUR_CLUSTER_NAME --region us-east1 --filter="operationType=UPGRADE_NODES"
```

## Recovery Options

**If the upgrade resumes:** Great! Let it complete naturally.

**If still stuck after 30 minutes:** You have two options:

1. **Retry (recommended):** Fix the root cause and the upgrade will continue
2. **Accept mixed state:** The cluster is functional with 3 nodes at 1.32 and 9 at 1.31 (within supported version skew)

## Escalation

If none of these fixes work after 30 minutes, contact GKE support with:
- Cluster name and region
- Operation ID from the operations list command
- Output from the diagnostic commands above

Would you like me to help you interpret the output from any of these diagnostic commands?