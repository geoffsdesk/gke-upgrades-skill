# GKE Upgrade Runbook: 1.32 → 1.33

**Cluster:** Standard | **Channel:** Regular | **Zone:** us-west1-b  
**Current:** 1.32 → **Target:** 1.33

This runbook provides complete step-by-step instructions for your first GKE upgrade. Follow each section in order.

## Pre-flight Checks (30 minutes)

### Step 1: Verify current cluster state

```bash
# Get current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Expected output: Control plane and both pools at 1.32.x
```

### Step 2: Check if 1.33 is available in Regular channel

```bash
# Check available versions
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels.REGULAR.validVersions)"

# Look for versions starting with "1.33" in the output
```

### Step 3: Check for deprecated APIs (critical!)

```bash
# This is the #1 cause of upgrade failures
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# If you see any output, you have deprecated API usage that must be fixed first
# No output = you're good to proceed
```

### Step 4: Verify cluster health

```bash
# All nodes should be Ready
kubectl get nodes

# No pods should be stuck
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded

# Check system components
kubectl get pods -n kube-system
```

### Step 5: Review workload protection

```bash
# Check for PodDisruptionBudgets
kubectl get pdb -A -o wide

# Important: ALLOWED DISRUPTIONS should not be 0 for all PDBs
# If any show 0 disruptions allowed, note them for potential adjustment
```

## Phase 1: Control Plane Upgrade (15-20 minutes)

The control plane must be upgraded before node pools. This is a GKE requirement.

### Step 1: Start control plane upgrade

```bash
# Replace CLUSTER_NAME with your actual cluster name
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version 1.33

# You'll see: "Do you want to continue (Y/n)?" → Type 'Y' and press Enter
```

**What happens:** GKE upgrades the control plane (API server). Your workloads keep running, but you temporarily can't deploy new workloads or change cluster config.

### Step 2: Monitor control plane upgrade

```bash
# Check upgrade progress (run every 2-3 minutes)
gcloud container operations list --zone us-west1-b --filter="operationType=UPGRADE_MASTER" --limit=1

# When STATUS changes to DONE, proceed to next step
```

### Step 3: Verify control plane upgrade

```bash
# Control plane should now show 1.33.x
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"

# System pods should be healthy
kubectl get pods -n kube-system
```

## Phase 2: Node Pool Upgrades (30-60 minutes each)

Now upgrade each node pool. GKE will create new nodes with 1.33, drain old nodes, then delete them.

### Configure surge settings (recommended for safety)

```bash
# Set conservative surge for both pools
# maxSurge=1: Creates 1 extra node at a time
# maxUnavailable=0: No nodes unavailable during upgrade

gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

gcloud container node-pools update workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### Upgrade default-pool first

```bash
# Start node pool upgrade
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33

# You'll see: "Do you want to continue (Y/n)?" → Type 'Y' and press Enter
```

### Monitor default-pool upgrade

```bash
# Watch nodes being replaced (run this in a separate terminal)
watch 'kubectl get nodes -o wide'

# You'll see:
# - New nodes appear with 1.33
# - Old nodes get cordoned (SchedulingDisabled)
# - Pods drain from old nodes to new nodes
# - Old nodes disappear
```

### Verify default-pool completion

```bash
# All default-pool nodes should show 1.33
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool

# Check for any stuck pods
kubectl get pods -A | grep -v Running | grep -v Completed
```

### Upgrade workload-pool

```bash
# Start second node pool upgrade
gcloud container node-pools upgrade workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33

# Type 'Y' to confirm
```

### Monitor workload-pool upgrade

```bash
# Continue watching nodes
watch 'kubectl get nodes -o wide'

# Check operation status
gcloud container operations list --zone us-west1-b --filter="operationType=UPGRADE_NODES" --limit=2
```

## Phase 3: Post-Upgrade Validation (15 minutes)

### Step 1: Verify all versions

```bash
# Everything should show 1.33.x
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# All nodes should be Ready at 1.33
kubectl get nodes -o wide
```

### Step 2: Check workload health

```bash
# No pods should be stuck
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded

# All deployments at desired replica count
kubectl get deployments -A

# All StatefulSets ready
kubectl get statefulsets -A
```

### Step 3: System health check

```bash
# System pods healthy
kubectl get pods -n kube-system

# No stuck PDBs
kubectl get pdb -A -o wide
```

### Step 4: Application smoke test

Test your key applications to ensure they're working properly:

```bash
# Example: Test an application endpoint
kubectl get ingress -A
# Access your application URLs and verify functionality

# Example: Check service endpoints
kubectl get svc -A
```

## Troubleshooting Common Issues

### Issue 1: "PodDisruptionBudget is blocking drain"

**Symptom:** Node upgrade stuck, pods can't be evicted

**Fix:**
```bash
# Find the problematic PDB
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# Temporarily relax the PDB
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'

# Restore after upgrade completes
```

### Issue 2: "Pods pending due to insufficient resources"

**Symptom:** New pods can't be scheduled

**Fix:**
```bash
# Check node capacity
kubectl top nodes
kubectl describe nodes | grep -A 5 "Allocated resources"

# Temporarily scale down non-critical workloads
kubectl scale deployment NON_CRITICAL_APP --replicas=0
```

### Issue 3: "Upgrade operation not progressing"

**Symptom:** No visible progress for >30 minutes

**Fix:**
```bash
# Check for events
kubectl get events -A --sort-by='.lastTimestamp' | tail -10

# Check operation details
gcloud container operations describe OPERATION_ID --zone us-west1-b
```

### Issue 4: If you need to cancel/rollback

```bash
# List current operations
gcloud container operations list --zone us-west1-b

# You cannot cancel control plane upgrades
# For node pool upgrades, GKE will complete the current node then stop
# No manual rollback needed - existing upgraded nodes are fine
```

## Important Notes

- **Duration:** Expect 1-2 hours total for both node pools
- **Workload impact:** Pods restart as nodes are replaced, but services stay available
- **Cost:** Temporary cost increase during upgrade due to surge nodes
- **Rollback:** Control plane cannot be rolled back. Node pools can be replaced if needed
- **Auto-upgrades:** This cluster will automatically upgrade to future 1.33 patches

## Emergency contacts

- **If upgrade fails completely:** Contact your cloud admin or open a Google Cloud support case
- **If workloads are impacted:** Check your application logs and monitoring dashboards

---

**Next steps after successful upgrade:**
- Document the process for your team
- Consider setting up maintenance windows for future auto-upgrades
- Review GKE release notes for 1.33 features you might want to use

Your cluster will now automatically receive 1.33 patch updates per the Regular release channel schedule.