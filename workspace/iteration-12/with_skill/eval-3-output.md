# Stuck Node Pool Upgrade Troubleshooting

## Current situation
- **Standard cluster in us-east1, control plane 1.31 → node pools 1.32**
- **3/12 nodes upgraded, 9 nodes stuck**
- **Pods not draining from remaining nodes**

Let's diagnose systematically. Work through these checks in order:

## 1. Check for PDB blocking drain (most common cause)

**Diagnose:**
```bash
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# Check events for eviction failures
kubectl get events -A --field-selector reason=EvictionBlocked --sort-by='.lastTimestamp' | tail -20
```

**What to look for:** PDBs with `ALLOWED DISRUPTIONS: 0` are blocking node drain.

**Fix if found:**
```bash
# Temporarily relax overly restrictive PDBs
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'

# Or allow all disruptions temporarily (restore after upgrade)
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"100%"}}'
```

## 2. Check for resource constraints

**Diagnose:**
```bash
# Look for pending pods that can't be rescheduled
kubectl get pods -A | grep Pending

# Check scheduling failures
kubectl get events -A --field-selector reason=FailedScheduling --sort-by='.lastTimestamp' | tail -10

# Check node resource usage
kubectl top nodes
```

**Fix if found:**
```bash
# Increase surge capacity for faster parallel upgrades
gcloud container node-pools update YOUR_NODE_POOL_NAME \
  --cluster YOUR_CLUSTER_NAME \
  --zone us-east1-a \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

## 3. Check for bare pods (no controller)

**Diagnose:**
```bash
# Find pods without owner references (won't be rescheduled)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

**Fix if found:** Delete bare pods (they can't be rescheduled anyway):
```bash
kubectl delete pod POD_NAME -n NAMESPACE
```

## 4. Check for long termination periods

**Diagnose:**
```bash
# Check for pods with very long grace periods
kubectl get pods -A -o json | \
  jq '.items[] | select(.spec.terminationGracePeriodSeconds > 300) | {ns:.metadata.namespace, name:.metadata.name, grace:.spec.terminationGracePeriodSeconds}'

# Check which pods are currently terminating
kubectl get pods -A | grep Terminating
```

**Context:** GKE waits up to 1 hour for pod eviction during upgrades.

## 5. Check current upgrade operation status

**Diagnose:**
```bash
# Check upgrade operation details
gcloud container operations list \
  --filter="operationType=UPGRADE_NODES AND status=RUNNING" \
  --cluster YOUR_CLUSTER_NAME \
  --zone us-east1-a

# Get specific operation details
gcloud container operations describe OPERATION_ID \
  --zone us-east1-a
```

## Quick diagnosis script

Run this to get a comprehensive view:

```bash
echo "=== PDB Status ==="
kubectl get pdb -A -o wide

echo "=== Pending Pods ==="
kubectl get pods -A | grep Pending

echo "=== Terminating Pods ==="
kubectl get pods -A | grep Terminating

echo "=== Recent Events ==="
kubectl get events -A --sort-by='.lastTimestamp' | tail -20

echo "=== Node Status ==="
kubectl get nodes -o wide

echo "=== Upgrade Operations ==="
gcloud container operations list \
  --filter="operationType=UPGRADE_NODES" \
  --cluster YOUR_CLUSTER_NAME \
  --zone us-east1-a \
  --limit=5
```

## Most likely fix

Based on the symptoms (nodes not draining), **PDBs are the most common culprit**. If you find restrictive PDBs:

1. **Back up current PDB configuration:**
```bash
kubectl get pdb -A -o yaml > pdb-backup-$(date +%Y%m%d).yaml
```

2. **Temporarily relax PDBs:**
```bash
# For each blocking PDB:
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

3. **Monitor upgrade progress:**
```bash
watch 'kubectl get nodes -o wide | grep -E "VERSION|Ready"'
```

4. **Restore PDBs after upgrade completes:**
```bash
kubectl apply -f pdb-backup-$(date +%Y%m%d).yaml
```

## Escalation

If the upgrade remains stuck after resolving pod-level issues for 30+ minutes, contact GKE support with:
- Cluster name and zone
- Current operation ID
- Timeline of when it got stuck

Run the diagnosis script above and share those results. The issue is most likely PDBs blocking drain - fix those first.