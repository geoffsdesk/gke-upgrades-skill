# GKE Node Pool Upgrade Troubleshooting: Stuck at 3/12 Nodes

## Situation Summary

- **Cluster Mode**: Standard
- **Region**: us-east1
- **Current Version**: 1.29
- **Target Version**: 1.30
- **Status**: Upgrade stuck for 2 hours; 3 out of 12 nodes upgraded
- **Issue**: Pods on remaining nodes are not draining

## Root Cause Analysis

When a node pool upgrade stalls during the drain phase, the most common causes are:

1. **Pod Disruption Budgets (PDBs) blocking drain** — GKE respects PDBs during surge upgrades for up to 1 hour. If a PDB is too restrictive, GKE cannot evict pods and the upgrade pauses.
2. **Pods without controllers** — Bare pods (not managed by Deployment, StatefulSet, DaemonSet, etc.) cannot be rescheduled and will block the drain indefinitely.
3. **Resource constraints** — If the cluster is at capacity and `maxSurge` is set to 0, new pods have nowhere to be scheduled, preventing the old node from draining.
4. **Admission webhooks** — Webhooks rejecting pod creation can prevent rescheduling.
5. **PVC issues** — Pods with PersistentVolumeClaims that can't be attached to new nodes will fail to reschedule.

## Diagnostic Steps

### Step 1: Check Pod Disruption Budgets

PDBs are the #1 reason upgrades get stuck. Run:

```bash
kubectl get pdb --all-namespaces
kubectl describe pdb <PDB_NAME> -n <NAMESPACE>
```

Look for PDBs with very restrictive `minAvailable` or `maxUnavailable` settings. A PDB requiring `minAvailable: 3` on a 2-replica deployment means no pods can be evicted.

**What to look for:**
- `disruptions_allowed: 0` — Pods cannot be evicted right now
- Mismatch between `desired` and `disruptions_allowed` — All pods are protected

### Step 2: Identify Pods Blocking the Drain

Find pods on the nodes that are refusing to drain:

```bash
# Get the names of non-upgraded nodes
kubectl get nodes --sort-by=.metadata.creationTimestamp | grep NotReady

# Or check nodes by version
kubectl get nodes -o wide | grep 1.29

# For each node, see what pods are on it
kubectl get pods --all-namespaces -o wide --field-selector spec.nodeName=<NODE_NAME>
```

Check if any pods:
- Have no owner reference (bare pods)
- Are in `Terminating` state for > 30 seconds (PVC, webhook, or finalizer issue)
- Have `terminationGracePeriodSeconds` set to a very high value

### Step 3: Check for Pods Without Controllers

Bare pods will never be rescheduled and will block node drains:

```bash
kubectl get pods --all-namespaces -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace) \(.metadata.name)"'
```

Any pods found here must be manually deleted or restarted with a controller (e.g., wrapped in a Deployment).

### Step 4: Check Resource Constraints

If the cluster is out of capacity, pods won't reschedule:

```bash
# Check node capacity
kubectl top nodes
kubectl describe nodes | grep -A 5 "Allocated resources"

# Check if any pods are pending
kubectl get pods --all-namespaces | grep Pending

# Check for insufficient resources events
kubectl get events --all-namespaces --field-selector reason=FailedScheduling
```

If pods are pending with `Insufficient cpu` or `Insufficient memory`, either:
- Add temporary surge nodes (increase `maxSurge`)
- Remove or scale down non-critical workloads

### Step 5: Check Surge Upgrade Settings

Verify the node pool's current surge configuration:

```bash
gcloud container node-pools describe <NODE_POOL_NAME> \
  --cluster <CLUSTER_NAME> \
  --zone us-east1-b \
  --format="value(managementConfig.upgradeOptions.maxSurge, managementConfig.upgradeOptions.maxUnavailable)"
```

If both `maxSurge` and `maxUnavailable` are 0, nodes can't drain because there's nowhere for pods to go.

### Step 6: Check for Webhook Issues

Admission webhooks can silently fail during pod rescheduling:

```bash
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations

# Check webhook status and rules
kubectl describe validatingwebhookconfigurations <NAME>

# Check webhook logs in kube-system
kubectl logs -n kube-system -l app=<WEBHOOK_APP> --tail=50
```

Look for rules that match `*` or apply to core API groups.

### Step 7: Check the Upgrade Operation Status

Monitor the actual upgrade progress:

```bash
# Watch node pool upgrade status
gcloud container node-pools describe <NODE_POOL_NAME> \
  --cluster <CLUSTER_NAME> \
  --zone us-east1-b \
  --format="value(managementConfig.upgradeOptions)"

# Check Google Cloud Operations (stackdriver) for drain errors
# or retrieve logs via gcloud
gcloud container operations list --cluster <CLUSTER_NAME> --zone us-east1-b
```

## Fix Procedures

### Fix 1: Address Problematic Pod Disruption Budgets

If a PDB is blocking the upgrade:

**Option A: Temporarily relax the PDB**

```bash
kubectl patch pdb <PDB_NAME> -n <NAMESPACE> -p '{"spec":{"minAvailable":null,"maxUnavailable":100%}}'
```

This allows all pods under the PDB to be evicted. Once the upgrade completes, restore the original PDB.

**Option B: Get the original PDB definition, modify it, and reapply:**

```bash
kubectl get pdb <PDB_NAME> -n <NAMESPACE> -o yaml > pdb-backup.yaml
# Edit pdb-backup.yaml to increase maxUnavailable
kubectl apply -f pdb-backup.yaml
```

### Fix 2: Remove Bare Pods

Bare pods can only be deleted (they won't reschedule):

```bash
# Delete the bare pod (it's gone for good)
kubectl delete pod <POD_NAME> -n <NAMESPACE>

# Consider wrapping critical workloads in a Deployment or StatefulSet
```

### Fix 3: Add Temporary Surge Capacity

If the cluster is out of capacity, add surge nodes:

```bash
gcloud container node-pools update <NODE_POOL_NAME> \
  --cluster <CLUSTER_NAME> \
  --zone us-east1-b \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 1
```

This adds 2 temporary nodes during upgrade, allowing pods to reschedule. After the upgrade completes, surge nodes are automatically removed.

### Fix 4: Scale Down Non-Critical Workloads

If adding surge nodes isn't feasible, free up space by scaling down:

```bash
# Identify and scale down low-priority deployments
kubectl scale deployment <DEPLOYMENT_NAME> -n <NAMESPACE> --replicas=0

# Restore after upgrade
kubectl scale deployment <DEPLOYMENT_NAME> -n <NAMESPACE> --replicas=<ORIGINAL_COUNT>
```

### Fix 5: Fix Webhook Issues

If a webhook is rejecting pod creation:

**Option A: Temporarily disable the webhook**

```bash
kubectl patch validatingwebhookconfigurations <NAME> -p '{"webhooks":[{"name":"<WEBHOOK_NAME>","clientConfig":{"service":null}}]}'
```

Then re-enable after the upgrade.

**Option B: Update the webhook to exclude system namespaces**

Edit the webhook to add a namespace selector that excludes `kube-system` and other critical namespaces.

### Fix 6: Manually Restart the Upgrade

Once issues are resolved, restart the upgrade:

```bash
gcloud container node-pools upgrade <NODE_POOL_NAME> \
  --cluster <CLUSTER_NAME> \
  --zone us-east1-b \
  --cluster-version 1.30
```

GKE will resume draining and upgrading from where it left off.

## Validation Steps After Fix

Once you've applied a fix:

```bash
# Monitor pod drain and node upgrade progress
watch 'kubectl get nodes -o wide | grep -E "NAME|1.29|1.30"'

# Check for any pods still stuck in Terminating
kubectl get pods --all-namespaces | grep Terminating

# Verify no new stuck nodes
kubectl get pods --all-namespaces --field-selector=status.phase=Pending
```

The upgrade should resume and complete within a reasonable time (typically minutes per node, depending on workload size).

## Prevention Checklist for Future Upgrades

- [ ] Review all PDBs before upgrading: `kubectl get pdb --all-namespaces`
- [ ] Ensure no bare pods: verify all pods have ownerReferences
- [ ] Set reasonable `terminationGracePeriodSeconds` (typically 30-60 seconds, not > 300)
- [ ] Configure surge: `maxSurge >= 1`, `maxUnavailable <= 1` for safety
- [ ] Reserve cluster headroom: keep ~20% of nodes unscheduled before upgrades
- [ ] Audit admission webhooks: ensure they don't reject normal pod operations
- [ ] Test PDBs in staging before applying to production
- [ ] Monitor the upgrade: watch nodes and pods during the operation, don't assume it will complete unattended
