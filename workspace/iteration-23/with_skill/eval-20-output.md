# GKE Upgrade Runbook: 1.32 → 1.33

**Cluster Details:**
- Type: Standard
- Channel: Regular 
- Current Version: 1.32
- Target Version: 1.33
- Zone: us-west1-b
- Node Pools: default-pool, workload-pool

**Prerequisites:**
- `gcloud` CLI installed and authenticated
- `kubectl` configured for the cluster
- Cluster admin permissions

## Phase 1: Pre-Flight Checks (15 minutes)

### 1.1 Verify current cluster state

```bash
# Check current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Expected output: Control plane and all nodes at 1.32.x
```

### 1.2 Confirm target version availability

```bash
# Check available versions in Regular channel
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels)" | grep -A 10 "REGULAR"

# Verify 1.33.x appears in the list
```

### 1.3 Check for deprecated API usage

```bash
# Check for deprecated API calls (most common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# If output shows deprecated usage, check GKE console > Insights tab for details
# Address any deprecation warnings before proceeding
```

### 1.4 Verify cluster health

```bash
# All nodes should be Ready
kubectl get nodes

# No pods in bad states
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded

# System pods healthy
kubectl get pods -n kube-system

# Check for overly restrictive PDBs
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0 which could block upgrades
```

### 1.5 Check resource capacity

```bash
# Current resource usage
kubectl top nodes

# Detailed allocation per node
kubectl describe nodes | grep -A 5 "Allocated resources"

# Note: You'll need ~20% extra CPU/memory for surge nodes during upgrade
```

**✅ Pre-flight checklist complete. Proceed only if all checks pass.**

## Phase 2: Configure Maintenance Settings (5 minutes)

### 2.1 Set maintenance window (optional but recommended)

```bash
# Configure weekend maintenance window (Saturday 2-6 AM)
gcloud container clusters update CLUSTER_NAME \
  --zone us-west1-b \
  --maintenance-window-start "2024-12-07T02:00:00-08:00" \
  --maintenance-window-end "2024-12-07T06:00:00-08:00" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### 2.2 Configure node pool upgrade settings

```bash
# Configure conservative surge settings for default-pool
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Configure conservative surge settings for workload-pool  
gcloud container node-pools update workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Note: maxSurge=1 means 1 extra node during upgrade
# Note: maxUnavailable=0 means no downtime during rolling replacement
```

## Phase 3: Control Plane Upgrade (15-20 minutes)

### 3.1 Start control plane upgrade

```bash
# Upgrade control plane to 1.33
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version 1.33

# When prompted, type 'Y' to confirm
```

### 3.2 Monitor control plane upgrade

```bash
# Check upgrade progress (run every 2-3 minutes)
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --filter="operationType=UPGRADE_MASTER" \
  --limit 1

# Status will show RUNNING → DONE (takes ~10-15 minutes)
```

### 3.3 Verify control plane upgrade

```bash
# Confirm control plane is at 1.33
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"

# Should show 1.33.x

# Verify cluster is responsive
kubectl get pods -n kube-system
# All system pods should be Running
```

**⚠️ Important: Do not proceed to node upgrades until control plane shows 1.33**

## Phase 4: Node Pool Upgrades (30-60 minutes total)

### 4.1 Upgrade default-pool

```bash
# Start node pool upgrade
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33

# When prompted, type 'Y' to confirm
```

### 4.2 Monitor default-pool upgrade

```bash
# Monitor node versions (run every 5 minutes)
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Look for:
# - Old nodes: STATUS=Ready,SchedulingDisabled (cordoned)
# - New nodes: STATUS=Ready with 1.33.x version
# - Pods migrating between nodes

# Check for stuck pods
kubectl get pods -A | grep -E "Terminating|Pending|ContainerCreating"

# Monitor upgrade operation
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --filter="operationType=UPGRADE_NODES" \
  --limit 1
```

### 4.3 Verify default-pool upgrade completion

```bash
# All nodes in default-pool should show 1.33
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool

# No pods in bad states
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded
```

### 4.4 Upgrade workload-pool

```bash
# Start workload-pool upgrade
gcloud container node-pools upgrade workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33

# When prompted, type 'Y' to confirm
```

### 4.5 Monitor workload-pool upgrade

```bash
# Monitor progress (same commands as default-pool)
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check operation status
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --filter="operationType=UPGRADE_NODES" \
  --limit 1
```

## Phase 5: Post-Upgrade Validation (10 minutes)

### 5.1 Verify final cluster state

```bash
# All components at 1.33
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# All nodes Ready and at 1.33
kubectl get nodes -o wide

# System pods healthy
kubectl get pods -n kube-system
```

### 5.2 Application health check

```bash
# No pods in error states
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded

# Check your application pods specifically
kubectl get pods -n default  # or your app namespace
kubectl get deployments -A   # All deployments at desired replica count
```

### 5.3 Basic functionality test

```bash
# Test pod creation/deletion
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Upgrade successful"

# Expected output: "Upgrade successful" then pod deletion
```

## Troubleshooting Common Issues

### Issue: Upgrade stuck with pods Terminating

**Diagnosis:**
```bash
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0
```

**Fix:**
```bash
# Temporarily relax the PDB
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"100%"}}'

# Restore after upgrade completes
```

### Issue: Pods stuck Pending during upgrade

**Diagnosis:**
```bash
kubectl get events -A --field-selector reason=FailedScheduling
kubectl top nodes
```

**Fix:**
```bash
# Reduce surge to use less extra capacity
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

### Issue: Deprecated API blocking upgrade

**Diagnosis:**
```bash
# Check GKE console → Insights tab for deprecation details
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```

**Fix:** Update workloads to use supported API versions before retrying upgrade.

## Rollback Procedure (Emergency Only)

**⚠️ Contact Google Cloud Support before attempting rollback**

If you must rollback node pools:

```bash
# Create new node pool at 1.32
gcloud container node-pools create POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.32 \
  --num-nodes 3 \
  --machine-type e2-medium

# Cordon upgraded nodes
kubectl cordon -l cloud.google.com/gke-nodepool=ORIGINAL_POOL_NAME

# Manually migrate workloads, then delete old pool
```

## Timeline Expectations

- **Pre-flight checks:** 15 minutes
- **Control plane upgrade:** 15-20 minutes  
- **default-pool upgrade:** 15-30 minutes
- **workload-pool upgrade:** 15-30 minutes
- **Validation:** 10 minutes

**Total: 70-105 minutes**

## Success Criteria

✅ Control plane at 1.33.x  
✅ All nodes at 1.33.x  
✅ All pods Running/Completed  
✅ Test pod creation successful  
✅ Application health checks passing  

**Your upgrade is complete!** Document any issues encountered and lessons learned for future upgrades.