# GKE Upgrade Runbook: 1.32 → 1.33

**Cluster:** Standard cluster on Regular channel  
**Location:** us-west1-b (zonal cluster)  
**Current version:** 1.32  
**Target version:** 1.33  
**Node pools:** default-pool, workload-pool  

⚠️ **Important:** This is a **zonal cluster** — during control plane upgrade (~10-15 minutes), you cannot deploy new workloads or modify cluster config, but existing workloads continue running.

## Phase 1: Pre-flight Checks

### 1.1 Verify current state
```bash
# Check current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# List node pools
gcloud container node-pools list --cluster CLUSTER_NAME --zone us-west1-b

# Check cluster health
kubectl get nodes
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed
```

### 1.2 Verify 1.33 is available
```bash
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels)" | grep -A 20 "REGULAR"
```
Look for version 1.33.x in the Regular channel output.

### 1.3 Check for deprecated APIs (critical!)
```bash
# Quick check for deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# If any deprecated APIs found, this must be resolved before upgrading
# The upgrade will fail if deprecated APIs are in use
```

### 1.4 Verify workload health
```bash
# Check for any problematic pod states
kubectl get pods --all-namespaces --field-selector=status.phase!=Running,status.phase!=Succeeded

# Check PodDisruptionBudgets (PDBs) - these control drain behavior
kubectl get pdb --all-namespaces

# List any bare pods (not managed by controllers) - these won't reschedule
kubectl get pods --all-namespaces -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

### 1.5 Check compute quota (for surge nodes)
```bash
# Check current node counts
kubectl get nodes --show-labels | grep node-pool

# Verify you have quota for additional nodes during upgrade
# Default surge will create 1 extra node per pool temporarily
gcloud compute project-info describe --format="yaml(quotas)" | grep -A2 -B2 CPUS
```

## Phase 2: Configure Upgrade Settings

### 2.1 Set maintenance window (recommended)
```bash
# Set weekend maintenance window (Saturday 2-6 AM PST)
gcloud container clusters update CLUSTER_NAME \
  --zone us-west1-b \
  --maintenance-window-start "2024-01-06T10:00:00Z" \
  --maintenance-window-end "2024-01-06T14:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### 2.2 Configure node pool upgrade strategy
```bash
# Set conservative surge settings for default-pool
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Set conservative surge settings for workload-pool  
gcloud container node-pools update workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

## Phase 3: Control Plane Upgrade

### 3.1 Upgrade control plane to 1.33
```bash
# Start control plane upgrade
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version 1.33

# This will prompt for confirmation - type 'y'
```

**Expected behavior:**
- Takes 10-15 minutes
- Existing workloads continue running
- You cannot create new workloads or modify cluster during this time

### 3.2 Monitor control plane upgrade
```bash
# Check upgrade progress
gcloud container operations list --cluster CLUSTER_NAME --zone us-west1-b --limit=5

# Wait for control plane upgrade to complete, then verify
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"
```

### 3.3 Verify control plane health
```bash
# Check system pods are healthy
kubectl get pods -n kube-system

# Verify API server is responding normally
kubectl get nodes
kubectl get namespaces
```

**✅ Control plane upgrade complete when:**
- `currentMasterVersion` shows 1.33.x
- All kube-system pods are Running
- kubectl commands respond normally

## Phase 4: Node Pool Upgrades

**Important:** Control plane must be at 1.33 before upgrading node pools.

### 4.1 Upgrade default-pool
```bash
# Start node pool upgrade
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33
```

### 4.2 Monitor default-pool upgrade
```bash
# Watch node versions change (run in separate terminal)
watch 'kubectl get nodes -o wide --show-labels | grep cloud.google.com/gke-nodepool'

# Check for any stuck pods
kubectl get pods --all-namespaces | grep -E "Terminating|Pending|Evicted"

# Monitor upgrade operation
gcloud container operations list --cluster CLUSTER_NAME --zone us-west1-b --limit=3
```

**During upgrade, you'll see:**
- New nodes appear with version 1.33
- Old nodes marked "SchedulingDisabled" 
- Pods drain from old nodes to new ones
- Old nodes disappear when drain completes

### 4.3 Verify default-pool upgrade
```bash
# Confirm all nodes in default-pool are at 1.33
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool -o wide

# Check no pods are stuck
kubectl get pods --all-namespaces --field-selector=status.phase!=Running,status.phase!=Succeeded
```

### 4.4 Upgrade workload-pool
```bash
# Start workload-pool upgrade
gcloud container node-pools upgrade workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33
```

### 4.5 Monitor workload-pool upgrade
```bash
# Watch progress (same commands as default-pool)
watch 'kubectl get nodes -o wide --show-labels | grep cloud.google.com/gke-nodepool'

kubectl get pods --all-namespaces | grep -E "Terminating|Pending|Evicted"
```

### 4.6 Final verification
```bash
# Confirm all nodes are at 1.33
kubectl get nodes -o wide

# Verify node pool status
gcloud container node-pools list --cluster CLUSTER_NAME --zone us-west1-b

# Check overall cluster health
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed
```

## Phase 5: Post-Upgrade Validation

### 5.1 Cluster health check
```bash
# Verify cluster versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# System pods health
kubectl get pods -n kube-system

# All deployments healthy
kubectl get deployments --all-namespaces | grep -v "READY.*/"
```

### 5.2 Workload validation
```bash
# Check all pods are running
kubectl get pods --all-namespaces --field-selector=status.phase!=Running,status.phase!=Succeeded

# Verify services are responding
kubectl get services --all-namespaces

# Check any ingress/load balancers
kubectl get ingress --all-namespaces
```

### 5.3 Application smoke tests
Run your application-specific health checks here:
- Test application endpoints
- Verify database connections  
- Check monitoring/logging is flowing
- Validate any custom integrations

## Troubleshooting Common Issues

### If upgrade gets stuck with draining pods:

**Symptoms:** Nodes stuck in "SchedulingDisabled" state, pods in "Terminating"

**Diagnosis:**
```bash
# Check which pods are blocking
kubectl get pods --all-namespaces | grep Terminating

# Check PodDisruptionBudgets
kubectl get pdb --all-namespaces -o wide
```

**Fix:** Temporarily relax PDB that's blocking drain:
```bash
# Allow one more disruption temporarily
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":2}}'

# Restore original PDB after upgrade
```

### If new pods are Pending:

**Diagnosis:**
```bash
kubectl describe pod PENDING_POD_NAME -n NAMESPACE
kubectl get events --sort-by='.lastTimestamp' | tail -10
```

**Common causes:**
- Insufficient CPU/memory resources
- Node taints/tolerations mismatch
- Missing storage or network resources

### If you need to cancel the upgrade:
```bash
# List current operations
gcloud container operations list --cluster CLUSTER_NAME --zone us-west1-b

# Note: You cannot cancel a node upgrade once started
# It will complete draining the current node batch, then stop
```

## Expected Timeline

- **Control plane upgrade:** 10-15 minutes
- **Each node pool upgrade:** 5-10 minutes per node (sequential)
- **Total estimated time:** 30-60 minutes depending on node count

## Success Criteria

✅ **Upgrade complete when:**
- Control plane shows version 1.33.x
- All node pools show version 1.33.x  
- All pods are Running (except Completed jobs)
- Applications respond normally to health checks
- No nodes stuck in "SchedulingDisabled" state

---

**Remember:** Replace `CLUSTER_NAME` with your actual cluster name in all commands above. Run commands one at a time and verify each step before proceeding.