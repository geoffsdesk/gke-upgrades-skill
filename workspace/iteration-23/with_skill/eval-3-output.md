I'll help you diagnose and fix this stuck node pool upgrade. Let's work through the most common causes systematically.

# Diagnosing Stuck Node Pool Upgrade

## Current State Analysis
- **Cluster**: Standard, us-east1, control plane 1.32
- **Node upgrade**: 3/12 nodes completed, 9 stuck
- **Symptom**: Pods not draining from remaining nodes

Let's diagnose the blockage:

## 1. Check PDBs (Most Common Cause)

```bash
# Check for overly restrictive PDBs
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# Get details on problematic PDBs
kubectl describe pdb PDB_NAME -n NAMESPACE
```

**What to look for**: PDBs showing 0 allowed disruptions. This means drain is blocked because removing any pod would violate the PDB.

**Quick fix**:
```bash
# Temporarily allow more disruptions (back up first)
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup.yaml

# Allow 1 disruption temporarily
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":1}}'
```

## 2. Check Resource Constraints

```bash
# Look for pending pods that can't be scheduled
kubectl get pods -A | grep Pending

# Check scheduling failures
kubectl get events -A --field-selector reason=FailedScheduling --sort-by='.lastTimestamp' | tail -10

# Check node capacity
kubectl top nodes
kubectl describe nodes | grep -A 5 "Allocated resources"
```

**What to look for**: Pods evicted from draining nodes can't be scheduled elsewhere due to insufficient resources.

**Fix**: Reduce maxSurge to create fewer nodes at once:
```bash
# Get current surge settings
gcloud container node-pools describe NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1-b

# Reduce to minimal surge
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

## 3. Check for Bare Pods

```bash
# Find pods without controllers (won't be rescheduled)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

**Fix**: Delete bare pods manually:
```bash
kubectl delete pod POD_NAME -n NAMESPACE
```

## 4. Check Admission Webhooks

```bash
# List webhook configurations
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations

# Check recent webhook failures
kubectl get events -A --field-selector type=Warning | grep webhook
```

**Fix**: Temporarily disable problematic webhooks:
```bash
# Add failure policy to ignore webhook failures
kubectl patch validatingwebhookconfigurations WEBHOOK_NAME \
  -p '{"webhooks":[{"name":"WEBHOOK","failurePolicy":"Ignore"}]}'
```

## 5. Monitor Current Drain Status

```bash
# Check which nodes are cordoned (being drained)
kubectl get nodes | grep SchedulingDisabled

# Watch pod termination events
kubectl get events -A --field-selector reason=Killing,reason=Preempting --sort-by='.lastTimestamp' | tail -20

# Check for long-running terminating pods
kubectl get pods -A | grep Terminating
```

## Immediate Action Plan

1. **First**: Check PDBs - this blocks 80% of stuck drains
2. **Second**: Check for pending pods due to resource constraints
3. **Third**: Look for bare pods that need manual deletion
4. **Monitor**: Watch for progress after each fix

## Recovery Commands

Once you identify the issue:

```bash
# Resume monitoring the upgrade
gcloud container operations list --cluster CLUSTER_NAME --zone us-east1-b --limit=3

# Watch node status
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check upgrade progress
gcloud container node-pools describe NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1-b \
  --format="value(status,version)"
```

## If Still Stuck After 30 Minutes

Contact GKE Support with:
- Cluster name and zone
- Operation ID from `gcloud container operations list`
- Results of the diagnostic commands above

The upgrade should resume within 15-30 minutes after removing the blockage. PDB issues are the most common cause - start there first.

Which diagnostic command should you run first to identify the blockage?