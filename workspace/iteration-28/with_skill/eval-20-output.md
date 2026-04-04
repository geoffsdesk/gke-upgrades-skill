# GKE Upgrade Runbook: 1.32 → 1.33

**Cluster:** Standard cluster on Regular channel  
**Current version:** 1.32  
**Target version:** 1.33  
**Location:** us-west1-b  
**Node pools:** default-pool, workload-pool

This runbook provides complete step-by-step commands for your first GKE upgrade.

## Phase 1: Pre-flight Checks (15 minutes)

### 1.1 Verify current cluster state

```bash
# Check current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"
```

**Expected output:** Control plane and both node pools should show 1.32.x versions.

### 1.2 Confirm target version is available

```bash
# Check available versions in Regular channel
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels.REGULAR.validVersions)"
```

**What to look for:** Version 1.33.x should appear in the list. If not, wait a few days for it to reach Regular channel.

### 1.3 Check for deprecated APIs (critical)

```bash
# Check for deprecated API usage - this is the #1 upgrade failure cause
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```

**If you see output:** You have deprecated APIs in use. Check the GKE console → your cluster → Insights tab for details on what needs to be fixed before upgrading.

**If no output:** Good to proceed.

### 1.4 Verify cluster health

```bash
# Check all nodes are Ready
kubectl get nodes

# Check for any failing pods
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded
```

**What to look for:** All nodes should show "Ready". Any pods showing "CrashLoopBackOff", "Error", or "Pending" should be investigated first.

### 1.5 Check Pod Disruption Budgets (PDBs)

```bash
# List all PDBs - these can block upgrades
kubectl get pdb -A -o wide
```

**What to look for:** If "ALLOWED DISRUPTIONS" shows 0 for critical services, the upgrade may get stuck. Make note of these for potential troubleshooting later.

### 1.6 Verify workload controllers

```bash
# Ensure no bare pods (they won't reschedule during upgrade)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

**If you see output:** These are bare pods that will be lost during upgrade. Wrap them in Deployments or delete if they're not needed.

## Phase 2: Control Plane Upgrade (20 minutes)

### 2.1 Upgrade control plane first

```bash
# Upgrade control plane to 1.33 (control plane MUST be upgraded before nodes)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version 1.33
```

**Expected behavior:** This will take 10-15 minutes. Your workloads continue running, but you temporarily can't deploy new workloads or make cluster configuration changes.

### 2.2 Monitor control plane upgrade

```bash
# Check operation status
gcloud container operations list --cluster CLUSTER_NAME --zone us-west1-b --limit=1

# Once complete, verify control plane version
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"
```

**Expected output:** Should show 1.33.x after completion.

### 2.3 Verify system pods restarted successfully

```bash
# Check kube-system pods are healthy after control plane upgrade
kubectl get pods -n kube-system

# Check for any events indicating issues
kubectl get events -n kube-system --sort-by='.lastTimestamp' | tail -10
```

**What to look for:** All kube-system pods should be Running. If any are CrashLoopBackOff, investigate before proceeding.

## Phase 3: Node Pool Upgrades (45-90 minutes)

### 3.1 Configure surge settings (Standard clusters only)

For first-time upgraders, we'll use conservative settings that minimize risk:

```bash
# Configure default-pool with conservative surge settings
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Configure workload-pool with same settings
gcloud container node-pools update workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**What this means:** Upgrade one node at a time (safest), create 1 new node before draining the old one (zero downtime).

### 3.2 Upgrade default-pool first

```bash
# Start default-pool upgrade
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33
```

**Expected behavior:** GKE will create a new 1.33 node, cordon an old 1.32 node, drain pods to the new node, then delete the old node. This repeats for each node.

### 3.3 Monitor default-pool upgrade progress

```bash
# Watch nodes upgrade (run this in a separate terminal)
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check for stuck operations every 10 minutes
gcloud container operations list --cluster CLUSTER_NAME --zone us-west1-b --limit=3
```

**What to look for:** Nodes should show version progression from 1.32 → 1.33. If stuck for >30 minutes on one node, check troubleshooting section.

### 3.4 Verify default-pool completion

```bash
# Confirm all default-pool nodes are at 1.33
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool

# Check no pods are stuck
kubectl get pods -A | grep -E "Terminating|Pending|ContainerCreating"
```

**Expected:** All default-pool nodes show 1.33.x, no stuck pods.

### 3.5 Upgrade workload-pool

```bash
# Start workload-pool upgrade
gcloud container node-pools upgrade workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33
```

### 3.6 Monitor workload-pool upgrade

```bash
# Continue watching progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Monitor for any pod disruption issues
kubectl get events -A --field-selector type=Warning | tail -20
```

## Phase 4: Post-upgrade Validation (10 minutes)

### 4.1 Verify final cluster state

```bash
# Confirm all components at target version
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# All nodes should be Ready and at 1.33
kubectl get nodes -o wide
```

**Expected:** Control plane and both node pools at 1.33.x, all nodes Ready.

### 4.2 Application health check

```bash
# Check all deployments have desired replicas
kubectl get deployments -A

# Verify no failed pods
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded

# Check StatefulSets if you have any
kubectl get statefulsets -A
```

### 4.3 System health verification

```bash
# Ensure kube-system is healthy
kubectl get pods -n kube-system

# Check cluster can schedule new pods (smoke test)
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Upgrade successful"
```

**Expected:** Test pod should run successfully and output "Upgrade successful".

## Troubleshooting Common Issues

### Issue: Upgrade stuck with "PodDisruptionBudget violated"

**Diagnosis:**
```bash
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0
```

**Fix (temporary):**
```bash
# Temporarily relax the blocking PDB
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'

# After upgrade completes, restore original PDB
kubectl rollout undo pdb/PDB_NAME -n NAMESPACE
```

### Issue: Pods stuck "Pending" during upgrade

**Diagnosis:**
```bash
kubectl describe pods POD_NAME -n NAMESPACE
# Look for "Insufficient cpu/memory" in events
```

**Fix:**
```bash
# Reduce surge to use less resources
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

### Issue: Node upgrade not starting after 30 minutes

**Check operation status:**
```bash
gcloud container operations list --cluster CLUSTER_NAME --zone us-west1-b --limit=1
```

**If operation shows "RUNNING" but no progress:** Contact Google Cloud Support with the operation ID.

## Rollback Plan (Emergency Only)

Control plane rollback requires Google Cloud Support. For node pools:

```bash
# Create new pool at old version (1.32)
gcloud container node-pools create default-pool-rollback \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.32 \
  --machine-type n1-standard-2 \
  --num-nodes 3

# Cordon upgraded nodes
kubectl cordon -l cloud.google.com/gke-nodepool=default-pool

# Wait for workloads to drain naturally, then delete old pool
gcloud container node-pools delete default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b
```

## Timeline Expectations

- **Control plane upgrade:** 10-15 minutes
- **Each node pool upgrade:** 20-45 minutes (depends on node count)
- **Total time:** 60-90 minutes for your cluster

## Success Criteria

✅ Control plane at 1.33.x  
✅ Both node pools at 1.33.x  
✅ All nodes show "Ready"  
✅ All workloads running normally  
✅ Test pod creation works  

Your cluster is now successfully upgraded to GKE 1.33!

## Notes for Future Upgrades

- **Auto-upgrades:** Your Regular channel cluster will auto-upgrade in the future. Configure maintenance windows if you want to control timing.
- **Patch upgrades:** Minor patches (e.g., 1.33.1 → 1.33.2) happen automatically and are much lower risk.
- **Next minor upgrade:** 1.33 → 1.34 will follow this same process when 1.34 reaches Regular channel.