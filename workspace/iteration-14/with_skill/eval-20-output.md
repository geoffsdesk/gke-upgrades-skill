# GKE Cluster Upgrade Runbook: 1.32 → 1.33

**Cluster:** Standard mode, Regular channel  
**Current version:** 1.32  
**Target version:** 1.33  
**Zone:** us-west1-b  
**Node pools:** default-pool, workload-pool

This runbook provides complete step-by-step instructions for your first GKE upgrade.

## Pre-flight Checks (30 minutes)

### 1. Verify cluster status and versions

```bash
# Check current cluster and node pool versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Verify 1.33 is available in Regular channel
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels.REGULAR)"
```

**Expected output:** Control plane and nodes should show 1.32.x versions, and 1.33.x should appear in Regular channel available versions.

### 2. Check for deprecated API usage

```bash
# Check for deprecated APIs (major upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Also check GKE insights (alternative method)
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=us-west1-b \
    --project=$(gcloud config get-value project) \
    --format="table(name,description)"
```

**Expected output:** No deprecated API usage shown. If you see deprecated APIs, stop here and fix them first.

### 3. Verify cluster health

```bash
# Check all nodes are Ready
kubectl get nodes -o wide

# Check for unhealthy pods
kubectl get pods -A | grep -v Running | grep -v Completed

# Check system pods specifically  
kubectl get pods -n kube-system | grep -v Running

# Check for PodDisruptionBudgets that might block drain
kubectl get pdb -A -o wide
```

**Expected output:** 
- All nodes show `Ready`
- No pods in `CrashLoopBackOff`, `Error`, or `Pending` states
- All kube-system pods are `Running`
- PDBs show `ALLOWED DISRUPTIONS > 0`

### 4. Backup critical data (if applicable)

```bash
# List persistent volumes
kubectl get pv

# For any critical stateful workloads, ensure recent backups exist
# Check your backup procedures for databases, etc.
```

## Phase 1: Control Plane Upgrade (15-20 minutes)

### 1. Upgrade the control plane to 1.33

```bash
# Start control plane upgrade
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version 1.33

# When prompted, type 'Y' to confirm
```

**Expected output:** Operation will start. You'll see a message like "Upgrading CLUSTER_NAME...done."

### 2. Monitor control plane upgrade progress

```bash
# Check upgrade operation status
gcloud container operations list \
  --zone us-west1-b \
  --filter="operationType=UPGRADE_MASTER" \
  --limit=1

# Wait for operation to complete (usually 10-15 minutes)
# Check every 2-3 minutes with:
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"
```

**Expected output:** Version should change from 1.32.x to 1.33.x when complete.

### 3. Verify control plane upgrade success

```bash
# Confirm control plane version
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"

# Test API server connectivity
kubectl get nodes

# Check system pods restarted successfully
kubectl get pods -n kube-system
```

**Expected output:** Control plane version shows 1.33.x, kubectl commands work, all system pods are Running.

## Phase 2: Node Pool Upgrades (30-60 minutes per pool)

### 1. Configure upgrade strategy for default-pool

```bash
# Set surge upgrade parameters (conservative settings for first upgrade)
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**What this does:** Creates 1 extra node during upgrade, keeps all existing nodes until new one is ready (zero downtime).

### 2. Start default-pool upgrade

```bash
# Upgrade default-pool to 1.33
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33

# When prompted, type 'Y' to confirm
```

### 3. Monitor default-pool upgrade

```bash
# Watch node replacement progress (run this in a separate terminal)
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check for any stuck pods during drain
kubectl get pods -A | grep -E "Terminating|Pending"

# Monitor upgrade operation
gcloud container operations list \
  --zone us-west1-b \
  --filter="operationType=UPGRADE_NODES" \
  --limit=1
```

**Expected behavior:** You'll see:
1. New nodes appear with 1.33.x version
2. Old nodes get cordoned (marked as unschedulable)
3. Pods migrate to new nodes
4. Old nodes are deleted
5. Process repeats for each node

### 4. Verify default-pool upgrade

```bash
# Check all nodes in default-pool are at 1.33
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool -o wide

# Verify no stuck pods
kubectl get pods -A | grep -v Running | grep -v Completed
```

### 5. Configure upgrade strategy for workload-pool

```bash
# Set surge upgrade parameters for workload-pool
gcloud container node-pools update workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### 6. Start workload-pool upgrade

```bash
# Upgrade workload-pool to 1.33
gcloud container node-pools upgrade workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33

# When prompted, type 'Y' to confirm
```

### 7. Monitor workload-pool upgrade

```bash
# Watch node replacement progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Monitor for any issues
kubectl get pods -A | grep -E "Terminating|Pending"
```

## Post-Upgrade Validation (10 minutes)

### 1. Verify all components upgraded

```bash
# Check final cluster state
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Verify all nodes
kubectl get nodes -o wide
```

**Expected output:** Control plane and all node pools show 1.33.x versions.

### 2. Application health checks

```bash
# Check all pods are running
kubectl get pods -A | grep -v Running | grep -v Completed

# Check deployments are at desired replica count
kubectl get deployments -A

# Check any StatefulSets
kubectl get statefulsets -A

# Test a sample application endpoint (replace with your app)
# curl http://YOUR_APP_ENDPOINT/health
```

### 3. Verify cluster services

```bash
# Test DNS resolution
kubectl run test-pod --image=busybox --rm -it --restart=Never -- nslookup kubernetes.default.svc.cluster.local

# Check ingress/load balancers (if you have any)
kubectl get ingress -A
kubectl get services -A --field-selector spec.type=LoadBalancer
```

## Troubleshooting Common Issues

### If upgrade gets stuck:

```bash
# Check what's blocking the drain
kubectl get events --sort-by='.lastTimestamp' | tail -20

# Check for restrictive PodDisruptionBudgets
kubectl get pdb -A -o wide | grep "0"

# Temporarily relax a blocking PDB (example)
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"100%"}}'
```

### If pods won't schedule:

```bash
# Check node capacity
kubectl describe nodes | grep -A 5 "Allocated resources"

# Look for pending pods and reasons
kubectl get events --field-selector reason=FailedScheduling
```

### Emergency rollback (node pools only):

```bash
# Create new pool at old version if needed
gcloud container node-pools create rollback-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.32 \
  --num-nodes 3 \
  --machine-type e2-standard-4

# Cordon upgraded nodes and migrate workloads
kubectl cordon -l cloud.google.com/gke-nodepool=workload-pool
```

## Success Checklist

- [ ] Control plane shows version 1.33.x
- [ ] Both node pools show version 1.33.x
- [ ] All nodes are in `Ready` state
- [ ] All pods are `Running` (except completed jobs)
- [ ] Applications responding normally
- [ ] No upgrade operations in progress
- [ ] Surge quota automatically released

## What to do next

1. **Monitor for 24-48 hours** - Watch for any delayed issues
2. **Update your documentation** - Record the upgrade for future reference  
3. **Set up maintenance windows** - Configure recurring windows for future auto-upgrades
4. **Consider automation** - Let GKE handle future patch upgrades automatically

## Maintenance window setup (recommended)

```bash
# Set recurring weekend maintenance window for future auto-upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone us-west1-b \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-end "2024-01-06T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Congratulations!** You've successfully completed your first GKE upgrade. The cluster is now running Kubernetes 1.33 and will receive automatic patch updates during your maintenance window.