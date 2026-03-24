# GKE Upgrade Runbook: 1.32 → 1.33

**Cluster:** Standard cluster, Regular channel  
**Location:** us-west1-b  
**Upgrade:** 1.32 → 1.33 (minor version)  
**Node pools:** default-pool, workload-pool  

## Before You Start

⚠️ **Important Notes:**
- This is a **minor version upgrade** — expect 1-2 hours total time
- Control plane upgrades first (10-15 minutes), then each node pool (30-60 minutes each)
- Workloads will restart during node pool upgrades
- Have your team available during the upgrade window

## Phase 1: Pre-Flight Checks (15 minutes)

### 1.1 Verify Current State

```bash
# Check current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Expected output: Control plane and nodes should show 1.32.x
```

### 1.2 Confirm Target Version Available

```bash
# Check what versions are available in Regular channel
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels.REGULAR.validVersions)"

# Look for 1.33.x in the list
```

### 1.3 Check for Deprecated APIs (Critical)

```bash
# This is the #1 cause of upgrade failures
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# If you see ANY output, stop here and contact your platform team
# Empty output = good to proceed
```

### 1.4 Verify Cluster Health

```bash
# All nodes should be Ready
kubectl get nodes

# No pods should be stuck
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded

# Check for PodDisruptionBudgets that might block upgrades
kubectl get pdb -A
```

### 1.5 Check Resource Usage

```bash
# Ensure you have capacity for surge nodes during upgrade
kubectl top nodes

# If nodes are >80% CPU/memory, consider scaling down non-critical workloads first
```

## Phase 2: Configure Upgrade Settings (10 minutes)

### 2.1 Set Maintenance Window (Optional but Recommended)

```bash
# Set a maintenance window for future auto-upgrades (weekends at 2 AM)
gcloud container clusters update CLUSTER_NAME \
  --zone us-west1-b \
  --maintenance-window-start "2024-12-14T02:00:00Z" \
  --maintenance-window-end "2024-12-14T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### 2.2 Configure Node Pool Upgrade Strategy

For **default-pool** (assuming general workloads):
```bash
# Conservative settings: 1 surge node, 0 unavailable
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

For **workload-pool** (assuming application workloads):
```bash
# Slightly more aggressive: 2 surge nodes, 0 unavailable
gcloud container node-pools update workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

## Phase 3: Control Plane Upgrade (15 minutes)

### 3.1 Start Control Plane Upgrade

```bash
# Upgrade control plane to 1.33 (find exact version from step 1.2)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version 1.33.x-gke.xxxx

# You'll see a confirmation prompt - type 'y' and press Enter
```

### 3.2 Monitor Control Plane Upgrade

```bash
# Check upgrade progress (run every few minutes)
gcloud container operations list \
  --zone us-west1-b \
  --filter="targetLink~CLUSTER_NAME" \
  --limit=1

# Status should show RUNNING, then DONE
```

### 3.3 Verify Control Plane Upgrade

```bash
# Confirm control plane is now at 1.33
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"

# Test API access
kubectl get nodes

# Check system pods are healthy
kubectl get pods -n kube-system
```

## Phase 4: Node Pool Upgrades (60-90 minutes total)

### 4.1 Upgrade default-pool First

```bash
# Start node pool upgrade
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33.x-gke.xxxx

# Type 'y' to confirm
```

### 4.2 Monitor default-pool Upgrade

```bash
# Watch nodes being replaced (run in separate terminal)
watch 'kubectl get nodes -o wide'

# You'll see:
# - New nodes appear with 1.33
# - Old nodes get cordoned (SchedulingDisabled)
# - Old nodes get drained and deleted
```

### 4.3 Verify default-pool Upgrade

```bash
# Check all default-pool nodes are at 1.33
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool

# Ensure no pods are stuck
kubectl get pods -A | grep -v Running | grep -v Completed
```

### 4.4 Upgrade workload-pool

```bash
# Start second node pool upgrade
gcloud container node-pools upgrade workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33.x-gke.xxxx

# Type 'y' to confirm
```

### 4.5 Monitor workload-pool Upgrade

```bash
# Watch the second node pool upgrade
watch 'kubectl get nodes -o wide'

# Monitor for any pod issues
kubectl get pods -A | grep -v Running | grep -v Completed
```

## Phase 5: Post-Upgrade Validation (15 minutes)

### 5.1 Verify Final State

```bash
# All components should be at 1.33
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(currentMasterVersion, nodePools[].name, nodePools[].version)"

# All nodes Ready
kubectl get nodes

# All pods healthy
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded
```

### 5.2 Application Health Checks

```bash
# Check your specific applications are responding
# Replace with your actual service/ingress endpoints
kubectl get services -A
kubectl get ingress -A

# Test critical application endpoints
# curl YOUR_APP_ENDPOINT/health
```

### 5.3 Check for Common Post-Upgrade Issues

```bash
# Look for any webhook failures (common after K8s version bumps)
kubectl get events -A --field-selector type=Warning | grep -i webhook

# Check for any admission controller issues
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "test"
# This pod should create and run successfully
```

## Troubleshooting Common Issues

### If Control Plane Upgrade Fails
```bash
# Check the operation status for error details
gcloud container operations list \
  --zone us-west1-b \
  --filter="targetLink~CLUSTER_NAME" \
  --limit=1 \
  --format="yaml"

# Contact GKE support if operation shows unexpected errors
```

### If Node Pool Upgrade Gets Stuck
```bash
# Check for pods that won't drain
kubectl get pods -A | grep Terminating

# Check for restrictive PodDisruptionBudgets
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# Temporarily relax a PDB if needed:
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

### If Pods Won't Schedule
```bash
# Check for resource constraints
kubectl describe nodes | grep -A 5 "Allocated resources"

# Look for pending pods and why they can't schedule
kubectl get pods -A --field-selector=status.phase=Pending
kubectl describe pod POD_NAME -n NAMESPACE
```

## Rollback Plan (Emergency Only)

⚠️ **Control plane cannot be downgraded** - only node pools can be rolled back

### If Node Pool Needs Rollback
```bash
# Create new node pool at old version
gcloud container node-pools create default-pool-rollback \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.32.x-gke.xxxx \
  --num-nodes 3 \
  --machine-type e2-medium

# Cordon the upgraded pool
kubectl cordon -l cloud.google.com/gke-nodepool=default-pool

# Manually drain and delete the upgraded pool after workloads migrate
```

## Expected Timeline

| Phase | Duration | Description |
|-------|----------|-------------|
| Pre-flight | 15 min | Health checks, version verification |
| Control plane | 15 min | Master upgrade, API server restart |
| default-pool | 30-45 min | Node replacement, pod rescheduling |
| workload-pool | 30-45 min | Node replacement, pod rescheduling |
| Validation | 15 min | Health checks, smoke tests |
| **Total** | **1.5-2 hours** | Complete upgrade process |

## Success Criteria

✅ Control plane version: 1.33.x  
✅ All node pool versions: 1.33.x  
✅ All nodes status: Ready  
✅ All pods status: Running/Completed  
✅ Applications responding normally  
✅ No deprecated API warnings  

---

**Replace `CLUSTER_NAME` with your actual cluster name throughout this runbook.**

This runbook assumes standard configurations. If you encounter unexpected behavior, don't hesitate to reach out to your platform team or GKE support.