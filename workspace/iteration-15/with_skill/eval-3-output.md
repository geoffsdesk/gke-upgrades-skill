# Diagnosing Stuck Node Pool Upgrade

Your node pool upgrade is stuck at 3/12 nodes after 2 hours - this is a draining issue. Let's diagnose systematically:

## 1. Check PodDisruptionBudgets (Most Likely Cause)

```bash
# Check for overly restrictive PDBs
kubectl get pdb -A -o wide

# Look for ALLOWED DISRUPTIONS = 0 - this blocks all evictions
kubectl describe pdb -A | grep -A 10 -B 5 "Allowed disruptions: 0"
```

**If you find PDBs with 0 allowed disruptions, temporarily relax them:**

```bash
# Back up the original PDB first
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup.yaml

# Allow some disruptions temporarily
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"33%"}}'
```

## 2. Check Resource Constraints

```bash
# Look for pending pods that can't be rescheduled
kubectl get pods -A | grep Pending

# Check node capacity
kubectl top nodes
kubectl describe nodes | grep -A 5 "Allocated resources"

# Check for scheduling failures
kubectl get events -A --field-selector reason=FailedScheduling --sort-by='.lastTimestamp' | tail -20
```

**If nodes are at capacity, increase surge temporarily:**

```bash
gcloud container node-pools update YOUR_NODE_POOL_NAME \
  --cluster YOUR_CLUSTER_NAME \
  --region us-east1 \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

## 3. Check for Bare Pods (Won't Reschedule)

```bash
# Find pods without ownerReferences (bare pods)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

**Delete bare pods - they won't reschedule anyway:**

```bash
kubectl delete pod POD_NAME -n NAMESPACE
```

## 4. Check Long Termination Grace Periods

```bash
# Find pods with long grace periods
kubectl get pods -A -o json | \
  jq '.items[] | select(.spec.terminationGracePeriodSeconds > 300) | {ns:.metadata.namespace, name:.metadata.name, grace:.spec.terminationGracePeriodSeconds}'
```

GKE only waits 1 hour for pod eviction during surge upgrades. If you have jobs running longer than 1 hour, they'll be force-killed.

## 5. Monitor Current Draining Status

```bash
# Check which nodes are being drained
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool

# Check pods on nodes being upgraded
kubectl get pods -A --field-selector spec.nodeName=NODE_NAME
```

## 6. Check GKE Operation Status

```bash
# Check the upgrade operation details
gcloud container operations list \
  --region us-east1 \
  --cluster YOUR_CLUSTER_NAME \
  --filter="operationType=UPGRADE_NODES" \
  --limit=1

# Get operation details
gcloud container operations describe OPERATION_ID \
  --region us-east1
```

## Quick Resolution Steps

**Most common fix sequence:**

1. **Temporarily relax PDBs** to allow 1-2 disruptions
2. **Delete any bare pods** blocking drain
3. **Scale down non-critical deployments** temporarily if capacity is tight:
   ```bash
   kubectl scale deployment NON_CRITICAL_APP --replicas=0
   ```
4. **Monitor progress:**
   ```bash
   watch 'kubectl get nodes | grep -E "Ready|NotReady" && echo "---" && kubectl get pods -A | grep -E "Terminating|Pending" | wc -l'
   ```

## After Upgrade Completes

- Restore original PDB settings: `kubectl apply -f pdb-backup.yaml`
- Scale back up any deployments you scaled down
- Verify all workloads healthy: `kubectl get pods -A | grep -v Running | grep -v Completed`

The upgrade should resume within 5-10 minutes after resolving the blocking issues. If it's still stuck after fixing pod-level problems, the GKE operation itself may need support intervention.

Which of these checks shows issues in your cluster?