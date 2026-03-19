# GKE Node Pool Upgrade Troubleshooting Guide

**Scenario:** Node pool upgrade stuck at 3/12 nodes completed after 2 hours (v1.29 → v1.30 upgrade, Standard cluster in us-east1)

---

## Overview: Systematic Diagnosis for Stuck Pod Drainage

When GKE node upgrades stall during the drain phase, pods on remaining nodes are unable to be evicted. The most common causes, in order of likelihood, are:

1. **Pod Disruption Budgets (PDBs)** blocking graceful drain
2. **Resource constraints** preventing pod rescheduling
3. **Bare pods** without controllers that cannot be rescheduled
4. **Admission webhooks** rejecting pod creation on updated nodes
5. **PVC attachment issues** preventing pod migration

---

## Step 1: Check Pod Disruption Budgets (Most Common Cause)

Pod Disruption Budgets are the #1 reason for stuck upgrades. A PDB with `minAvailable` or `maxUnavailable` set too conservatively can prevent any pods from being evicted during the upgrade.

### Check for blocking PDBs:

```bash
kubectl get pdb --all-namespaces -o wide
```

**What to look for:**
- Any PDB with `ALLOWED DISRUPTIONS = 0`
- PDBs that match pods on the nodes being upgraded

**Example output that indicates a problem:**
```
NAMESPACE       NAME              MIN AVAILABLE   MAX UNAVAILABLE   ALLOWED DISRUPTIONS   AGE
default         web-app-pdb       3               N/A               0                     45d
production      api-pdb           2               N/A               0                     30d
```

### Identify which pods are blocked:

```bash
# Check which pods match the PDB
kubectl get pods -n <namespace> -o wide --selector <label-selector>

# Example: if your web app uses app=web-app label
kubectl get pods -n default -o wide --selector app=web-app
```

### Identify pods currently on nodes being upgraded:

```bash
# Get the node pool name from your upgrade operation
# Then check which pods are on those nodes:

kubectl get pods -A -o wide | grep -E "<node-name-pattern>"
```

---

## Step 2: Diagnose Resource Constraints

Even if PDBs aren't blocking, capacity issues can prevent pods from being rescheduled to healthy nodes.

### Check for pending pods (resource starvation):

```bash
kubectl get pods -A --field-selector=status.phase=Pending
```

### Check node capacity and allocatable resources:

```bash
kubectl get nodes -o wide
kubectl describe nodes | grep -A 5 "Allocatable"
```

### Check scheduling failures on the upgraded nodes:

```bash
# Look for FailedScheduling events, which indicate pods cannot be scheduled
kubectl get events -A --field-selector reason=FailedScheduling --sort-by='.lastTimestamp' | tail -20
```

**If you see FailedScheduling events:**
- CPU, memory, or GPU resources may be exhausted
- New node image may have different resource allocations
- Taints/tolerations may be preventing pod placement

---

## Step 3: Check for Bare Pods

Bare pods (pods not managed by Deployment, StatefulSet, DaemonSet, etc.) cannot be rescheduled and will block upgrade.

### Identify bare pods on nodes being upgraded:

```bash
# Get bare pods (owned by Node or with no controller)
kubectl get pods -A -o json | jq '.items[] | select(.metadata.ownerReferences | length == 0) | {name: .metadata.name, namespace: .metadata.namespace, node: .spec.nodeName}'
```

**Common places for bare pods:**
- Kubernetes system namespaces (kube-system, kube-node-lease)
- Custom system components

**Fix for bare pods:**
You cannot evict bare pods gracefully. Options:
1. Recreate as Deployment/StatefulSet with proper controllers
2. Manually delete if not critical: `kubectl delete pod <name> -n <namespace>`
3. Use `kubectl drain --delete-emptydir-data --ignore-daemonsets` if pod data loss is acceptable

---

## Step 4: Check Admission Webhooks

Validating or mutating webhooks might be rejecting pod creation on newly upgraded nodes (e.g., due to image validation, security policies, or node taints).

### List all validating webhooks:

```bash
kubectl get validatingwebhookconfigurations -o wide
kubectl get mutatingwebhookconfigurations -o wide
```

### Examine webhook configuration:

```bash
kubectl describe validatingwebhookconfigurations <webhook-name>
```

**What to look for:**
- `rules.apiGroups: ["*"]` with `rules.operations: ["*"]` (overly broad)
- `failurePolicy: Fail` (rejects if webhook is unavailable)
- Selectors that might exclude system namespaces or upgraded nodes

### Check for webhook errors in pod events:

```bash
kubectl describe pod <pod-name> -n <namespace> | grep -A 5 "Events:"
```

**Example error indicating webhook rejection:**
```
Failed      AdmissionWebhook    pod rejected by <webhook-name>
```

---

## Step 5: Check PVC Attachment Issues

Pods using PersistentVolumeClaims may not drain if the PVC is not properly mounted or attached to available nodes.

### Check for volume attachment issues:

```bash
# List all PVCs and their bound status
kubectl get pvc -A

# Check volumeattachment resources
kubectl get volumeattachments -o wide

# Check for stuck attachments
kubectl describe volumeattachment <attachment-name>
```

---

## Recommended Fixes (in order of safety)

### Fix 1: Adjust Restrictive PDBs (Safest)

If PDBs are blocking the upgrade:

**Option A: Temporarily increase maxUnavailable:**
```bash
kubectl patch pdb <pdb-name> -n <namespace> -p '{"spec":{"maxUnavailable":"100%"}}'
```

**Option B: Reduce minAvailable:**
```bash
kubectl patch pdb <pdb-name> -n <namespace> -p '{"spec":{"minAvailable":1}}'
```

**After upgrade completes, restore original PDB values.**

### Fix 2: Increase Node Surge for Faster Drain (Medium Risk)

If using GKE's upgrade operations, increase the surge capability to allow more nodes to upgrade in parallel:

```bash
# Via gcloud (adjust surge-max-unavailable as needed)
gcloud container node-pools update <node-pool-name> \
  --cluster=<cluster-name> \
  --zone=us-east1-b \
  --max-surge-upgrade=5 \
  --max-unavailable-upgrade=3
```

This allows more nodes to be upgraded simultaneously, giving pods more target nodes for rescheduling.

### Fix 3: Resolve Resource Constraints (Medium Risk)

If nodes lack capacity:

```bash
# Scale down non-critical workloads
kubectl scale deployment <deployment-name> --replicas=<lower-count>

# Or add more nodes to the pool
gcloud container node-pools update <node-pool-name> \
  --num-nodes=<increased-count>
```

### Fix 4: Handle Bare Pods (Use with Caution)

**Only if bare pods are blocking and cannot be recreated:**

```bash
# Check what's on the node before deleting
kubectl get pods -n <namespace> --field-selector spec.nodeName=<node-name>

# Force delete bare pod (will lose any in-memory data)
kubectl delete pod <pod-name> -n <namespace> --grace-period=0 --force
```

### Fix 5: Drain Nodes Manually (Last Resort)

```bash
# Cordon the node (prevent new pods from being scheduled)
kubectl cordon <node-name>

# Drain with force (deletes pods not backed by controllers)
kubectl drain <node-name> \
  --ignore-daemonsets \
  --delete-emptydir-data \
  --force \
  --grace-period=30
```

---

## Validation Steps to Confirm Fix is Working

After applying fixes, monitor the upgrade progress:

### Monitor node upgrade status:

```bash
# Watch nodes as they transition through upgrade phases
watch -n 5 'kubectl get nodes --show-labels | grep -E "cloud.google.com/gke-nodepool|cloud.google.com/gke-version"'
```

### Check that pods are draining from remaining nodes:

```bash
# Watch pods being evicted and rescheduled
watch -n 5 'kubectl get pods -A --field-selector=status.phase=Pending | wc -l'
```

### Verify no pods are stuck:

```bash
# Check for pods stuck in Terminating state
kubectl get pods -A --field-selector=status.phase=Terminating
```

If pods remain in Terminating state for >5 minutes, check their finalizers:
```bash
kubectl get pod <pod-name> -n <namespace> -o jsonpath='{.metadata.finalizers}'
```

### Confirm upgrade resuming:

```bash
# Check GKE cluster upgrade status (via gcloud)
gcloud container operations list --filter="status!=DONE" --format="table(name,status,startTime)"

# Or check node versions as they update
kubectl get nodes -o wide | awk '{print $1, $NF}'
```

### Check event log for any remaining errors:

```bash
kubectl get events -A --sort-by='.lastTimestamp' | grep -i "fail\|error\|warning" | tail -20
```

---

## Quick Diagnostic Checklist

Use this checklist when upgrade gets stuck:

- [ ] **PDBs:** Run `kubectl get pdb -A -o wide` → Look for ALLOWED DISRUPTIONS = 0
- [ ] **Pending Pods:** Run `kubectl get pods -A --field-selector=status.phase=Pending` → Check count and reasons
- [ ] **Scheduling Failures:** Run `kubectl get events -A --field-selector reason=FailedScheduling` → Look for capacity errors
- [ ] **Bare Pods:** Run `kubectl get pods -A -o json | jq '.items[] | select(.metadata.ownerReferences | length == 0)'` → Identify non-controller pods
- [ ] **Webhooks:** Run `kubectl get validatingwebhookconfigurations` → Check for overly broad configs
- [ ] **Webhook Errors:** Run `kubectl describe pod <stuck-pod> | grep -i webhook` → Check for rejection logs
- [ ] **PVC Issues:** Run `kubectl get volumeattachments` → Check for stuck attachments
- [ ] **Node Capacity:** Run `kubectl top nodes` → Check CPU/memory availability
- [ ] **Terminating Pods:** Run `kubectl get pods -A --field-selector=status.phase=Terminating` → Check for stuck finalizers

---

## Summary

When a GKE node pool upgrade stalls:

1. **Start with PDBs** (most common culprit) - they prevent any pod eviction if ALLOWED DISRUPTIONS = 0
2. **Check capacity constraints** - pending pods indicate rescheduling failures
3. **Identify bare pods** - they cannot be rescheduled and block upgrades
4. **Review webhooks** - they may reject pods on new nodes
5. **Check PVC attachments** - volume issues prevent pod migration
6. **Apply targeted fixes** - PDB adjustments, surge increases, or forced drains
7. **Validate continuously** - watch nodes and pods to confirm upgrade is progressing

The upgrade should resume within minutes after the root cause is addressed.
