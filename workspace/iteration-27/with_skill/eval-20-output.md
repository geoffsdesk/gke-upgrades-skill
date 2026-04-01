# GKE Upgrade Runbook: 1.32 → 1.33

**Cluster:** Standard cluster on Regular channel  
**Location:** us-west1-b  
**Current version:** 1.32  
**Target version:** 1.33  
**Node pools:** default-pool, workload-pool  

This runbook assumes auto-upgrades are disabled or you want manual control over timing. Each step includes validation to confirm success before proceeding.

## Phase 1: Pre-flight Checks (15 minutes)

### 1.1 Verify current cluster state
```bash
# Check current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Expected: Control plane and all nodes at 1.32.x-gke.xxx
```

### 1.2 Confirm target version availability
```bash
# Check what versions are available in Regular channel
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels.REGULAR.validVersions)" | grep "1.33"

# Expected: Should see 1.33.x-gke.xxx versions listed
```

### 1.3 Check for deprecated APIs (critical)
```bash
# Check for deprecated API usage - this is the #1 cause of upgrade failures
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Expected: No output (good) or specific deprecated API calls (needs investigation)
# If you see deprecated APIs, check the GKE console → Clusters → [your cluster] → Insights tab
```

### 1.4 Review cluster health
```bash
# Check all nodes are Ready
kubectl get nodes
# Expected: All nodes STATUS = Ready

# Check for problematic pods
kubectl get pods -A | grep -v Running | grep -v Completed
# Expected: Minimal output - only expected non-Running pods

# Check system pods
kubectl get pods -n kube-system
# Expected: All kube-system pods Running or Completed
```

### 1.5 Check PodDisruptionBudgets
```bash
# List all PDBs - these can block upgrades
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0 (problematic)

# If you see PDBs with 0 allowed disruptions:
kubectl describe pdb PDB_NAME -n NAMESPACE
# Note which ones might block drain - we'll handle this during the upgrade
```

## Phase 2: Control Plane Upgrade (20-30 minutes)

### 2.1 Backup current configuration (optional but recommended)
```bash
# Backup cluster config
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b > cluster-backup-$(date +%Y%m%d).yaml
```

### 2.2 Upgrade control plane to 1.33
```bash
# Upgrade control plane only (--master flag)
# Replace CLUSTER_NAME with your actual cluster name
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version 1.33

# You'll see a prompt: "Do you want to continue (Y/n)?" - type Y and press Enter
```

**Expected output:** 
```
Master of cluster [CLUSTER_NAME] will be upgraded from version [1.32.x-gke.xxx] to version [1.33.x-gke.xxx].
Do you want to continue (Y/n)?  Y
Upgrading CLUSTER_NAME... 
```

### 2.3 Monitor control plane upgrade
```bash
# Check upgrade operation status
gcloud container operations list --zone us-west1-b --filter="operationType=UPGRADE_MASTER"

# Wait for STATUS = DONE (typically 10-15 minutes)
```

### 2.4 Verify control plane upgrade
```bash
# Confirm control plane is at 1.33
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"

# Expected: 1.33.x-gke.xxx

# Test API server connectivity
kubectl get nodes
# Expected: Should work normally, nodes still show 1.32.x
```

## Phase 3: Node Pool Upgrades (30-60 minutes per pool)

**Important:** Nodes will be cordoned and drained. Pods will restart on new nodes. This is normal and expected.

### 3.1 Configure surge upgrade settings

For most workloads, these conservative settings work well:

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

**What this means:** One new node at a time, no downtime (maxUnavailable=0)

### 3.2 Upgrade first node pool (default-pool)

```bash
# Start default-pool upgrade
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33

# You'll see: "Do you want to continue (Y/n)?" - type Y
```

### 3.3 Monitor default-pool upgrade progress

```bash
# Watch node versions change (run in separate terminal)
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check upgrade operation
gcloud container operations list --zone us-west1-b --filter="operationType=UPGRADE_NODES"

# Monitor pod disruptions
kubectl get pods -A | grep -E "Terminating|Pending|ContainerCreating"
```

**What you'll see:** Nodes will show "Ready,SchedulingDisabled" then get replaced by new 1.33 nodes. Pods will be "Terminating" then recreated.

### 3.4 Troubleshoot if upgrade gets stuck

If no progress for >30 minutes, check common issues:

```bash
# Check for PDB blocking drain
kubectl get pdb -A -o wide
# If ALLOWED DISRUPTIONS = 0, temporarily relax:
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'

# Check for pending pods (resource constraints)
kubectl get pods -A | grep Pending
kubectl get events -A --field-selector reason=FailedScheduling

# Check for bare pods (not managed by controllers)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
# Delete any bare pods: kubectl delete pod POD_NAME -n NAMESPACE
```

### 3.5 Verify default-pool upgrade completion

```bash
# Confirm all default-pool nodes at 1.33
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool
# Expected: All nodes VERSION = v1.33.x-gke.xxx

# Check pod health
kubectl get pods -A | grep -v Running | grep -v Completed
# Expected: Minimal output
```

### 3.6 Upgrade second node pool (workload-pool)

```bash
# Start workload-pool upgrade
gcloud container node-pools upgrade workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33

# Monitor same as default-pool
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=workload-pool'
```

### 3.7 Verify workload-pool upgrade completion

```bash
# Confirm all workload-pool nodes at 1.33
kubectl get nodes -l cloud.google.com/gke-nodepool=workload-pool
# Expected: All nodes VERSION = v1.33.x-gke.xxx
```

## Phase 4: Post-Upgrade Validation (15 minutes)

### 4.1 Verify complete cluster state
```bash
# All nodes should be at 1.33
kubectl get nodes -o wide

# All system pods healthy
kubectl get pods -n kube-system

# Check all deployments have desired replicas
kubectl get deployments -A
# Look for READY column matching DESIRED
```

### 4.2 Application health checks
```bash
# Check all application pods
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
# Expected: Minimal or no output

# Test application endpoints
# Replace with your actual application URLs/services
kubectl get services
kubectl get ingress -A
```

### 4.3 Restore any modified PDBs
```bash
# If you relaxed any PDBs during the upgrade, restore them:
kubectl get pdb -A -o wide
# Restore original PDB settings if modified
```

## Final Verification Commands

Run these to confirm the upgrade succeeded:

```bash
# Complete cluster version summary
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Node readiness
kubectl get nodes
kubectl top nodes  # Resource usage

# Pod health across all namespaces  
kubectl get pods -A | grep -v Running | grep -v Completed

# Check for any events indicating problems
kubectl get events -A --sort-by='.lastTimestamp' | tail -20
```

## Expected Timeline

- **Pre-flight checks:** 15 minutes
- **Control plane upgrade:** 15-30 minutes  
- **default-pool upgrade:** 15-30 minutes
- **workload-pool upgrade:** 15-30 minutes
- **Post-upgrade validation:** 15 minutes

**Total time:** 75-120 minutes

## Rollback Plan (if needed)

If critical issues arise, you cannot roll back the control plane from 1.33 to 1.32 easily. However, node pools can be rolled back:

```bash
# Create new node pool at 1.32 (if rollback needed)
gcloud container node-pools create default-pool-rollback \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --node-version 1.32 \
  --num-nodes 3 \
  --machine-type e2-medium

# Cordon problematic pools and migrate workloads
kubectl cordon -l cloud.google.com/gke-nodepool=default-pool
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data
```

## Emergency Contacts

Before starting, ensure:
- [ ] On-call engineer available
- [ ] Escalation path to GKE support defined  
- [ ] Stakeholders notified of maintenance window

**Ready to proceed?** Start with Phase 1 Pre-flight Checks.