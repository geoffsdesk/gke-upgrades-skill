I'll walk you through diagnosing and fixing your stuck node pool upgrade. Since pods aren't draining, this is likely a PDB, resource constraint, or webhook issue. Let's check systematically:

## Immediate Diagnosis

Run these commands to identify the root cause:

### 1. Check for PDB blocking drain (most common cause)
```bash
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# If you see any with 0 allowed disruptions, get details:
kubectl describe pdb PDB_NAME -n NAMESPACE
```

### 2. Check for resource constraints
```bash
kubectl get pods -A | grep Pending
kubectl get events -A --field-selector reason=FailedScheduling | tail -10
kubectl top nodes
```

### 3. Check for bare pods (won't reschedule)
```bash
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

### 4. Check recent events for drain failures
```bash
kubectl get events -A --sort-by='.lastTimestamp' | tail -20
```

## Most Likely Fixes

**If PDBs are blocking (most common):**
```bash
# Temporarily relax the blocking PDB
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'

# Or if it's a critical service, allow 1 disruption:
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":1}}'
```

**If resource constraints (pods can't reschedule):**
```bash
# Reduce surge to 1 node at a time (uses less quota)
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region us-east1 \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**If bare pods are blocking:**
```bash
# Delete them (they won't reschedule anyway)
kubectl delete pod POD_NAME -n NAMESPACE --force
```

## Monitor Progress

Once you apply a fix:
```bash
# Watch node upgrade progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check for stuck pods
kubectl get pods -A | grep -E "Terminating|Pending"

# Monitor the upgrade operation
gcloud container operations list --cluster CLUSTER_NAME --region us-east1 --limit=1
```

## If Still Stuck After 30 Minutes

The upgrade should resume within 15-30 minutes after fixing the blocking issue. If it doesn't:

1. **Check for admission webhooks blocking pod creation:**
```bash
kubectl get validatingwebhookconfigurations
kubectl get events -A --field-selector reason=FailedCreate | tail -10
```

2. **Look for GKE-level operation issues:**
```bash
gcloud container operations list --cluster CLUSTER_NAME --region us-east1 \
  --filter="operationType=UPGRADE_NODES" --limit=5
```

**What's your cluster and node pool name?** I can give you the exact commands with your details filled in. Also, can you run the PDB check first? That's the #1 cause of stuck drains.

The good news: your cluster is functional with the mixed 1.31/1.32 state. No urgency to force anything - let's identify and fix the root cause properly.