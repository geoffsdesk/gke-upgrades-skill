# GKE Node Pool Upgrade Troubleshooting
## Stuck Upgrade: 3/12 Nodes Upgraded, Pods Not Draining

**Cluster Details:**
- Mode: Standard
- Region: us-east1
- Current Node Version: 1.29
- Target Node Version: 1.30
- Status: 3 out of 12 nodes upgraded (2+ hours stuck)
- Issue: Remaining nodes not draining pods

---

## Diagnostic Workflow

Work through these checks **in order** to identify why pods aren't draining. Each has a diagnosis command and fix.

### 1. PDB (Pod Disruption Budget) Blocking Drain — **Most Common Cause**

Pod Disruption Budgets prevent Kubernetes from evicting pods during maintenance. If a PDB has `minAvailable` set too high or `maxUnavailable=0`, it will block node drains.

**Diagnose:**
```bash
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0 (these are blocking drains)

kubectl describe pdb PDB_NAME -n NAMESPACE
# Check minAvailable and maxUnavailable values
```

**What to look for:**
- Any PDB with `ALLOWED DISRUPTIONS: 0` — this is blocking the upgrade
- `minAvailable` set to equal or greater than the current replica count

**Fix — Temporarily relax the PDB:**
```bash
# Option A: Allow all disruptions temporarily (fastest)
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"100%"}}'

# Option B: Reduce minAvailable
# First, back up the original
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup.yaml

# Edit the YAML to reduce minAvailable or set maxUnavailable: "100%"
nano pdb-backup.yaml

# Apply the updated version
kubectl apply -f pdb-backup.yaml
```

**After upgrade completes:** Restore the original PDB from your backup:
```bash
kubectl apply -f pdb-backup.yaml
```

---

### 2. Resource Constraints — Pending Pods, No Room to Reschedule

During a surge upgrade, GKE temporarily over-provisions nodes. If the pool is resource-constrained, new pods can't schedule, blocking the drain of old pods.

**Diagnose:**
```bash
# Check for pending pods
kubectl get pods -A | grep Pending

# Check scheduling failures
kubectl get events -A --field-selector reason=FailedScheduling

# View node resource utilization
kubectl top nodes

# See allocated vs available resources
kubectl describe nodes | grep -A 5 "Allocated resources"
```

**What to look for:**
- Pods stuck in `Pending` state on non-upgraded nodes
- Events showing `FailedScheduling` with "insufficient" errors (CPU, memory, etc.)
- Nodes with >80% resource usage

**Fix — Increase surge capacity:**
```bash
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone us-east1-c \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

This allows up to 3 temporary extra nodes during upgrade, giving rescheduled pods more room.

**Alternative:** Scale down non-critical workloads temporarily:
```bash
kubectl scale deployment NAME --replicas=0 -n NAMESPACE
# Resume after upgrade:
kubectl scale deployment NAME --replicas=N -n NAMESPACE
```

---

### 3. Bare Pods Blocking Drain

Bare pods (pods not owned by a Deployment, StatefulSet, DaemonSet, etc.) can't be rescheduled. They will never drain and will block node upgrades indefinitely.

**Diagnose:**
```bash
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

**What to look for:**
- List of pods with no owner (typical output: `namespace/pod-name`)
- These pods are typically temporary or debug pods

**Fix — Delete bare pods:**
```bash
# Delete individual bare pod
kubectl delete pod POD_NAME -n NAMESPACE

# Or delete all bare pods (use with caution!)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"' | \
  while read ns pod; do kubectl delete pod "$pod" -n "$ns"; done
```

Alternative: Wrap bare pods in a Deployment for automatic rescheduling.

---

### 4. Admission Webhooks Rejecting New Pod Creation

If a validating or mutating webhook has a broad scope and rejects pod creation, pods can't reschedule to other nodes, blocking drain.

**Diagnose:**
```bash
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations

# Describe a specific webhook to see its rules
kubectl describe validatingwebhookconfigurations WEBHOOK_NAME
```

**What to look for:**
- Webhooks that match broad API groups (e.g., `*` or `apps/*`)
- Rules with `apiVersions: ["*"]` or similar broad matchers
- Webhook failure policies set to `Fail` (instead of `Ignore`)

**Fix — Temporarily disable problematic webhook:**
```bash
# List the webhook and capture its YAML
kubectl get validatingwebhookconfigurations WEBHOOK_NAME -o yaml > webhook-backup.yaml

# Delete it during upgrade (it will prevent pod scheduling)
kubectl delete validatingwebhookconfigurations WEBHOOK_NAME

# After upgrade, restore it:
kubectl apply -f webhook-backup.yaml
```

---

### 5. PVC (Persistent Volume Claim) Attachment Issues

If pods with persistent volumes can't migrate to upgraded nodes (e.g., volume is zone-locked), they'll block drain.

**Diagnose:**
```bash
# Check for unbound PVCs
kubectl get pvc -A | grep -v Bound

# Check for volume attachment failures
kubectl get events -A --field-selector reason=FailedAttachVolume
kubectl get events -A --field-selector reason=FailedMount
```

**What to look for:**
- PVCs showing `Pending` instead of `Bound`
- Events mentioning `FailedAttachVolume` or `FailedMount`
- Nodes in different zones (zone-locked volumes can't migrate)

**Fix — Migrate workloads:**
```bash
# For zone-locked volumes, manually move pods to already-upgraded nodes
kubectl cordon NODE_NAME  # Prevent new pods on old node
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data

# Or increase maxSurge to allow temporary volume duplication
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone us-east1-c \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

---

### 6. Long Termination Grace Periods

Pods with very long `terminationGracePeriodSeconds` (>300s) can delay node draining significantly.

**Diagnose:**
```bash
kubectl get pods -A -o json | \
  jq '.items[] | select(.spec.terminationGracePeriodSeconds > 120) | {ns:.metadata.namespace, name:.metadata.name, grace:.spec.terminationGracePeriodSeconds}'
```

**What to look for:**
- Pods with grace periods >300 seconds (5 minutes)
- These are often database pods or batch jobs

**Fix — Reduce grace period if possible:**
```bash
# Patch the deployment/statefulset
kubectl patch deployment NAME -n NAMESPACE \
  -p '{"spec":{"template":{"spec":{"terminationGracePeriodSeconds":60}}}}'
```

GKE allows up to 1 hour for graceful termination during surge upgrades, so reducing excessively long periods can help.

---

### 7. Upgrade Operation Stuck at GKE Level

If you've fixed all pod-level issues but the operation still shows no progress, the problem is at the GKE infrastructure level.

**Diagnose:**
```bash
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --zone us-east1-c \
  --filter="operationType=UPGRADE_NODES"
```

**What to look for:**
- Operation status and timestamps
- Whether progress has changed in the last 30 minutes
- Operation warnings or errors

**Fix:** If stuck for >2 hours after resolving pod issues, contact GKE support with:
- Cluster name
- Zone
- Operation ID
- Steps you've already taken

---

## Recommended Diagnostic Sequence for Your Situation

Since your upgrade is stuck with 3/12 nodes upgraded and pods not draining, run these in order:

```bash
# Step 1: Check PDBs (most common culprit)
kubectl get pdb -A -o wide

# Step 2: Check for pending pods
kubectl get pods -A | grep Pending

# Step 3: Check scheduling events
kubectl get events -A --field-selector reason=FailedScheduling | head -20

# Step 4: Check for bare pods
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"' | head -20

# Step 5: Check webhooks
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations

# Step 6: Monitor node status
kubectl get nodes -o wide | grep -E "NAME|1.29|1.30"
```

**Expected output format for nodes:**
- Upgraded nodes should show version `1.30.x`
- Stuck nodes should show version `1.29.x` with status `Ready` or `NotReady`

---

## Validation After Applying a Fix

Once you've identified and fixed the issue, monitor the upgrade progress:

```bash
# Watch node upgrade progress (updates every 2 seconds)
watch 'kubectl get nodes -o wide | grep -E "NAME|VERSION|STATUS"'

# Check for pods still terminating or pending
kubectl get pods -A | grep -E "Terminating|Pending"

# Confirm the operation is progressing
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --zone us-east1-c \
  --limit=1 \
  --filter="operationType=UPGRADE_NODES"
```

**Expected progress:** After fix, nodes should upgrade at a rate of ~1-2 nodes per 5-10 minutes.

---

## Quick Reference: Most Likely Fixes

| Issue | Command |
|-------|---------|
| **PDB blocking drain** | `kubectl patch pdb PDB_NAME -n NAMESPACE -p '{"spec":{"minAvailable":null,"maxUnavailable":"100%"}}'` |
| **Need more capacity** | `gcloud container node-pools update default-pool --cluster CLUSTER_NAME --zone us-east1-c --max-surge-upgrade 3 --max-unavailable-upgrade 0` |
| **Bare pods stuck** | `kubectl delete pod POD_NAME -n NAMESPACE` |
| **Webhook blocking** | `kubectl delete validatingwebhookconfigurations WEBHOOK_NAME` |

---

## Next Steps

1. **Run diagnostic sequence above** — identify the specific cause
2. **Apply the corresponding fix** — start with PDB check (most common)
3. **Monitor upgrade progress** — watch should show nodes upgrading within 5 minutes
4. **Restore settings after upgrade** — re-apply PDBs, webhooks, increase replicas
5. **Contact GKE support** if stuck >2 hours after fixing pod-level issues
