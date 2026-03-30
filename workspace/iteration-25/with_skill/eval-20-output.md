# GKE Upgrade Runbook: 1.32 → 1.33

**Cluster:** Standard GKE cluster  
**Channel:** Regular  
**Current Version:** 1.32  
**Target Version:** 1.33  
**Location:** us-west1-b  
**Node Pools:** default-pool, workload-pool  

This runbook assumes auto-upgrades are enabled and 1.33 is available in Regular channel. Total time estimate: 2-4 hours depending on cluster size.

## Phase 1: Pre-Flight Checks (30 minutes)

### 1.1 Verify current cluster state

```bash
# Check current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check available versions in Regular channel
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels)" | grep -A 20 "REGULAR"
```

**Expected:** Control plane and both node pools at 1.32.x. Version 1.33.x should appear in Regular channel's available versions.

### 1.2 Check for deprecated APIs (critical)

```bash
# Check for deprecated API usage (most common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# If the above returns results, get details:
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=us-west1-b \
    --project=PROJECT_ID \
    --filter="category.category:RELIABILITY"
```

**Expected:** No deprecated API usage. If found, fix before proceeding.

### 1.3 Verify cluster health

```bash
# All nodes should be Ready
kubectl get nodes -o wide

# No stuck or failing pods
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded

# System components healthy
kubectl get pods -n kube-system
```

**Expected:** All nodes Ready, no crashlooping pods.

### 1.4 Check workload protection

```bash
# List all PDBs (Pod Disruption Budgets)
kubectl get pdb -A -o wide

# Verify no overly restrictive PDBs (ALLOWED DISRUPTIONS should be > 0)
kubectl describe pdb -A | grep -A 5 -B 5 "Allowed disruptions.*0"
```

**Expected:** PDBs exist for critical workloads but allow at least 1 disruption.

### 1.5 Verify resource capacity

```bash
# Check node resource utilization
kubectl top nodes

# Check for pending pods due to resource constraints
kubectl get pods -A | grep Pending
```

**Expected:** Nodes not over-allocated, no pending pods due to resources.

## Phase 2: Control Plane Upgrade (30-45 minutes)

### 2.1 Upgrade control plane to 1.33

```bash
# Upgrade control plane only (--master flag)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version 1.33

# Confirm when prompted (this takes 10-15 minutes)
```

**During upgrade:** You cannot make cluster configuration changes, but workloads continue running normally.

### 2.2 Verify control plane upgrade

```bash
# Check control plane version (wait until shows 1.33.x)
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"

# Verify system components restarted successfully
kubectl get pods -n kube-system
```

**Expected:** Control plane at 1.33.x, all kube-system pods Running.

## Phase 3: Node Pool Upgrades (1-3 hours)

### 3.1 Configure surge upgrade settings

For most workloads, these conservative settings work well:

```bash
# Configure default-pool surge settings
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Configure workload-pool surge settings  
gcloud container node-pools update workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**What this does:** Upgrades 1 node at a time, creates new node before draining old one (zero downtime).

### 3.2 Upgrade first node pool (default-pool)

```bash
# Start default-pool upgrade
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33

# Confirm when prompted
```

### 3.3 Monitor default-pool upgrade progress

```bash
# Monitor nodes (run this in a separate terminal)
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check for any stuck pods during upgrade
kubectl get pods -A | grep -E "Terminating|Pending|ContainerCreating"

# Monitor upgrade operation status
gcloud container operations list --cluster CLUSTER_NAME --zone us-west1-b --limit=3
```

**What to expect:** 
- Nodes will show "Ready,SchedulingDisabled" when cordoned
- New nodes appear with version 1.33.x
- Pods migrate automatically to new nodes
- Old nodes disappear when drained

### 3.4 Wait for default-pool completion

Wait until:
```bash
# All default-pool nodes show version 1.33.x
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool -o wide
```

**Expected:** All default-pool nodes at 1.33.x, all pods rescheduled successfully.

### 3.5 Upgrade second node pool (workload-pool)

```bash
# Start workload-pool upgrade
gcloud container node-pools upgrade workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33

# Confirm when prompted
```

### 3.6 Monitor workload-pool upgrade

```bash
# Monitor progress (same commands as before)
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Verify workloads remain healthy during upgrade
kubectl get deployments -A
kubectl get statefulsets -A
```

## Phase 4: Post-Upgrade Validation (15 minutes)

### 4.1 Verify all components upgraded

```bash
# Check all versions match target
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# All nodes should be 1.33.x
kubectl get nodes -o wide
```

**Expected:** Control plane and all node pools at 1.33.x.

### 4.2 Validate cluster health

```bash
# No failing pods
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded

# System components healthy
kubectl get pods -n kube-system

# Check for any events indicating problems
kubectl get events -A --sort-by='.lastTimestamp' | tail -20
```

### 4.3 Application smoke tests

```bash
# Test pod scheduling works
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Upgrade successful"

# Verify ingress/services responding (replace with your app endpoints)
# curl http://YOUR_APP_ENDPOINT/health

# Check any critical application health endpoints
```

## Phase 5: Cleanup and Documentation

### 5.1 Final verification

```bash
# Confirm no resource issues
kubectl top nodes
kubectl get pdb -A -o wide

# Document the upgrade
echo "Cluster CLUSTER_NAME upgraded from 1.32 to 1.33 on $(date)" >> upgrade-log.txt
```

## Troubleshooting Common Issues

### If upgrade gets stuck:

**Problem:** Pods won't drain from nodes
```bash
# Check what's blocking drain
kubectl describe pdb -A
kubectl get pods -A -o json | jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

**Fix:** Temporarily relax PDBs or delete bare pods:
```bash
kubectl patch pdb PDB_NAME -n NAMESPACE -p '{"spec":{"maxUnavailable":"100%"}}'
```

**Problem:** "Insufficient resources" errors
```bash
# Check resource usage
kubectl top nodes
kubectl describe nodes | grep -A 5 "Allocated resources"
```

**Fix:** Scale down non-critical workloads temporarily:
```bash
kubectl scale deployment NON_CRITICAL_APP --replicas=0 -n NAMESPACE
```

### Emergency rollback (if needed):

**Control plane rollback:** Contact GKE support - not user-initiated.

**Node pool rollback:** Create new pool at old version and migrate:
```bash
gcloud container node-pools create rollback-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.32 \
  --num-nodes 3
```

## Success Criteria

✅ Control plane version: 1.33.x  
✅ All node pools version: 1.33.x  
✅ All nodes Status: Ready  
✅ No CrashLoopBackOff or Pending pods  
✅ Applications responding normally  

**Estimated total time:** 2-4 hours depending on cluster size and workload complexity.

**Next steps:** Monitor applications for 24-48 hours post-upgrade. Set up maintenance windows to control timing of future auto-upgrades.