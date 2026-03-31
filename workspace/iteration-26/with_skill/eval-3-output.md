# Stuck Node Pool Upgrade Troubleshooting

Your upgrade is stuck because pods aren't draining from the remaining 9 nodes. Let's diagnose this systematically:

## 1. Check PDBs (Most Common Cause)

**Diagnose:**
```bash
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0 or very low numbers
kubectl describe pdb PDB_NAME -n NAMESPACE
```

**What to look for:** PDBs with `ALLOWED DISRUPTIONS: 0` are blocking eviction entirely.

**Fix - temporarily relax overly restrictive PDBs:**
```bash
# Back up the current PDB first
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup-$(date +%Y%m%d).yaml

# Allow more disruptions temporarily
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

## 2. Check for Bare Pods (Can't Be Rescheduled)

**Diagnose:**
```bash
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

**Fix:** Delete bare pods - they won't reschedule anyway:
```bash
kubectl delete pod POD_NAME -n NAMESPACE
```

## 3. Check Resource Constraints

**Diagnose:**
```bash
kubectl get pods -A | grep Pending
kubectl top nodes
kubectl get events -A --field-selector reason=FailedScheduling | tail -10
```

**Fix - if insufficient capacity for rescheduled pods:**
```bash
# Reduce surge parallelism to fit within quota
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region us-east1 \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

## 4. Check Long-Running/Persistent Workloads

**Diagnose:**
```bash
# Check for pods with very long termination grace periods
kubectl get pods -A -o json | \
  jq '.items[] | select(.spec.terminationGracePeriodSeconds > 300) | {ns:.metadata.namespace, name:.metadata.name, grace:.spec.terminationGracePeriodSeconds}'

# Check for pods with safe-to-evict=false annotation
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.annotations."cluster-autoscaler.kubernetes.io/safe-to-evict" == "false") | "\(.metadata.namespace)/\(.metadata.name)"'
```

**Fix:** For batch jobs or pods marked safe-to-evict=false, either:
- Wait for them to complete naturally, or
- Remove the annotation temporarily:
```bash
kubectl annotate pod POD_NAME -n NAMESPACE cluster-autoscaler.kubernetes.io/safe-to-evict-
```

## 5. Check Current Drain Events

**Diagnose what's actually happening:**
```bash
# Check recent drain/eviction events
kubectl get events -A --field-selector reason=Killing --sort-by='.lastTimestamp' | tail -20
kubectl get events -A --field-selector reason=EvictionBlocked --sort-by='.lastTimestamp' | tail -10

# Check which nodes are being drained
kubectl get nodes -o wide | grep SchedulingDisabled
```

## 6. Monitor GKE Operation Status

```bash
# Check upgrade operation details
gcloud container operations list \
  --filter="operationType=UPGRADE_NODES AND status=RUNNING" \
  --region us-east1

# Get detailed operation info
gcloud container operations describe OPERATION_ID --region us-east1
```

## Immediate Resolution Steps

**Step 1:** Start with PDB check (90% of stuck drains)
**Step 2:** If PDBs look OK, check for bare pods and delete them
**Step 3:** Look at recent events to see exactly what's blocking eviction
**Step 4:** Apply the appropriate fix above
**Step 5:** Monitor progress:

```bash
# Watch nodes transition through upgrade
watch 'kubectl get nodes -o wide'

# Monitor pod movements
watch 'kubectl get pods -A | grep -E "Terminating|Pending"'
```

## If Still Stuck After 30 Minutes

Contact GKE support with:
- Cluster name and region
- Node pool name
- Operation ID from the operations list
- Output of the PDB and events commands above

## Post-Fix: Restore Original Configuration

Once the upgrade completes successfully:
```bash
# Restore original PDBs
kubectl apply -f pdb-backup-$(date +%Y%m%d).yaml

# Verify all nodes upgraded
kubectl get nodes -o wide
gcloud container node-pools list --cluster CLUSTER_NAME --region us-east1
```

Start with the PDB check - that's the culprit in most stuck drain scenarios. Let me know what you find!