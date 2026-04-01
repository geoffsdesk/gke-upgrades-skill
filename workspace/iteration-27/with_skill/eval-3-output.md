I'll help you diagnose and fix this stuck node pool upgrade. Let's work through the most common causes systematically.

## Immediate Diagnosis Commands

Run these commands to identify what's blocking the drain:

### 1. Check for PDB violations (most common cause)
```bash
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# Check recent events for PDB violations
kubectl get events -A --field-selector reason=EvictionBlocked --sort-by='.lastTimestamp'
```

### 2. Check for pods that can't be rescheduled
```bash
# Look for Pending pods (can't schedule elsewhere)
kubectl get pods -A | grep Pending

# Check scheduling failures
kubectl get events -A --field-selector reason=FailedScheduling --sort-by='.lastTimestamp'

# Look for bare pods (no controller to reschedule them)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

### 3. Check current drain status
```bash
# See which nodes are being drained
kubectl get nodes -o wide
kubectl describe node NODE_NAME | grep -A 10 "Taints"

# Check pods stuck in Terminating
kubectl get pods -A | grep Terminating
```

## Most Likely Fixes

### Fix 1: PDB is too restrictive
If step 1 shows `ALLOWED DISRUPTIONS = 0`, temporarily relax the PDB:

```bash
# Back up the original PDB first
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup.yaml

# Temporarily allow more disruptions
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'

# Or allow all disruptions temporarily
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"100%"}}'
```

### Fix 2: Resource constraints (pods can't reschedule)
If step 2 shows Pending pods, you need more capacity:

```bash
# Reduce maxSurge to use less extra quota
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region us-east1 \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Alternative: switch to drain-first mode (no extra quota needed)
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region us-east1 \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

### Fix 3: Delete bare pods
If step 2 found bare pods (no ownerReferences), delete them:

```bash
kubectl delete pod POD_NAME -n NAMESPACE --grace-period=0 --force
```

### Fix 4: Long-running jobs blocking drain
If you see pods with very long termination grace periods:

```bash
# Check for long grace periods
kubectl get pods -A -o json | \
  jq '.items[] | select(.spec.terminationGracePeriodSeconds > 300) | {ns:.metadata.namespace, name:.metadata.name, grace:.spec.terminationGracePeriodSeconds}'

# For non-critical long-running jobs, you can force delete
kubectl delete pod POD_NAME -n NAMESPACE --grace-period=0 --force
```

## Monitor Progress

After applying fixes, monitor the upgrade:

```bash
# Watch node upgrade progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check GKE operation status
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --region us-east1 \
  --filter="operationType=UPGRADE_NODES" \
  --limit=1
```

## Emergency Rollback (if needed)

If the upgrade continues to fail and you need to stop it:

```bash
# List current operations
gcloud container operations list --cluster CLUSTER_NAME --region us-east1

# Cancel the upgrade operation (this stops further nodes from upgrading)
gcloud container operations cancel OPERATION_ID --region us-east1
```

## Most Common Resolution Path

Based on your symptoms (nodes not draining), this is likely either:

1. **PDB too restrictive** - Fix 1 above
2. **Resource constraints** - Pods evicted from draining nodes can't reschedule due to insufficient capacity

Run the diagnostic commands in order, and you'll likely find the culprit quickly. The PDB check is the most common cause of exactly this symptom.

Once you identify and fix the root cause, the upgrade should resume automatically within 5-10 minutes. Let me know what the diagnostic commands reveal and I can provide more specific guidance!