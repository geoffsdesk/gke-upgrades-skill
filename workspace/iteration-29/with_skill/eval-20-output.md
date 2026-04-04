# GKE Upgrade Runbook: 1.32 → 1.33

**Cluster:** Standard | **Channel:** Regular | **Location:** us-west1-b  
**Current:** 1.32 | **Target:** 1.33 | **Node Pools:** default-pool, workload-pool

⚠️ **Important:** This upgrade follows GKE best practices with auto-upgrade controls. Since you're on the Regular channel, this upgrade will happen automatically unless you control the timing with maintenance windows or exclusions.

## Phase 1: Pre-Flight Checks (15 minutes)

### 1.1 Verify current cluster state
```bash
# Get current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed
```
**Expected:** All nodes show Ready, minimal non-Running pods (only DaemonSet terminating pods are OK).

### 1.2 Check version availability
```bash
# Confirm 1.33 is available in Regular channel
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels.REGULAR.validVersions)" | grep "1\.33"
```
**Expected:** Should show 1.33.x versions available.

### 1.3 Check for deprecated APIs (critical!)
```bash
# Check for deprecated API usage - most common upgrade blocker
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# If any deprecated APIs found, also check GKE insights
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=us-west1-b \
    --project=PROJECT_ID \
    --filter="category.category:RELIABILITY"
```
**Expected:** No output (no deprecated APIs). If you see deprecated API usage, **STOP** and remediate those first.

### 1.4 Verify workload readiness
```bash
# Check for PDBs that might block drain
kubectl get pdb -A -o wide

# Check for bare pods (won't be rescheduled)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Check resource pressure
kubectl top nodes
```

**Expected:** 
- PDBs show ALLOWED DISRUPTIONS > 0
- No bare pods (or acceptable to lose them)
- Node CPU/memory utilization < 80%

### 1.5 Backup critical data
```bash
# For any StatefulSets with persistent data, verify backup strategy
kubectl get statefulsets -A
kubectl get pv -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy

# Recommended: Take application-level backups now
# Example for databases: pg_dump, mysqldump, elasticsearch snapshot, etc.
```

## Phase 2: Configure Upgrade Strategy (10 minutes)

### 2.1 Set maintenance window (optional but recommended)
```bash
# Set upgrade window to Saturday 2-6 AM Pacific (helps control auto-upgrade timing)
gcloud container clusters update CLUSTER_NAME \
  --zone us-west1-b \
  --maintenance-window-start "2024-01-06T10:00:00Z" \
  --maintenance-window-end "2024-01-06T14:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### 2.2 Configure node pool upgrade settings
```bash
# Default pool - conservative settings for system workloads
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Workload pool - slightly more aggressive (adjust based on your workloads)
gcloud container node-pools update workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

**Why these settings:**
- `maxSurge=1-2`: Creates 1-2 extra nodes during upgrade (needs quota)
- `maxUnavailable=0`: No nodes become unavailable (zero-downtime)
- Conservative for first upgrade; you can increase `maxSurge` later for speed

## Phase 3: Control Plane Upgrade (20 minutes)

⚠️ **Critical:** Control plane MUST be upgraded before node pools.

### 3.1 Start control plane upgrade
```bash
# Upgrade control plane to 1.33
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version 1.33

# Answer "Y" when prompted
```

**Expected duration:** 10-15 minutes. You'll see "Upgrading master..." output.

### 3.2 Monitor control plane upgrade
```bash
# Check upgrade progress (run every 2-3 minutes)
gcloud container operations list --cluster CLUSTER_NAME --zone us-west1-b --limit=3

# Check current master version (should change to 1.33.x when done)
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"
```

### 3.3 Verify control plane health
```bash
# Once master shows 1.33.x, verify system components
kubectl get pods -n kube-system
kubectl get nodes

# Test API responsiveness
kubectl get namespaces
```

**Expected:** All kube-system pods Running, all nodes still Ready, API responds normally.

## Phase 4: Node Pool Upgrades (45-60 minutes)

### 4.1 Upgrade default-pool first
```bash
# Start default-pool upgrade
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b

# Answer "Y" when prompted
```

### 4.2 Monitor default-pool upgrade
```bash
# Watch node versions change (run every 5 minutes)
kubectl get nodes -o wide --show-labels | grep "nodepool=default-pool"

# Monitor for stuck pods
kubectl get pods -A | grep -E "Terminating|Pending|ContainerCreating"

# Check upgrade operation status
gcloud container operations list --cluster CLUSTER_NAME --zone us-west1-b --limit=1
```

**What you'll see:** Nodes will show "SchedulingDisabled" → "Ready" with new version. Pods will move to new nodes automatically.

### 4.3 Troubleshooting if stuck
If upgrade stalls for >30 minutes:

```bash
# Check PDB violations
kubectl get events -A --field-selector reason=EvictionBlocked
kubectl get pdb -A -o wide

# Check resource constraints
kubectl describe nodes | grep -A 5 "Allocated resources"

# Check pod events
kubectl get events -A --sort-by=.lastTimestamp | tail -20
```

**Common fixes:**
- PDB too restrictive: `kubectl patch pdb PDB_NAME -n NAMESPACE -p '{"spec":{"maxUnavailable":"50%"}}'`
- No room for pods: Scale down non-critical workloads temporarily
- Pods won't terminate: Check `terminationGracePeriodSeconds` in pod specs

### 4.4 Upgrade workload-pool
```bash
# Once default-pool shows all nodes at 1.33.x, start workload-pool
gcloud container node-pools upgrade workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b

# Monitor same as default-pool
kubectl get nodes -o wide --show-labels | grep "nodepool=workload-pool"
```

## Phase 5: Post-Upgrade Validation (15 minutes)

### 5.1 Verify all versions upgraded
```bash
# Final version check - should show 1.33.x everywhere
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# All nodes at target version
kubectl get nodes -o wide
```

### 5.2 Verify workload health
```bash
# Check all pods running
kubectl get pods -A | grep -v Running | grep -v Completed

# Check deployments at desired scale
kubectl get deployments -A

# Check StatefulSets ready
kubectl get statefulsets -A
```

### 5.3 Application smoke tests
```bash
# Test your applications - examples:
curl http://YOUR_SERVICE_ENDPOINT/health
kubectl port-forward service/YOUR_SERVICE 8080:80
# Browse to http://localhost:8080

# Check ingress/load balancer status
kubectl get ingress -A
kubectl get services -A --field-selector spec.type=LoadBalancer
```

### 5.4 Verify no stuck resources
```bash
# Final health check
kubectl get events -A --field-selector type=Warning | tail -10
kubectl get pdb -A -o wide

# Check for any remaining issues
kubectl describe nodes | grep -E "Conditions|Events" -A 5
```

## Phase 6: Cleanup & Documentation (5 minutes)

### 6.1 Clean up temporary changes
```bash
# If you temporarily modified PDBs, restore them:
kubectl apply -f your-original-pdb-backup.yaml

# Verify maintenance window is still configured
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="yaml(maintenancePolicy)"
```

### 6.2 Document completion
Create a completion record:
```
✅ GKE Upgrade Completed
- Date: $(date)
- Cluster: CLUSTER_NAME in us-west1-b
- Upgraded: 1.32 → 1.33
- Control plane duration: ___ minutes
- Node upgrades duration: ___ minutes
- Issues encountered: ___
- Resolution: ___
```

## Emergency Rollback (if needed)

**Control plane:** Cannot downgrade easily. Contact Google Cloud Support if critical issues.

**Node pools:** Create new pools at old version:
```bash
# Emergency rollback - create new pool at 1.32
gcloud container node-pools create rollback-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.32.x \
  --num-nodes 3 \
  --machine-type e2-medium

# Cordon upgraded nodes
kubectl cordon -l cloud.google.com/gke-nodepool=workload-pool

# Migrate critical workloads manually, then delete old pool
```

## Success Criteria
- ✅ Control plane at 1.33.x
- ✅ Both node pools at 1.33.x  
- ✅ All pods Running or Completed
- ✅ Applications responding normally
- ✅ No Warning events in past 15 minutes

**Total estimated time:** 90-120 minutes

**Next steps:** Consider setting up automated upgrades with maintenance windows to avoid manual upgrades in the future. Your cluster will auto-upgrade to future 1.33 patches and eventually to 1.34 when it becomes available in Regular channel.