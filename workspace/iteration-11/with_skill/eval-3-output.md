I'll help you diagnose and fix this stuck node pool upgrade. Let's work through the most common causes systematically.

## Immediate Diagnosis Commands

Run these commands to identify what's blocking the drain:

### 1. Check for PDB blocking drain (most common cause)
```bash
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

kubectl describe pdb PDB_NAME -n NAMESPACE
# Check which pods are preventing disruption
```

### 2. Check for pods that can't be scheduled elsewhere
```bash
kubectl get pods -A | grep Pending
kubectl get events -A --field-selector reason=FailedScheduling | tail -20
```

### 3. Look for bare pods (won't reschedule)
```bash
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

### 4. Check resource availability on upgraded nodes
```bash
kubectl top nodes
kubectl describe nodes | grep -A 5 "Allocated resources"
```

## Most Likely Fixes

### Fix 1: Temporarily relax overly restrictive PDBs
If PDBs show `ALLOWED DISRUPTIONS = 0`:

```bash
# Back up current PDB first
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup.yaml

# Temporarily allow more disruptions
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

### Fix 2: Increase surge capacity if resource-constrained
If pods are Pending due to insufficient resources:

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region us-east1 \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

### Fix 3: Delete bare pods
If you found bare pods (they can't reschedule anyway):

```bash
kubectl delete pod POD_NAME -n NAMESPACE --grace-period=0 --force
```

## Monitor Progress

```bash
# Watch node upgrade status
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check upgrade operation
gcloud container operations list --cluster CLUSTER_NAME --region us-east1 --limit=1
```

## Complete Troubleshooting Runbook

If the above doesn't resolve it, here's the full diagnostic sequence:

```bash
# 1. Current upgrade status
gcloud container operations list --cluster CLUSTER_NAME --region us-east1 --filter="operationType=UPGRADE_NODES"

# 2. Pod eviction events
kubectl get events -A --field-selector reason=Killing,reason=Preempting | tail -20

# 3. Check for admission webhooks blocking pod creation
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations

# 4. PVC attachment issues
kubectl get pvc -A | grep -v Bound
kubectl get events -A --field-selector reason=FailedAttachVolume

# 5. Long termination grace periods
kubectl get pods -A -o json | \
  jq '.items[] | select(.spec.terminationGracePeriodSeconds > 120) | {ns:.metadata.namespace, name:.metadata.name, grace:.spec.terminationGracePeriodSeconds}'
```

## What to try first

1. **Check PDBs** - This is the #1 cause of stuck drains
2. **Look for bare pods** - Delete them (they won't reschedule anyway)
3. **Increase surge if resource-constrained** - More nodes = more room for pods

Run the PDB check first and let me know what you find. In most cases, overly restrictive PDBs (`minAvailable: 100%` or `maxUnavailable: 0`) are the culprit.

After you resolve the blocking issue, the upgrade should resume automatically within a few minutes. If it's still stuck after 30 minutes with no pod-level issues, that indicates a GKE-level problem requiring support.