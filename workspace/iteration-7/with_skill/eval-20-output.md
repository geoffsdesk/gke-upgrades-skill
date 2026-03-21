I notice you mentioned upgrading from 1.32 to 1.32 — since you're already at 1.32, I'll assume you meant upgrading **to** 1.33 (the next minor version). Let me create a complete runbook for your first GKE upgrade.

# GKE Upgrade Runbook: 1.32 → 1.33
**Cluster:** Standard | **Channel:** Regular | **Zone:** us-west1-b

## Overview
This runbook upgrades your cluster in two phases:
1. **Control plane** (master) upgrade to 1.33
2. **Node pools** upgrade to 1.33

The control plane must be upgraded first — node pools cannot be newer than the control plane.

---

## Phase 1: Pre-flight Checks

### 1.1 Verify current state
```bash
# Check current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Expected output: Control plane and nodes should show 1.32.x
```

### 1.2 Confirm target version availability
```bash
# Check available versions in Regular channel
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels.REGULAR.validVersions)"

# Look for 1.33.x versions in the output
```

### 1.3 Check for deprecated APIs (most common upgrade failure)
```bash
# Check if your workloads use deprecated APIs
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# If this returns results, you have deprecated API usage that must be fixed first
# Common culprits: old Ingress apiVersion, PodSecurityPolicy, etc.
```

### 1.4 Verify cluster health
```bash
# All nodes should be Ready
kubectl get nodes

# All system pods should be Running
kubectl get pods -n kube-system

# Check for any unhealthy workloads
kubectl get pods -A | grep -v Running | grep -v Completed
```

### 1.5 Check PodDisruptionBudgets (PDBs)
```bash
# List all PDBs - these can block upgrades if too restrictive
kubectl get pdb -A

# Check each PDB's allowed disruptions
kubectl get pdb -A -o wide

# If any show ALLOWED DISRUPTIONS = 0, note them for potential adjustment
```

**🛑 STOP:** If any pre-flight checks fail, resolve issues before proceeding.

---

## Phase 2: Control Plane Upgrade

### 2.1 Upgrade the control plane
```bash
# Start control plane upgrade to latest 1.33.x
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version 1.33

# Type 'Y' when prompted to confirm
# This takes 10-15 minutes typically
```

### 2.2 Monitor upgrade progress
```bash
# Check upgrade operation status
gcloud container operations list --cluster CLUSTER_NAME --zone us-west1-b --limit=1

# Wait until operation shows "DONE" status
```

### 2.3 Verify control plane upgrade
```bash
# Confirm control plane is now 1.33.x
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"

# System pods should restart automatically - check they're healthy
kubectl get pods -n kube-system

# Basic functionality test
kubectl get nodes
```

**✅ Control plane upgrade complete**

---

## Phase 3: Node Pool Upgrades

Now upgrade each node pool. Nodes will be replaced with new ones running 1.33.

### 3.1 Configure surge upgrade settings

For most workloads, these settings provide a good balance of speed and safety:
```bash
# Configure default-pool upgrade strategy
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Configure workload-pool upgrade strategy  
gcloud container node-pools update workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**What this means:**
- `max-surge-upgrade 1`: Create 1 extra node before removing old ones
- `max-unavailable-upgrade 0`: Don't remove nodes until replacements are ready
- This minimizes disruption but uses extra compute quota temporarily

### 3.2 Upgrade default-pool
```bash
# Start default-pool upgrade
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33

# Type 'Y' when prompted
```

### 3.3 Monitor default-pool upgrade
```bash
# Watch node replacement progress (press Ctrl+C to exit)
watch 'kubectl get nodes -o wide'

# Look for:
# - New nodes appearing with 1.33.x
# - Old nodes going to NotReady then disappearing
# - Pods being rescheduled to new nodes

# Alternative: Check operation status
gcloud container operations list --cluster CLUSTER_NAME --zone us-west1-b --limit=1
```

### 3.4 Verify default-pool upgrade
```bash
# Confirm all default-pool nodes are 1.33.x
gcloud container node-pools describe default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(version)"

# Check node health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed
```

### 3.5 Upgrade workload-pool
```bash
# Start workload-pool upgrade
gcloud container node-pools upgrade workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33

# Type 'Y' when prompted
```

### 3.6 Monitor workload-pool upgrade
```bash
# Watch progress
watch 'kubectl get nodes -o wide'

# Check operation status
gcloud container operations list --cluster CLUSTER_NAME --zone us-west1-b --limit=1
```

### 3.7 Verify workload-pool upgrade
```bash
# Confirm workload-pool is 1.33.x
gcloud container node-pools describe workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(version)"
```

---

## Phase 4: Post-Upgrade Validation

### 4.1 Verify complete cluster state
```bash
# Final version check - everything should be 1.33.x
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# All nodes Ready
kubectl get nodes

# All system components healthy
kubectl get pods -n kube-system

# No stuck or failed pods
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded
```

### 4.2 Application smoke tests
```bash
# Test key application endpoints
# Replace with your actual application URLs/services
kubectl get services -A
kubectl get ingress -A

# Check your applications are responding
# curl http://YOUR_APP_URL/health
```

### 4.3 Clean up
```bash
# Surge nodes are automatically cleaned up
# Check compute quota usage is back to normal
gcloud compute instances list --zones=us-west1-b --filter="name~gke-CLUSTER_NAME"
```

---

## Troubleshooting Common Issues

### If upgrade gets stuck:

**1. Check for restrictive PDBs:**
```bash
kubectl get pdb -A -o wide
# If ALLOWED DISRUPTIONS = 0, temporarily relax:
kubectl patch pdb PDB_NAME -n NAMESPACE -p '{"spec":{"maxUnavailable":"50%"}}'
```

**2. Check for resource constraints:**
```bash
kubectl get pods -A | grep Pending
kubectl top nodes
# If nodes are full, increase surge: --max-surge-upgrade 2
```

**3. Check for bare pods:**
```bash
kubectl get pods -A -o json | jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
# Delete bare pods - they won't reschedule anyway
```

**4. Check operations status:**
```bash
gcloud container operations list --cluster CLUSTER_NAME --zone us-west1-b
# If stuck for >2 hours, contact GKE support
```

---

## Emergency Rollback

**Control plane:** Cannot be easily rolled back. Contact GKE support if issues.

**Node pools:** Create new pools at old version and migrate workloads:
```bash
# Example: Create replacement pool at 1.32
gcloud container node-pools create default-pool-rollback \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.32 \
  --num-nodes 3 \
  --machine-type e2-medium

# Cordon upgraded pool and drain workloads
kubectl cordon -l cloud.google.com/gke-nodepool=default-pool
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data
```

---

## Summary Checklist

- [ ] Pre-flight checks passed
- [ ] Control plane upgraded to 1.33.x  
- [ ] default-pool upgraded to 1.33.x
- [ ] workload-pool upgraded to 1.33.x
- [ ] All nodes Ready
- [ ] All applications responding
- [ ] No stuck pods or operations

**Expected total time:** 45-90 minutes depending on cluster size and workload complexity.

**Next steps:** Consider setting up maintenance windows for future auto-upgrades to control timing better.