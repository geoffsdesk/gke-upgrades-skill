# GKE Upgrade Runbook: 1.32 → 1.33

**Cluster:** Standard cluster on Regular channel  
**Current version:** 1.32  
**Target version:** 1.33  
**Location:** us-west1-b (zonal)  
**Node pools:** default-pool, workload-pool  

This runbook assumes you have `gcloud` and `kubectl` configured and cluster admin access.

## Pre-flight Checks (30 minutes)

### 1. Verify current state
```bash
# Get current cluster and node versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check all nodes are Ready
kubectl get nodes -o wide

# Check for any failing pods
kubectl get pods -A | grep -v Running | grep -v Completed
```

**Expected:** All nodes show Ready, minimal non-Running pods.

### 2. Check version availability
```bash
# Verify 1.33 is available in Regular channel
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels.REGULAR.validVersions)"
```

**Expected:** 1.33.x appears in the list.

### 3. Check for deprecated API usage
```bash
# Quick check for deprecated API calls
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```

**Expected:** No output (good) or minimal deprecated usage. If you see many deprecated API calls, pause and investigate further.

### 4. Verify workload health
```bash
# Check PodDisruptionBudgets aren't too restrictive
kubectl get pdb -A -o wide

# Look for bare pods (not managed by controllers)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Check resource usage
kubectl top nodes
kubectl top pods -A --sort-by=cpu | head -10
```

**Action required if:**
- PDBs show "ALLOWED DISRUPTIONS: 0" — you'll need to temporarily relax them
- Bare pods exist — they won't be rescheduled during upgrade
- Nodes are >80% CPU/memory — upgrade may cause scheduling issues

## Step 1: Control Plane Upgrade (15-20 minutes)

### Start the control plane upgrade
```bash
# Upgrade control plane to 1.33
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version 1.33

# When prompted, type 'y' to confirm
```

**What happens:** GKE upgrades the API server. Since this is a zonal cluster, expect 2-5 minutes of API unavailability. Workloads keep running.

### Monitor progress
```bash
# Check upgrade status (run this every 2-3 minutes)
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --limit 1

# Once operation shows DONE, verify control plane version
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"
```

**Expected:** Output shows `1.33.x-gke.xxxx`

### Verify control plane health
```bash
# Check system pods are healthy
kubectl get pods -n kube-system

# Test API responsiveness
kubectl get nodes
kubectl get namespaces
```

**Expected:** All kube-system pods Running, API responds normally.

## Step 2: Configure Node Pool Upgrade Strategy

Before upgrading nodes, set surge parameters for each pool. These control how many nodes upgrade simultaneously.

### Default-pool configuration
```bash
# Set conservative surge settings (1 node at a time, no unavailable)
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### Workload-pool configuration
```bash
# Set conservative surge settings
gcloud container node-pools update workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Why these settings:** `maxSurge=1` creates 1 extra node before draining old ones. `maxUnavailable=0` ensures no capacity loss during upgrade. This is slower but safest for first-time upgraders.

## Step 3: Upgrade Node Pools (30-60 minutes per pool)

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
# Watch node versions (run in separate terminal)
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check upgrade operation status
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --limit 1
```

**What to watch for:**
- New nodes appear with 1.33.x version
- Old nodes get cordoned (SchedulingDisabled)
- Pods drain from old nodes to new nodes
- Old nodes disappear

### If upgrade gets stuck
Common issues and quick fixes:

**PDB blocking drain:**
```bash
# Check which PDBs are blocking
kubectl get pdb -A -o wide

# If a PDB shows "ALLOWED DISRUPTIONS: 0", temporarily relax it:
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

**Pods pending due to resource constraints:**
```bash
# Check what's pending
kubectl get pods -A | grep Pending
kubectl get events -A --field-selector reason=FailedScheduling | tail -5

# If needed, scale down non-critical workloads temporarily
kubectl scale deployment NON_CRITICAL_DEPLOYMENT --replicas=0 -n NAMESPACE
```

### Wait for default-pool completion
```bash
# Verify all default-pool nodes are at 1.33
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool -o wide

# Check no pods are stuck
kubectl get pods -A | grep -E "Terminating|Pending"
```

**Don't proceed until default-pool upgrade is complete.**

### Upgrade workload-pool
```bash
# Start workload-pool upgrade
gcloud container node-pools upgrade workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33
```

### Monitor workload-pool upgrade
```bash
# Watch progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Monitor for any stuck operations
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --limit 1
```

## Step 4: Post-Upgrade Validation (10 minutes)

### Verify cluster state
```bash
# Confirm all nodes at target version
kubectl get nodes -o wide

# Check node pool versions
gcloud container node-pools list --cluster CLUSTER_NAME --zone us-west1-b

# Verify control plane version
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"
```

**Expected:** All output shows 1.33.x versions.

### Verify workload health
```bash
# Check all pods are running
kubectl get pods -A | grep -v Running | grep -v Completed

# Verify deployments are at desired replica count
kubectl get deployments -A

# Check StatefulSets if you have any
kubectl get statefulsets -A

# Test a sample application endpoint (replace with your app)
kubectl get services -A
# curl http://SERVICE_IP:PORT/health  # if you have health endpoints
```

### Check system health
```bash
# Verify system pods
kubectl get pods -n kube-system | grep -v Running

# Check for any admission webhook issues
kubectl get events -A --field-selector type=Warning | grep webhook | tail -5

# Verify DNS resolution
kubectl run test-pod --image=busybox --rm -it --restart=Never -- nslookup kubernetes.default.svc.cluster.local
```

**Expected:** All system pods Running, DNS resolves correctly.

## Step 5: Cleanup and Documentation

### Restore any temporarily modified PDBs
```bash
# If you relaxed any PDBs during the upgrade, restore them:
# kubectl patch pdb PDB_NAME -n NAMESPACE -p '{"spec":{"maxUnavailable":"ORIGINAL_VALUE"}}'

# Scale back any deployments you scaled down
# kubectl scale deployment DEPLOYMENT_NAME --replicas=ORIGINAL_COUNT -n NAMESPACE
```

### Document the upgrade
Create a record with:
- Start time and duration
- Any issues encountered and how they were resolved  
- Current cluster versions
- Next upgrade target (GKE will auto-upgrade to newer 1.33 patches)

## Emergency Rollback (if needed)

**Important:** Control plane cannot be downgraded from 1.33 back to 1.32 without GKE support involvement. Node pools can be rolled back during an in-progress upgrade.

### Cancel in-progress node pool upgrade
```bash
# This will finish the current node and stop
gcloud container operations list --cluster CLUSTER_NAME --zone us-west1-b
# Note the operation ID, then contact GKE support
```

### For post-upgrade issues
If you discover issues after the upgrade completes:
1. Document the specific problem and error messages
2. Check GKE release notes for known issues with your target version
3. Consider creating a new node pool at 1.32 and migrating workloads back (complex process)
4. Contact Cloud Support with cluster details

## Timeline Expectations

- **Control plane upgrade:** 15-20 minutes
- **Each node pool upgrade:** 30-60 minutes (depends on node count and pod drain time)
- **Total time:** 1.5-2 hours for a typical 2-pool cluster

## When to Get Help

Contact Cloud Support if:
- Any operation is stuck for >2 hours with no progress
- Control plane upgrade fails or API becomes permanently unavailable
- You see repeated node creation failures
- Critical workloads are down after following this runbook

## Success Criteria

✅ Control plane at 1.33.x  
✅ All nodes at 1.33.x  
✅ All pods Running (except Jobs/CronJobs)  
✅ Applications responding normally  
✅ No stuck operations  

**Congratulations!** Your cluster is now on GKE 1.33. It will auto-upgrade to newer 1.33 patch versions and eventually to 1.34 according to your Regular channel schedule.