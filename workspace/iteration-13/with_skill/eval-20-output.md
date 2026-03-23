# GKE Upgrade Runbook: 1.32 → 1.33
**Cluster:** Standard | **Channel:** Regular | **Zone:** us-west1-b

This runbook covers upgrading both the control plane and node pools from GKE 1.32 to 1.33. Allow 2-3 hours total execution time.

## Pre-flight Checks (15 minutes)

First, let's verify the current state and confirm 1.33 is available.

### 1. Check current versions
```bash
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"
```
**Expected:** Control plane and both node pools should show 1.32.x

### 2. Confirm target version available
```bash
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels.REGULAR.validVersions)" | grep "1\.33"
```
**Expected:** Should see 1.33.x versions listed

### 3. Check for deprecated API usage
```bash
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```
**Expected:** No output (good) or minimal deprecated calls

### 4. Verify cluster health
```bash
# All nodes should be Ready
kubectl get nodes

# No unhealthy pods (ignore Completed/Succeeded)
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded
```

### 5. Check for Pod Disruption Budgets
```bash
kubectl get pdb -A -o wide
```
**Look for:** Any PDBs with ALLOWED DISRUPTIONS = 0 (these may block the upgrade)

**If you see blocked PDBs:** Note them down. We'll address during the upgrade if needed.

### 6. Backup current configuration
```bash
# Save current cluster config
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b > cluster-backup-$(date +%Y%m%d).yaml

# Save all PDB configurations
kubectl get pdb -A -o yaml > pdb-backup-$(date +%Y%m%d).yaml
```

## Phase 1: Control Plane Upgrade (20-30 minutes)

### 1. Upgrade the control plane
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version 1.33
```
**You'll see:** Confirmation prompt. Type `Y` and press Enter.

**Wait time:** 10-15 minutes. The command will show progress.

### 2. Verify control plane upgrade
```bash
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"
```
**Expected:** Should show 1.33.x

### 3. Check system pods
```bash
kubectl get pods -n kube-system
```
**Expected:** All pods should be Running. Some may be restarting (normal).

## Phase 2: Node Pool Upgrades (1-2 hours total)

We'll upgrade one node pool at a time, starting with default-pool.

### Configure surge settings for default-pool

First, let's set conservative surge settings for safe rolling replacement:

```bash
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### Upgrade default-pool
```bash
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33
```
**You'll see:** Confirmation prompt. Type `Y` and press Enter.

### Monitor default-pool progress
Open a second terminal and run this command to watch progress:
```bash
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "NAME|default-pool"'
```

**What you'll see:** 
- Nodes will show "SchedulingDisabled" (being drained)
- New nodes will appear with 1.33.x
- Old nodes will be deleted
- Takes 30-60 minutes depending on workloads

### If the upgrade gets stuck

**Check for pods that won't drain:**
```bash
kubectl get pods -A | grep Terminating
kubectl get events -A --field-selector reason=FailedScheduling --sort-by='.lastTimestamp' | tail -10
```

**Common fix - temporarily relax PDBs:**
```bash
# Find the problematic PDB
kubectl get pdb -A -o wide | grep "0.*0"

# Temporarily allow more disruptions (replace with actual PDB name/namespace)
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"50%"}}'
```

### Verify default-pool upgrade complete
```bash
# All default-pool nodes should show 1.33.x
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool -o wide

# Check for any stuck pods
kubectl get pods -A | grep -E "Terminating|Pending|Error"
```

### Configure surge settings for workload-pool
```bash
gcloud container node-pools update workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### Upgrade workload-pool
```bash
gcloud container node-pools upgrade workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33
```

### Monitor workload-pool progress
```bash
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "NAME|workload-pool"'
```

**Wait time:** Another 30-60 minutes

## Phase 3: Post-Upgrade Validation (10 minutes)

### 1. Verify all versions
```bash
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"
```
**Expected:** Everything should show 1.33.x

### 2. Check all nodes
```bash
kubectl get nodes -o wide
```
**Expected:** All nodes Ready with 1.33.x

### 3. Verify workload health
```bash
# Check deployments
kubectl get deployments -A

# Check for unhealthy pods
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded
```

### 4. Test application connectivity
Replace with your actual application endpoints:
```bash
# Example - test an ingress endpoint
curl -I http://YOUR_APP_ENDPOINT

# Or test a service
kubectl get services -A
```

## Cleanup and Restore

### 1. Restore original PDB settings (if modified)
```bash
kubectl apply -f pdb-backup-$(date +%Y%m%d).yaml
```

### 2. Clean up backup files (optional)
```bash
ls -la *backup*$(date +%Y%m%d).yaml
# Review and delete if no longer needed
```

## Troubleshooting Quick Reference

### Upgrade stuck at "Updating nodes"
```bash
# Check what's blocking drain
kubectl get pods -A | grep Terminating
kubectl describe pdb PDB_NAME -n NAMESPACE

# Common fix - allow more pod disruptions
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

### Pods stuck in Pending
```bash
# Check node resources
kubectl describe nodes | grep -A 5 "Allocated resources"

# Check for scheduling failures
kubectl get events -A --field-selector reason=FailedScheduling
```

### Emergency: Cancel upgrade
```bash
# List operations
gcloud container operations list --cluster CLUSTER_NAME --zone us-west1-b

# Cancel doesn't exist - let current node finish, then it stops
# You can create a new node pool at the old version if needed
```

## Success Checklist
- [ ] Control plane shows 1.33.x
- [ ] Both node pools show 1.33.x  
- [ ] All nodes are Ready
- [ ] No pods in Error/CrashLoopBackOff
- [ ] Applications responding normally
- [ ] PDBs restored to original settings

**Expected total time:** 2-3 hours
**Peak resource usage:** +1 node per pool during surge upgrade (temporary)

The cluster will now automatically receive 1.33 patch updates via the Regular channel. The next minor version (1.34) will arrive ~1 month after it reaches the Regular channel.