# GKE Upgrade Runbook: 1.32 → 1.33

**Cluster:** Standard | **Channel:** Regular | **Zone:** us-west1-b  
**Current:** 1.32 | **Target:** 1.33

This runbook provides complete step-by-step instructions for your first GKE upgrade. Follow each section in order.

## Pre-Flight Checks

### 1. Verify current cluster state
```bash
# Check current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Expected output: control plane and nodes both at 1.32.x-gke.xxx
```

### 2. Confirm 1.33 is available in Regular channel
```bash
# Check available versions
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels.REGULAR.validVersions)" | grep "1.33"

# You should see 1.33.x-gke.xxx versions listed
```

### 3. Check for deprecated APIs (upgrade blocker)
```bash
# Check for deprecated API usage - this is the #1 cause of upgrade failures
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# If you see output, you have deprecated APIs that need fixing before upgrade
# No output = good to proceed
```

### 4. Verify cluster health
```bash
# All nodes should be Ready
kubectl get nodes

# No unhealthy pods (ignore Completed pods)
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded

# System pods healthy
kubectl get pods -n kube-system
```

### 5. Check Pod Disruption Budgets (PDBs)
```bash
# List all PDBs - look for ALLOWED DISRUPTIONS = 0
kubectl get pdb -A -o wide

# If any PDB shows 0 allowed disruptions, note the name/namespace for later
```

### 6. Backup critical data (if you have stateful workloads)
```bash
# Example for databases - adapt to your workloads
# kubectl exec -it postgres-pod -- pg_dump dbname > backup.sql
# kubectl exec -it mysql-pod -- mysqldump --all-databases > backup.sql

echo "Take application-level backups of any databases before proceeding"
```

## Step 1: Configure Maintenance Settings

### Set maintenance window (recommended)
```bash
# Set weekend maintenance window (Saturday 2-6 AM PST)
gcloud container clusters update CLUSTER_NAME \
  --zone us-west1-b \
  --maintenance-window-start "2024-01-06T10:00:00Z" \
  --maintenance-window-end "2024-01-06T14:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Verify window is set
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(maintenancePolicy.window)"
```

### Optional: Add maintenance exclusion for control
```bash
# Only if you want to prevent automatic upgrades and control timing manually
# Skip this if you want GKE to auto-upgrade during your maintenance window

gcloud container clusters update CLUSTER_NAME \
  --zone us-west1-b \
  --add-maintenance-exclusion-name "manual-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-03-01T00:00:00Z"
```

## Step 2: Upgrade Control Plane

### Start control plane upgrade
```bash
# This upgrades only the control plane (master), not the nodes
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version 1.33

# When prompted, type 'y' to confirm
```

### Monitor control plane upgrade progress
```bash
# This takes 10-15 minutes typically
# Check operation status
gcloud container operations list \
  --zone us-west1-b \
  --filter="targetLink~CLUSTER_NAME AND operationType=UPGRADE_MASTER"

# Wait for operation to complete (STATUS = DONE)
```

### Verify control plane upgrade
```bash
# Control plane should now show 1.33.x-gke.xxx
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"

# System pods should restart and be healthy
kubectl get pods -n kube-system

# API should be responsive
kubectl get nodes
```

## Step 3: Configure Node Pool Upgrade Strategy

### Set surge settings for default-pool
```bash
# Conservative settings for your first upgrade
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

echo "default-pool configured: 1 surge node, 0 unavailable (zero-downtime rolling)"
```

### Set surge settings for workload-pool
```bash
# Same conservative settings
gcloud container node-pools update workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

echo "workload-pool configured: 1 surge node, 0 unavailable"
```

## Step 4: Upgrade Node Pools

### Upgrade default-pool first
```bash
# Start node pool upgrade
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33

# When prompted, type 'y' to confirm
```

### Monitor default-pool upgrade
```bash
# Watch nodes being upgraded (this takes 20-45 minutes depending on pool size)
watch 'kubectl get nodes -o wide'

# You'll see:
# - New nodes appearing with 1.33
# - Old nodes being cordoned (SchedulingDisabled)
# - Old nodes being drained and deleted

# Check for any stuck pods
kubectl get pods -A | grep -E "Terminating|Pending"
```

### Troubleshoot if nodes get stuck
```bash
# If upgrade stalls, check for PDB issues
kubectl get pdb -A -o wide

# If a PDB is blocking (ALLOWED DISRUPTIONS = 0), temporarily relax it:
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'

# Check for pending pods that can't schedule
kubectl get events -A --field-selector reason=FailedScheduling | tail -10
```

### Verify default-pool upgrade completion
```bash
# All nodes in default-pool should show 1.33
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool

# Confirm no unhealthy pods
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded
```

### Upgrade workload-pool
```bash
# Start second node pool upgrade
gcloud container node-pools upgrade workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33

# When prompted, type 'y' to confirm
```

### Monitor workload-pool upgrade
```bash
# Watch progress (another 20-45 minutes)
watch 'kubectl get nodes -o wide'

# Monitor workload health during upgrade
kubectl get pods -A | grep -v Running | grep -v Completed
```

## Step 5: Post-Upgrade Verification

### Verify all components at target version
```bash
# Control plane and all nodes should show 1.33
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"
```

### Check cluster health
```bash
# All nodes Ready
kubectl get nodes

# All system pods healthy
kubectl get pods -n kube-system

# No stuck pods anywhere
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded

# Deployments at desired replica count
kubectl get deployments -A
```

### Verify application functionality
```bash
# Test your applications - adapt these commands to your workloads:

# Check ingress/load balancers responding
kubectl get ingress -A
kubectl get services -A --field-selector spec.type=LoadBalancer

# Run basic connectivity test
kubectl run test-pod --image=nginx --rm -it --restart=Never -- curl -I http://your-app-service

# Check application-specific health endpoints
# curl http://your-app/health
```

### Clean up (if needed)
```bash
# Restore any PDBs you modified during upgrade
# kubectl apply -f pdb-backup.yaml

# Remove maintenance exclusion if you added one
gcloud container clusters update CLUSTER_NAME \
  --zone us-west1-b \
  --remove-maintenance-exclusion-name "manual-control"
```

## Rollback Plan (Emergency Only)

If you discover critical issues after upgrade:

### Node pool rollback
```bash
# Create new pool at old version
gcloud container node-pools create default-pool-rollback \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.32 \
  --num-nodes 3 \
  --machine-type e2-medium

# Cordon upgraded nodes
kubectl cordon -l cloud.google.com/gke-nodepool=default-pool

# Drain workloads to rollback pool
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data

# Delete old pool when rollback is complete
gcloud container node-pools delete default-pool --cluster CLUSTER_NAME --zone us-west1-b
```

## Expected Timeline

- **Control plane upgrade:** 10-15 minutes
- **default-pool upgrade:** 20-45 minutes (depends on node count)  
- **workload-pool upgrade:** 20-45 minutes (depends on node count)
- **Total:** 1-2 hours

## Success Criteria

✅ Control plane at 1.33.x-gke.xxx  
✅ All nodes at 1.33.x-gke.xxx  
✅ All pods Running or Completed  
✅ Applications responding normally  
✅ No deprecated API warnings  

---

**Important Notes:**
- This upgrade can run during business hours with zero downtime (maxUnavailable=0)
- Node pools upgrade one at a time automatically - you don't need to parallelize
- If you hit quota limits, the upgrade will slow down but continue
- Watch for PDB issues - they're the most common cause of stuck upgrades
- Control plane downgrades require Google support - node pools can be rolled back by creating new pools

**Replace `CLUSTER_NAME` with your actual cluster name in all commands.**