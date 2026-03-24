# GKE Node Pool Upgrade Stuck - Troubleshooting Guide

Your upgrade is stuck because pods aren't draining from the old nodes. Let's diagnose and fix this systematically.

## Immediate Diagnosis

Run these commands in order to identify the root cause:

### 1. Check PDBs (Most Common Cause)
```bash
kubectl get pdb -A -o wide
```
Look for `ALLOWED DISRUPTIONS = 0`. If any PDB shows 0 allowed disruptions, that's blocking the drain.

**If PDBs are blocking:**
```bash
# Get details on the problematic PDB
kubectl describe pdb PDB_NAME -n NAMESPACE

# Temporarily relax the PDB to allow drain
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"100%"}}'
```

### 2. Check for Resource Constraints
```bash
kubectl get pods -A | grep Pending
kubectl get events -A --field-selector reason=FailedScheduling --sort-by='.lastTimestamp' | tail -10
kubectl top nodes
```
If pods can't reschedule due to insufficient resources, the old nodes can't drain.

**If resource constrained:**
```bash
# Reduce surge to create fewer nodes at once
gcloud container node-pools update YOUR_NODE_POOL_NAME \
  --cluster YOUR_CLUSTER_NAME \
  --region us-east1 \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### 3. Check for Bare Pods (No Controllers)
```bash
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```
Bare pods can't be rescheduled and must be manually deleted.

**If bare pods exist:**
```bash
kubectl delete pod POD_NAME -n NAMESPACE
```

### 4. Check Pod Eviction Events
```bash
kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' | grep -i evict
```
Look for eviction failures, PDB violations, or webhook rejections.

### 5. Check Current Drain Status
```bash
# See which nodes are cordoned (being drained)
kubectl get nodes | grep SchedulingDisabled

# Check what pods are still running on cordoned nodes
kubectl get pods -A -o wide | grep CORDONED_NODE_NAME
```

## Quick Fixes by Root Cause

### If PDBs are too restrictive:
```bash
# Back up current PDB config
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup.yaml

# Allow more disruptions temporarily
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'

# Restore after upgrade: kubectl apply -f pdb-backup.yaml
```

### If admission webhooks are rejecting pods:
```bash
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations

# Check recent webhook events
kubectl get events -A --field-selector type=Warning | grep webhook
```

### If long-running jobs need more time:
```bash
# Check for pods with long termination grace periods
kubectl get pods -A -o json | \
  jq '.items[] | select(.spec.terminationGracePeriodSeconds > 300) | {ns:.metadata.namespace, name:.metadata.name, grace:.spec.terminationGracePeriodSeconds}'
```

## Monitor Progress After Fix

```bash
# Watch node upgrade progress
watch 'kubectl get nodes -o custom-columns=NAME:.metadata.name,STATUS:.status.conditions[?(@.type==\"Ready\")].status,VERSION:.status.nodeInfo.kubeletVersion'

# Monitor the upgrade operation
gcloud container operations list --cluster YOUR_CLUSTER_NAME --region us-east1 --limit=3
```

## If Still Stuck After 30 Minutes

1. **Check the operation status:**
```bash
gcloud container operations describe OPERATION_ID --region us-east1
```

2. **Force resume if needed:**
```bash
# Cancel and restart the upgrade with more conservative settings
gcloud container node-pools update YOUR_NODE_POOL_NAME \
  --cluster YOUR_CLUSTER_NAME \
  --region us-east1 \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade YOUR_NODE_POOL_NAME \
  --cluster YOUR_CLUSTER_NAME \
  --region us-east1 \
  --cluster-version 1.32
```

## Prevention for Next Time

```bash
# Configure appropriate surge settings before upgrading
gcloud container node-pools update YOUR_NODE_POOL_NAME \
  --cluster YOUR_CLUSTER_NAME \
  --region us-east1 \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

**Start with the PDB check** - that's the cause in 80% of stuck upgrades. Once you identify and fix the blocking issue, the upgrade should resume automatically within 10-15 minutes.

What do you see when you run the PDB check?