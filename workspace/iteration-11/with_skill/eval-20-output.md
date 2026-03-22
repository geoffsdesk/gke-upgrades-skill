# GKE Upgrade Runbook: 1.32 → 1.32 (Patch Upgrade)

## Overview
- **Cluster**: Standard cluster on Regular channel
- **Current version**: 1.32.x
- **Target version**: 1.32.latest (patch upgrade)
- **Location**: us-west1-b
- **Node pools**: default-pool, workload-pool

This is a **patch upgrade** (staying within the same minor version). Patch upgrades are low-risk and typically include security fixes and bug patches.

## Pre-flight Checks (15 minutes)

### 1. Verify current cluster state
```bash
# Check current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Expected: Control plane and nodes both on 1.32.x
```

### 2. Check what target version is available
```bash
# See available versions in Regular channel
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels.REGULAR.validVersions)" | grep "1.32"

# Note the latest 1.32.x version - this will be your target
```

### 3. Verify cluster health
```bash
# All nodes should be Ready
kubectl get nodes

# No failing pods (ignore Completed pods)
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded

# System pods healthy
kubectl get pods -n kube-system

# If any pods are not Running, investigate before proceeding
```

### 4. Check for any deprecated APIs (unlikely for patch upgrade)
```bash
# This command may return "not found" - that's OK
kubectl get --raw /metrics 2>/dev/null | grep apiserver_request_total | grep deprecated || echo "No deprecated API usage found"
```

### 5. Document baseline metrics
```bash
# Count current pods for comparison later
kubectl get pods -A --no-headers | wc -l

# Save this number - you should have the same count after upgrade
```

## Phase 1: Control Plane Upgrade (10-15 minutes)

### Step 1: Upgrade the control plane
```bash
# Replace CLUSTER_NAME with your actual cluster name
# Replace TARGET_VERSION with the latest 1.32.x from step 2 above
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version TARGET_VERSION

# You'll be prompted to confirm - type 'y'
# This takes 10-15 minutes typically
```

### Step 2: Monitor control plane upgrade
```bash
# Check upgrade progress (run every few minutes)
gcloud container operations list \
  --filter="operationType=UPGRADE_MASTER" \
  --limit=1

# Status should show RUNNING, then DONE when complete
```

### Step 3: Verify control plane upgrade
```bash
# Confirm control plane is at target version
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"

# Check system pods restarted successfully
kubectl get pods -n kube-system

# All kube-system pods should be Running
```

## Phase 2: Node Pool Upgrades (20-40 minutes per pool)

### Step 1: Configure surge settings for faster upgrades
```bash
# Set conservative surge for default-pool (likely has system workloads)
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Set higher surge for workload-pool (can handle more disruption)
gcloud container node-pools update workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

### Step 2: Upgrade default-pool first
```bash
# Start node pool upgrade
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version TARGET_VERSION

# You'll be prompted to confirm - type 'y'
```

### Step 3: Monitor default-pool upgrade
```bash
# Watch node upgrade progress (run this in a separate terminal if possible)
watch 'kubectl get nodes -o wide'

# You'll see nodes with different versions during the upgrade
# Old nodes will show as Ready, then NotReady, then disappear
# New nodes will appear as NotReady, then Ready

# Check for any stuck pods
kubectl get pods -A | grep -E "Pending|Terminating|CrashLoopBackOff"
```

### Step 4: Verify default-pool upgrade completion
```bash
# All nodes should be at target version
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool -o wide

# Verify node pool version
gcloud container node-pools describe default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(version)"
```

### Step 5: Upgrade workload-pool
```bash
# Start workload-pool upgrade
gcloud container node-pools upgrade workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version TARGET_VERSION

# Confirm when prompted
```

### Step 6: Monitor workload-pool upgrade
```bash
# Watch progress
watch 'kubectl get nodes -o wide'

# Check for stuck pods
kubectl get pods -A | grep -E "Pending|Terminating|CrashLoopBackOff"

# If you see pods stuck in Terminating for >10 minutes, see troubleshooting section
```

### Step 7: Verify workload-pool upgrade completion
```bash
# All nodes should be at target version
kubectl get nodes -l cloud.google.com/gke-nodepool=workload-pool -o wide

# Verify node pool version
gcloud container node-pools describe workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(version)"
```

## Phase 3: Post-Upgrade Validation (10 minutes)

### Step 1: Verify cluster health
```bash
# All nodes Ready at target version
kubectl get nodes

# All expected pods running
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded

# Should be empty or only show recently completed jobs
```

### Step 2: Check system components
```bash
# System pods healthy
kubectl get pods -n kube-system

# DNS working
kubectl run test-dns --image=busybox --rm -it --restart=Never -- nslookup kubernetes.default

# Should resolve successfully, then pod auto-deletes
```

### Step 3: Verify workload health
```bash
# Check deployments are at desired replica count
kubectl get deployments -A

# Check any StatefulSets
kubectl get statefulsets -A

# Verify pod count matches pre-upgrade baseline
kubectl get pods -A --no-headers | wc -l
```

### Step 4: Final cluster status
```bash
# Complete version status
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Everything should show TARGET_VERSION
```

## Troubleshooting Common Issues

### Pods stuck in Terminating
```bash
# Check which pods are stuck
kubectl get pods -A | grep Terminating

# Check if PodDisruptionBudgets are too restrictive
kubectl get pdb -A

# If PDB shows ALLOWED DISRUPTIONS = 0, temporarily increase it:
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"100%"}}'

# Remember to restore the original PDB after upgrade
```

### Pods stuck in Pending
```bash
# Check why pods can't schedule
kubectl describe pods POD_NAME -n NAMESPACE

# Usually means not enough resources - increase maxSurge:
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

### Upgrade appears stuck
```bash
# Check operation status
gcloud container operations list --cluster CLUSTER_NAME --zone us-west1-b --limit=5

# If operation is RUNNING for >2 hours, check pod issues above
# If no pod issues and still stuck, contact Google Cloud Support
```

## Important Notes

1. **This is a patch upgrade** - very low risk, mainly security and bug fixes
2. **Estimated total time**: 45-90 minutes depending on cluster size
3. **No application changes needed** - workloads will restart on new nodes automatically
4. **Rollback**: For patch versions, you can downgrade the control plane if needed by contacting Google Cloud Support
5. **Future upgrades**: Your cluster will auto-upgrade to newer patches in the Regular channel unless you configure maintenance exclusions

## Completion Checklist

- [ ] Control plane upgraded to target version
- [ ] Both node pools upgraded to target version  
- [ ] All nodes showing Ready status
- [ ] All system pods running in kube-system namespace
- [ ] Application pods running with same count as pre-upgrade
- [ ] DNS resolution test passed
- [ ] No pods stuck in Pending/Terminating status

Your cluster upgrade is complete! The cluster will continue to receive automatic patch updates in the future according to the Regular channel schedule.