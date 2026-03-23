# GKE Node Pool Upgrade Stuck - Troubleshooting Guide

Your node pool upgrade is stuck because pods aren't draining from the remaining 9 nodes. Let's diagnose and fix this systematically.

## Immediate Diagnosis Commands

Run these commands in order to identify the root cause:

### 1. Check for PDB blocking drain (most common cause)

```bash
# Look for PodDisruptionBudgets with ALLOWED DISRUPTIONS = 0
kubectl get pdb -A -o wide

# Get details on any restrictive PDBs
kubectl describe pdb PDB_NAME -n NAMESPACE
```

**What to look for:** PDBs showing 0 allowed disruptions are blocking node drain.

### 2. Check for resource constraints

```bash
# Look for pods that can't be scheduled elsewhere
kubectl get pods -A | grep Pending
kubectl get events -A --field-selector reason=FailedScheduling | tail -20

# Check node resource utilization
kubectl top nodes
```

**What to look for:** Pending pods indicate insufficient capacity on upgraded nodes to reschedule workloads.

### 3. Check for bare pods (unmanaged pods)

```bash
# Find pods without owner references (won't be rescheduled)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

**What to look for:** Any pods listed here will prevent node drain and won't reschedule.

### 4. Check current surge settings

```bash
# See your current node pool upgrade configuration
gcloud container node-pools describe NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1-b \
  --format="value(upgradeSettings.maxSurge,upgradeSettings.maxUnavailable)"
```

## Most Likely Fixes

### Fix 1: Temporarily relax PDBs (if step 1 found restrictive PDBs)

```bash
# Back up the current PDB first
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup.yaml

# Temporarily allow all disruptions
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"100%"}}'
```

**Restore after upgrade:** `kubectl apply -f pdb-backup.yaml`

### Fix 2: Increase surge capacity (if step 2 found resource constraints)

```bash
# Increase surge to create more replacement nodes
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-east1-b \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

### Fix 3: Delete bare pods (if step 3 found unmanaged pods)

```bash
# Delete bare pods (they won't reschedule anyway)
kubectl delete pod POD_NAME -n NAMESPACE --force --grace-period=0
```

## Monitor Progress

After applying fixes, monitor the upgrade resuming:

```bash
# Watch node upgrade progress
watch 'kubectl get nodes -o wide | head -15'

# Check for stuck pods
kubectl get pods -A | grep -E "Terminating|Pending"

# Verify upgrade operation is progressing
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --zone us-east1-b \
  --filter="operationType=UPGRADE_NODES" \
  --limit=1
```

## If Still Stuck After 30 Minutes

Check for admission webhooks blocking pod creation:

```bash
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations
kubectl get events -A --field-selector reason=FailedCreate | tail -10
```

## Complete Validation Checklist

Once upgrade completes:

```bash
# All nodes at 1.32
kubectl get nodes -o wide

# All pods running
kubectl get pods -A | grep -v Running | grep -v Completed

# No stuck PDBs
kubectl get pdb -A -o wide
```

## Emergency Escalation

If the upgrade remains stuck after trying these fixes for 1+ hour:

1. Contact Google Cloud Support
2. Provide: cluster name, zone (us-east1-b), node pool name, and current operation ID
3. Include output from the diagnostic commands above

---

**Start with checking PDBs - they cause 80% of stuck node pool upgrades.** Run the first diagnostic command and let me know what you find if you need specific guidance for your PDB configuration.