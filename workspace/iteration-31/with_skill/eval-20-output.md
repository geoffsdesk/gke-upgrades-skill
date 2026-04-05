# GKE Upgrade Runbook: 1.32 → 1.33

**Cluster:** Standard cluster on Regular channel  
**Current version:** 1.32  
**Target version:** 1.33  
**Zone:** us-west1-b  
**Node pools:** default-pool, workload-pool

This runbook assumes you want **manual control** over the upgrade timing. The cluster is on Regular channel, so it would auto-upgrade eventually, but this gives you control over when.

## Prerequisites

- `gcloud` CLI configured with appropriate permissions
- `kubectl` configured for the target cluster
- Cluster admin access

## Phase 1: Pre-flight Checks (15-20 minutes)

### Step 1: Verify cluster information

```bash
# Get current cluster versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"
```

**Expected output:** Control plane and both node pools at 1.32.x

### Step 2: Check target version availability

```bash
# Confirm 1.33 is available in Regular channel
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels.REGULAR.validVersions)" | grep "1\.33"
```

**Expected output:** Should show 1.33.x versions available

### Step 3: Check for deprecated API usage

```bash
# Check for deprecated APIs (most common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Also check GKE insights
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=us-west1-b \
    --project=PROJECT_ID \
    --filter="category.category:RELIABILITY"
```

**Expected output:** No deprecated API usage shown. If you see results, resolve those issues before proceeding.

### Step 4: Verify cluster health

```bash
# Check all nodes are Ready
kubectl get nodes

# Check no pods in problematic states
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded

# Check system pods
kubectl get pods -n kube-system
```

**Expected output:** All nodes Ready, no CrashLoopBackOff or stuck pods

### Step 5: Check PodDisruptionBudgets

```bash
# List all PDBs and their current disruption allowances
kubectl get pdb -A -o wide
```

**Note any PDBs with ALLOWED DISRUPTIONS = 0** — these may block node drain later.

### Step 6: Backup critical data (if applicable)

If you have stateful workloads (databases, persistent storage), take application-level backups:

```bash
# Example for PostgreSQL (adjust for your workloads)
# kubectl exec -it postgres-pod -- pg_dump database_name > backup.sql

# Check PV reclaim policies (should be Retain for safety)
kubectl get pv -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy
```

## Phase 2: Control Plane Upgrade (10-15 minutes)

### Step 7: Start control plane upgrade

```bash
# Upgrade control plane to 1.33
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version 1.33
```

**Expected output:** Confirmation prompt → type `y` to proceed

**Timeline:** Control plane upgrade takes 10-15 minutes. Your workloads continue running normally.

### Step 8: Monitor control plane upgrade

```bash
# Check upgrade progress
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --limit 1

# Once complete, verify control plane version
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"
```

**Expected output:** Should show 1.33.x once complete

### Step 9: Verify control plane health

```bash
# System pods should restart and be healthy
kubectl get pods -n kube-system

# API server should respond normally
kubectl get nodes
```

## Phase 3: Node Pool Upgrades (30-60 minutes per pool)

**Important:** Control plane must be upgraded before node pools. Node pools are upgraded sequentially (one at a time).

### Step 10: Configure surge settings (optional but recommended)

For most workloads, default surge settings work fine. If you want faster upgrades:

```bash
# Configure conservative surge for default-pool
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Configure conservative surge for workload-pool  
gcloud container node-pools update workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**What this means:** 
- `maxSurge=1`: Create 1 extra node at target version
- `maxUnavailable=0`: Don't drain any nodes until the new node is ready
- This provides zero-downtime rolling replacement

### Step 11: Upgrade first node pool (default-pool)

```bash
# Start upgrading default-pool
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33
```

**Timeline:** 15-45 minutes depending on pool size and workloads

### Step 12: Monitor first node pool upgrade

```bash
# Watch node versions change
watch 'kubectl get nodes -o wide'

# In another terminal, monitor operations
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --limit 3

# Check for any stuck pods
kubectl get pods -A | grep -E "Terminating|Pending|ContainerCreating"
```

**What to expect:**
- New nodes appear with 1.33.x
- Old nodes get cordoned (marked unschedulable)
- Pods drain from old nodes to new nodes
- Old nodes disappear

### Step 13: Validate first node pool completion

```bash
# Verify all nodes in default-pool are at 1.33
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool

# Check pool status
gcloud container node-pools describe default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(version, status)"
```

**Expected output:** All nodes at 1.33.x, status RUNNING

### Step 14: Upgrade second node pool (workload-pool)

```bash
# Start upgrading workload-pool
gcloud container node-pools upgrade workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33
```

### Step 15: Monitor second node pool upgrade

```bash
# Same monitoring as before
watch 'kubectl get nodes -o wide'

# Check workload health during upgrade
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
```

### Step 16: Validate second node pool completion

```bash
# Verify all nodes in workload-pool are at 1.33
kubectl get nodes -l cloud.google.com/gke-nodepool=workload-pool

# Check pool status
gcloud container node-pools describe workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(version, status)"
```

## Phase 4: Post-Upgrade Validation (10 minutes)

### Step 17: Complete cluster health check

```bash
# Verify entire cluster is at 1.33
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# All nodes should be Ready and at target version
kubectl get nodes -o wide

# No pods should be stuck
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded
```

**Expected output:** Control plane and all node pools at 1.33.x

### Step 18: Application smoke tests

```bash
# Test key workload endpoints (adjust for your applications)
kubectl get ingress -A
kubectl get svc -A

# Run application-specific health checks
# Example: curl health endpoints, database connectivity tests, etc.
```

### Step 19: Verify system components

```bash
# System pods should all be healthy
kubectl get pods -n kube-system

# Check for any events indicating issues
kubectl get events -A --sort-by='.lastTimestamp' | tail -20
```

## Troubleshooting Common Issues

If the upgrade gets stuck, here's how to diagnose:

### Issue: Node upgrade stuck on draining

```bash
# Check what's preventing drain
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# If PDB is too restrictive, temporarily relax it:
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"100%"}}'
```

### Issue: Pods stuck Pending

```bash
# Check if there's room for pods
kubectl describe pods PENDING_POD -n NAMESPACE | grep -A 10 Events

# Check node resources
kubectl top nodes
```

### Issue: Surge nodes won't create

```bash
# Check if you have compute quota
gcloud compute project-info describe --format="yaml(quotas)" | grep -A2 CPUS

# Reduce surge to minimal settings
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

## Rollback (if needed)

If critical issues arise, you can rollback node pools (not control plane):

```bash
# Create new pool at previous version
gcloud container node-pools create rollback-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.32 \
  --num-nodes 3 \
  --machine-type e2-medium

# Cordon the problematic pool
kubectl cordon -l cloud.google.com/gke-nodepool=PROBLEM_POOL

# Migrate workloads manually, then delete problem pool
```

## Important Notes

- **This is a manual upgrade process.** Your cluster is on Regular channel and would eventually auto-upgrade, but this gives you control over timing.
- **Maintenance windows:** If you want future upgrades to happen automatically but only during specific times, configure maintenance windows:
  ```bash
  gcloud container clusters update CLUSTER_NAME \
    --zone us-west1-b \
    --maintenance-window-start "2024-01-01T02:00:00Z" \
    --maintenance-window-end "2024-01-01T06:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
  ```

- **Version skew:** Nodes can be up to 2 minor versions behind the control plane, so having 1.32 nodes with a 1.33 control plane is perfectly fine during the upgrade process.

- **Timeline:** Total upgrade time is typically 45-90 minutes (15 min control plane + 15-45 min per node pool).

You're now ready to upgrade! Start with the pre-flight checks and work through each phase systematically.