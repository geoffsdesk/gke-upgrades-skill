# GKE Cluster Upgrade Runbook: 1.31 to 1.32

## Prerequisites
- `gcloud` CLI installed and authenticated
- `kubectl` configured to access your cluster
- Basic understanding of your applications and workloads

## Phase 1: Pre-Upgrade Assessment

### Step 1: Set Environment Variables
```bash
export PROJECT_ID="your-project-id"
export CLUSTER_NAME="your-cluster-name"
export ZONE="us-west1-b"
```

### Step 2: Verify Current Cluster State
```bash
# Get current cluster version
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID | grep -E "currentMasterVersion|currentNodeVersion"

# List all node pools and their versions
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID

# Check cluster health
kubectl get nodes -o wide
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed
```

### Step 3: Check Available Versions
```bash
# List available versions for Regular channel
gcloud container get-server-config --zone=$ZONE --project=$PROJECT_ID | grep -A 20 "Regular channel"
```

### Step 4: Backup Critical Resources
```bash
# Create backup directory
mkdir -p cluster-backup-$(date +%Y%m%d)
cd cluster-backup-$(date +%Y%m%d)

# Backup cluster configuration
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID > cluster-config-backup.yaml

# Backup all namespaces and resources
kubectl get all --all-namespaces -o yaml > all-resources-backup.yaml
kubectl get configmaps --all-namespaces -o yaml > configmaps-backup.yaml
kubectl get secrets --all-namespaces -o yaml > secrets-backup.yaml
kubectl get pvc --all-namespaces -o yaml > pvc-backup.yaml

# List custom resources
kubectl api-resources --verbs=list --namespaced -o name | xargs -n 1 kubectl get --show-kind --ignore-not-found --all-namespaces > custom-resources-backup.yaml
```

### Step 5: Check for Breaking Changes
```bash
# Check for deprecated APIs
kubectl api-versions | sort

# Check workloads for deprecated API usage
kubectl get deployments,replicasets,daemonsets,statefulsets --all-namespaces -o yaml | grep -i "apiVersion"
```

## Phase 2: Control Plane Upgrade

### Step 6: Upgrade Control Plane to 1.32
```bash
# Get the exact 1.32 version available
AVAILABLE_VERSION=$(gcloud container get-server-config --zone=$ZONE --project=$PROJECT_ID --format="value(channels.REGULAR.validMasterVersions)" | tr ';' '\n' | grep "1.32" | head -1)

echo "Upgrading to version: $AVAILABLE_VERSION"

# Start control plane upgrade
gcloud container clusters upgrade $CLUSTER_NAME --master --cluster-version=$AVAILABLE_VERSION --zone=$ZONE --project=$PROJECT_ID
```

**⚠️ Important:** This command will prompt for confirmation. Type 'Y' to proceed.

### Step 7: Monitor Control Plane Upgrade
```bash
# Check upgrade status (run every 2-3 minutes)
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID | grep -E "status|currentMasterVersion"

# Verify API server accessibility
kubectl get nodes
kubectl cluster-info
```

**Wait for control plane upgrade to complete before proceeding (typically 10-20 minutes).**

## Phase 3: Node Pool Upgrades

### Step 8: Upgrade default-pool
```bash
# Check current node pool version
gcloud container node-pools describe default-pool --cluster=$CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID | grep version

# Get number of nodes in pool for monitoring
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool

# Start default-pool upgrade
gcloud container clusters upgrade $CLUSTER_NAME --node-pool=default-pool --zone=$ZONE --project=$PROJECT_ID
```

### Step 9: Monitor default-pool Upgrade
```bash
# Monitor node upgrade progress
watch kubectl get nodes -o wide

# Check pod rescheduling
kubectl get pods --all-namespaces -o wide | grep default-pool

# Check for any failed pods
kubectl get pods --all-namespaces | grep -E "Error|CrashLoopBackOff|Pending"
```

### Step 10: Verify default-pool Upgrade
```bash
# Verify all nodes in default-pool are upgraded
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool -o jsonpath='{.items[*].status.nodeInfo.kubeletVersion}'

# Check cluster health
kubectl get componentstatuses
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed
```

### Step 11: Upgrade workload-pool
```bash
# Check current node pool version
gcloud container node-pools describe workload-pool --cluster=$CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID | grep version

# Get number of nodes in pool for monitoring
kubectl get nodes -l cloud.google.com/gke-nodepool=workload-pool

# Start workload-pool upgrade
gcloud container clusters upgrade $CLUSTER_NAME --node-pool=workload-pool --zone=$ZONE --project=$PROJECT_ID
```

### Step 12: Monitor workload-pool Upgrade
```bash
# Monitor node upgrade progress
watch kubectl get nodes -o wide

# Check pod rescheduling
kubectl get pods --all-namespaces -o wide | grep workload-pool

# Check for any failed pods
kubectl get pods --all-namespaces | grep -E "Error|CrashLoopBackOff|Pending"
```

## Phase 4: Post-Upgrade Verification

### Step 13: Comprehensive Health Check
```bash
# Verify all components are upgraded
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID | grep -E "currentMasterVersion|currentNodeVersion"

# Check all nodes are ready and on correct version
kubectl get nodes -o wide

# Verify all node pools
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID

# Check system pods
kubectl get pods -n kube-system

# Check all application pods
kubectl get pods --all-namespaces
```

### Step 14: Application Health Verification
```bash
# Check deployment status
kubectl get deployments --all-namespaces

# Check service availability
kubectl get services --all-namespaces

# Check ingress resources
kubectl get ingress --all-namespaces

# Test a few critical application endpoints
kubectl get pods -o wide | head -10
```

### Step 15: Performance and Resource Check
```bash
# Check resource usage
kubectl top nodes
kubectl top pods --all-namespaces

# Check events for any issues
kubectl get events --sort-by=.metadata.creationTimestamp --all-namespaces | tail -20

# Check storage
kubectl get pv,pvc --all-namespaces
```

## Phase 5: Final Cleanup and Documentation

### Step 16: Clean Up and Document
```bash
# Save final cluster state
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID > cluster-config-post-upgrade.yaml

# Document the upgrade
echo "Upgrade completed on $(date)" > upgrade-log.txt
echo "Upgraded from 1.31 to $AVAILABLE_VERSION" >> upgrade-log.txt
kubectl get nodes -o jsonpath='{.items[*].status.nodeInfo.kubeletVersion}' >> upgrade-log.txt
```

## Troubleshooting Commands

If you encounter issues:

```bash
# Check cluster operations status
gcloud container operations list --zone=$ZONE --project=$PROJECT_ID

# Get detailed operation info (replace OPERATION_ID)
gcloud container operations describe OPERATION_ID --zone=$ZONE --project=$PROJECT_ID

# Check node pool status
kubectl describe nodes

# Check for resource constraints
kubectl describe pods <pod-name> -n <namespace>

# Check cluster events
kubectl get events --sort-by=.metadata.creationTimestamp -A

# Rollback if necessary (only for node pools, not control plane)
gcloud container node-pools rollback NODE_POOL_NAME --cluster=$CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID
```

## Expected Timeline
- **Control Plane Upgrade:** 10-20 minutes
- **Node Pool Upgrades:** 15-30 minutes per pool (depending on size)
- **Total Time:** 45-90 minutes

## Critical Notes
1. **No Control Plane Rollback:** Control plane upgrades cannot be rolled back
2. **Workload Disruption:** Pods will be rescheduled during node upgrades
3. **Regular Channel:** Upgrades are automatic; manual upgrades should align with channel versions
4. **Backup First:** Always backup critical data before starting
5. **Test Applications:** Verify your applications work correctly after upgrade

**Stop immediately and investigate if:**
- Control plane upgrade fails
- Nodes fail to join the cluster
- Critical applications don't start after upgrade
- Persistent volume claims fail to mount

This runbook provides a safe, step-by-step approach to upgrading your GKE cluster. Take your time with each phase and don't proceed if you encounter unexpected issues.