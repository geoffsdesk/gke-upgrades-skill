# GKE Node Pool Upgrade Stuck - Diagnostic & Fix

Your node pool upgrade is stuck with pods not draining from the remaining nodes. Let's diagnose systematically and get this moving.

## Immediate Diagnosis Commands

Run these in order to identify the root cause:

### 1. Check PDB blocking drain (most likely cause)
```bash
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# Check recent eviction events
kubectl get events -A --field-selector reason=Evicted,type=Warning --sort-by='.lastTimestamp' | tail -10

# Check for PDB violations in events
kubectl get events -A | grep -i "pdb\|disruption"
```

### 2. Check for bare pods (can't be rescheduled)
```bash
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

### 3. Check resource constraints
```bash
kubectl get pods -A | grep Pending
kubectl top nodes
kubectl describe nodes | grep -A 5 "Allocated resources"
```

### 4. Check for problematic termination grace periods
```bash
kubectl get pods -A -o json | \
  jq '.items[] | select(.spec.terminationGracePeriodSeconds > 300) | {ns:.metadata.namespace, name:.metadata.name, grace:.spec.terminationGracePeriodSeconds}'
```

## Likely Fixes Based on Common Causes

### Fix 1: PDB Too Restrictive (80% of cases)
If you found PDBs with 0 allowed disruptions:

```bash
# Temporarily relax the most restrictive PDBs
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"1"}}'

# Or allow more disruptions
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"minAvailable":1}}'  # instead of higher number
```

### Fix 2: Delete Bare Pods
If bare pods exist (they won't reschedule anyway):
```bash
kubectl delete pod POD_NAME -n NAMESPACE --grace-period=30
```

### Fix 3: Resource Constraints
If nodes are full and pods can't reschedule:
```bash
# Option A: Reduce maxSurge to limit concurrent upgrades
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region us-east1 \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Option B: Scale down non-critical workloads temporarily
kubectl scale deployment NON_CRITICAL_APP --replicas=0 -n NAMESPACE
```

### Fix 4: Long Grace Periods
For pods with long termination periods:
```bash
# Force drain the stuck nodes (if safe to do so)
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --force --grace-period=60
```

## Monitor Recovery

After applying fixes:
```bash
# Watch upgrade progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Monitor pod movements
kubectl get pods -A | grep -E "Terminating|Pending|ContainerCreating"

# Check upgrade operation status
gcloud container operations list --cluster CLUSTER_NAME --region us-east1 --limit=1
```

## If Still Stuck After 30 Minutes

Check for admission webhooks blocking pod creation:
```bash
kubectl get validatingwebhookconfigurations
kubectl get events -A --field-selector reason=FailedCreate,type=Warning
```

If webhooks are the issue, temporarily set failure policy to "Ignore":
```bash
kubectl patch validatingwebhookconfigurations WEBHOOK_NAME \
  -p '{"webhooks":[{"name":"WEBHOOK_NAME","failurePolicy":"Ignore"}]}'
```

## Nuclear Option (if nothing else works)

If the upgrade is completely stuck and none of the above resolves it:

1. **Cancel the current upgrade** (it will finish the current node and stop):
```bash
# List operations to find the upgrade operation ID
gcloud container operations list --cluster CLUSTER_NAME --region us-east1

# The upgrade will stop after the current node completes
```

2. **Create a new node pool** with the target version and migrate workloads manually:
```bash
gcloud container node-pools create NEW_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region us-east1 \
  --node-version 1.32.x-gke.xxxx \
  --num-nodes 3 \
  --machine-type YOUR_MACHINE_TYPE
```

## Root Cause Prevention

After recovery, implement these to prevent future stuck upgrades:

1. **Review PDB settings** - ensure they allow at least 1 disruption
2. **Set appropriate termination grace periods** (≤5 minutes for most apps)
3. **Eliminate bare pods** - wrap in Deployments
4. **Test upgrades in staging** with the same PDB configuration

Run the diagnostics above and let me know what you find. The most likely culprit is a PDB with `minAvailable` set too high or `maxUnavailable` set too low.