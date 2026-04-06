# GKE Upgrade Runbook: 1.32 → 1.33
**Cluster:** Standard | **Channel:** Regular | **Zone:** us-west1-b

This is a **minor version upgrade** (1.32→1.33). Follow each step carefully and don't proceed to the next until the current step is complete.

## Overview
GKE upgrades happen in two phases:
1. **Control plane upgrade** (~10-15 minutes) - manages the cluster
2. **Node pool upgrades** (~30-60 minutes each) - worker nodes where your pods run

## Phase 1: Pre-flight Checks

### 1.1 Verify current state
```bash
# Check current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"
```
**Expected:** Control plane and both node pools should show 1.32.x

### 1.2 Confirm target version is available
```bash
# Check available versions in Regular channel
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels)" | grep -A 10 "REGULAR"
```
**Expected:** Version 1.33.x should be listed as available

### 1.3 Check for deprecated APIs (critical!)
```bash
# Check for deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```
**Expected:** No output (good) or minimal deprecated calls

If you see deprecated APIs, check the [GKE deprecation insights](https://console.cloud.google.com/kubernetes/clusters) in the console before proceeding.

### 1.4 Verify cluster health
```bash
# All nodes should be Ready
kubectl get nodes

# No stuck/failed pods
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded

# System pods healthy
kubectl get pods -n kube-system
```
**Expected:** All nodes Ready, minimal non-Running pods, all system pods healthy

### 1.5 Check PodDisruptionBudgets
```bash
# Look for overly restrictive PDBs
kubectl get pdb -A -o wide
```
**Expected:** ALLOWED DISRUPTIONS should be > 0 for most PDBs. If any show 0, note them for potential adjustment.

## Phase 2: Control Plane Upgrade

### 2.1 Upgrade the control plane
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version 1.33
```
**⚠️ When prompted, type `Y` to confirm**

This takes 10-15 minutes. You'll see progress updates.

### 2.2 Verify control plane upgrade
```bash
# Wait for completion, then check version
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"
```
**Expected:** Should show 1.33.x

### 2.3 Test cluster API access
```bash
# Verify kubectl still works
kubectl get nodes
kubectl get pods -n kube-system
```
**Expected:** Commands work normally, system pods may be restarting (normal)

## Phase 3: Node Pool Upgrades

Now upgrade each node pool. **Do them one at a time, starting with default-pool.**

### 3.1 Configure surge settings for default-pool
```bash
# Set conservative surge settings (1 node at a time)
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### 3.2 Start default-pool upgrade
```bash
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33
```
**⚠️ When prompted, type `Y` to confirm**

### 3.3 Monitor default-pool progress
```bash
# Watch nodes upgrade (run this in a separate terminal)
watch 'kubectl get nodes -o wide'

# Check for issues (run occasionally)
kubectl get pods -A | grep -E "Pending|Terminating|CrashLoop"
```

**What to expect:**
- Nodes will show "SchedulingDisabled" as they're drained
- New nodes appear with version 1.33.x
- Old nodes disappear
- Pods may briefly show "Terminating" then restart on new nodes

**Estimated time:** 30-60 minutes depending on workloads

### 3.4 Verify default-pool completion
```bash
# All nodes in default-pool should be 1.33.x
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool -o wide
```

### 3.5 Configure surge settings for workload-pool
```bash
# Set conservative surge settings
gcloud container node-pools update workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### 3.6 Start workload-pool upgrade
```bash
gcloud container node-pools upgrade workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33
```
**⚠️ When prompted, type `Y` to confirm**

### 3.7 Monitor workload-pool progress
```bash
# Watch nodes upgrade
watch 'kubectl get nodes -o wide'

# Check for issues
kubectl get pods -A | grep -E "Pending|Terminating|CrashLoop"
```

### 3.8 Verify workload-pool completion
```bash
# All nodes should be 1.33.x
kubectl get nodes -l cloud.google.com/gke-nodepool=workload-pool -o wide
```

## Phase 4: Post-Upgrade Validation

### 4.1 Verify final state
```bash
# All components at 1.33
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# All nodes Ready
kubectl get nodes

# No stuck pods
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded
```

### 4.2 Test application functionality
```bash
# Check your applications are responding
kubectl get deployments -A
kubectl get services -A

# Run any application-specific health checks you have
```

## Troubleshooting Common Issues

### If upgrade gets stuck:

**1. Pods won't drain due to PDB:**
```bash
# Find the blocking PDB
kubectl get pdb -A -o wide
kubectl describe pdb PDB_NAME -n NAMESPACE

# Temporarily relax it
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

**2. Pods stuck Pending (not enough resources):**
```bash
# Check node resources
kubectl top nodes
kubectl describe nodes | grep -A 5 "Allocated resources"

# Scale down non-critical workloads temporarily
kubectl scale deployment DEPLOYMENT_NAME --replicas=0
```

**3. Long-running operations:**
```bash
# Check operation status
gcloud container operations list --cluster CLUSTER_NAME --zone us-west1-b --limit=5
```

## Emergency Rollback

If you need to stop an in-progress node pool upgrade:
```bash
# This won't rollback completed nodes, but stops further upgrades
gcloud container operations cancel OPERATION_ID --zone us-west1-b
```

**Note:** Control plane upgrades cannot be rolled back. Node pools that have already upgraded cannot be downgraded in-place.

## Final Notes

- **Total estimated time:** 2-3 hours for the complete upgrade
- **Best time to run:** During maintenance windows or low-traffic periods  
- **Cluster remains available:** Your applications stay running throughout the upgrade
- **Auto-upgrades:** Since you're on Regular channel, GKE will auto-upgrade in the future. Set maintenance windows if you want to control timing.

**Success criteria:**
- ✅ Control plane: 1.33.x
- ✅ All nodes: 1.33.x  
- ✅ All nodes: Ready status
- ✅ Applications: Responding normally

Replace `CLUSTER_NAME` with your actual cluster name in all commands above.