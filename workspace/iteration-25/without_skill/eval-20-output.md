# GKE Cluster Upgrade Runbook: 1.32 → 1.33

## Prerequisites
- `kubectl` configured to access your cluster
- `gcloud` CLI installed and authenticated
- Basic understanding of your workloads running on the cluster

## Phase 1: Pre-Upgrade Assessment and Backup

### Step 1: Verify Current Cluster State
```bash
# Set your project and cluster variables
export PROJECT_ID="your-project-id"
export CLUSTER_NAME="your-cluster-name"
export ZONE="us-west1-b"

# Verify cluster details
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID

# Check current versions
gcloud container clusters list --filter="name=$CLUSTER_NAME"

# Verify node pool versions
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE
```

### Step 2: Check Available Versions
```bash
# Check available master versions
gcloud container get-server-config --zone=$ZONE --format="value(validMasterVersions[0:5])"

# Verify 1.33 is available
gcloud container get-server-config --zone=$ZONE --format="yaml(validMasterVersions)" | grep "1.33"
```

### Step 3: Document Current Workloads
```bash
# List all namespaces
kubectl get namespaces

# List all deployments across namespaces
kubectl get deployments --all-namespaces -o wide

# List all daemonsets
kubectl get daemonsets --all-namespaces -o wide

# List all statefulsets
kubectl get statefulsets --all-namespaces -o wide

# Check node status and capacity
kubectl get nodes -o wide

# Check pod distribution across nodes
kubectl get pods --all-namespaces -o wide | grep -v Completed
```

### Step 4: Backup Critical Resources
```bash
# Create backup directory
mkdir -p gke-upgrade-backup-$(date +%Y%m%d)
cd gke-upgrade-backup-$(date +%Y%m%d)

# Backup cluster configuration
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE > cluster-config-backup.yaml

# Backup all deployments
kubectl get deployments --all-namespaces -o yaml > deployments-backup.yaml

# Backup all services
kubectl get services --all-namespaces -o yaml > services-backup.yaml

# Backup all configmaps
kubectl get configmaps --all-namespaces -o yaml > configmaps-backup.yaml

# Backup all secrets (metadata only, not the actual secret data)
kubectl get secrets --all-namespaces -o yaml > secrets-backup.yaml

# Backup persistent volume claims
kubectl get pvc --all-namespaces -o yaml > pvc-backup.yaml
```

### Step 5: Check for Deprecated APIs
```bash
# Check for deprecated APIs that might break in 1.33
kubectl api-versions

# Check for any deprecated resources in your current manifests
# Look for any warnings when running:
kubectl get all --all-namespaces
```

## Phase 2: Master Upgrade

### Step 6: Upgrade Control Plane
```bash
# Upgrade the master to 1.33 (this will automatically select the latest 1.33 patch version)
gcloud container clusters upgrade $CLUSTER_NAME \
  --zone=$ZONE \
  --master \
  --cluster-version=1.33 \
  --project=$PROJECT_ID

# This will take 10-20 minutes. Monitor progress:
gcloud container operations list --zone=$ZONE --filter="targetLink~$CLUSTER_NAME"
```

### Step 7: Verify Master Upgrade
```bash
# Check master version
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(currentMasterVersion)"

# Verify cluster is healthy
kubectl get componentstatuses

# Check that kubectl commands work
kubectl get nodes
kubectl get pods --all-namespaces
```

## Phase 3: Node Pool Upgrades

### Step 8: Prepare for Node Upgrades
```bash
# Check current node versions (should still be 1.32)
kubectl get nodes -o wide

# Verify workload tolerations for disruption
kubectl get pods --all-namespaces -o wide

# Check pod disruption budgets
kubectl get pdb --all-namespaces
```

### Step 9: Upgrade default-pool
```bash
# Start the upgrade for default-pool
gcloud container clusters upgrade $CLUSTER_NAME \
  --zone=$ZONE \
  --node-pool=default-pool \
  --cluster-version=1.33 \
  --project=$PROJECT_ID

# Monitor the upgrade progress
watch kubectl get nodes -o wide
```

**Wait for default-pool upgrade to complete before proceeding. This typically takes 15-30 minutes depending on the number of nodes.**

### Step 10: Verify default-pool Upgrade
```bash
# Check that all nodes in default-pool are running 1.33
kubectl get nodes -o wide | grep default-pool

# Verify pods are running properly
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

# Check for any failed pods
kubectl get pods --all-namespaces --field-selector=status.phase=Failed
```

### Step 11: Upgrade workload-pool
```bash
# Start the upgrade for workload-pool
gcloud container clusters upgrade $CLUSTER_NAME \
  --zone=$ZONE \
  --node-pool=workload-pool \
  --cluster-version=1.33 \
  --project=$PROJECT_ID

# Monitor the upgrade progress
watch kubectl get nodes -o wide
```

**Wait for workload-pool upgrade to complete.**

### Step 12: Verify workload-pool Upgrade
```bash
# Check that all nodes in workload-pool are running 1.33
kubectl get nodes -o wide | grep workload-pool

# Verify all nodes are now on 1.33
kubectl get nodes -o wide
```

## Phase 4: Post-Upgrade Verification

### Step 13: Comprehensive Health Check
```bash
# Verify all nodes are Ready and running 1.33
kubectl get nodes -o wide

# Check all system pods are running
kubectl get pods -n kube-system

# Verify all your application pods are running
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

# Check cluster info
kubectl cluster-info

# Verify services are accessible
kubectl get services --all-namespaces
```

### Step 14: Test Application Functionality
```bash
# Port-forward to test a sample application (replace with your app details)
# kubectl port-forward -n <namespace> <pod-name> <local-port>:<pod-port>

# Check ingress if you have any
kubectl get ingress --all-namespaces

# Verify persistent volumes are still attached
kubectl get pv
kubectl get pvc --all-namespaces
```

### Step 15: Final Verification
```bash
# Confirm final versions
echo "=== FINAL VERSION CHECK ==="
echo "Master version:"
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(currentMasterVersion)"

echo "Node versions:"
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,STATUS:.status.conditions[-1].type

# Verify cluster is healthy
kubectl get componentstatuses

# Check for any issues
kubectl get events --all-namespaces --sort-by='.lastTimestamp' | tail -20
```

## Phase 5: Cleanup and Documentation

### Step 16: Update Documentation
```bash
# Save final cluster state
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE > cluster-config-post-upgrade.yaml

# Document the upgrade
echo "Upgrade completed on $(date)" > upgrade-log.txt
echo "Master version: $(gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(currentMasterVersion)")" >> upgrade-log.txt
echo "Node versions:" >> upgrade-log.txt
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion >> upgrade-log.txt
```

## Troubleshooting Commands

If you encounter issues during the upgrade:

```bash
# Check operation status
gcloud container operations list --zone=$ZONE --filter="targetLink~$CLUSTER_NAME"

# Get detailed operation info
gcloud container operations describe <OPERATION_ID> --zone=$ZONE

# Check node pool status
gcloud container node-pools describe <POOL_NAME> --cluster=$CLUSTER_NAME --zone=$ZONE

# Check for stuck pods
kubectl get pods --all-namespaces | grep -E "(Pending|CrashLoopBackOff|Error)"

# Check node conditions
kubectl describe nodes

# View recent events
kubectl get events --all-namespaces --sort-by='.lastTimestamp' | tail -50
```

## Rollback Plan (Emergency Only)

If critical issues arise and you need to rollback:

```bash
# Note: You cannot rollback the master, but you can rollback node pools
gcloud container clusters upgrade $CLUSTER_NAME \
  --zone=$ZONE \
  --node-pool=<POOL_NAME> \
  --cluster-version=1.32 \
  --project=$PROJECT_ID
```

**⚠️ Important Notes:**
1. The master cannot be downgraded once upgraded
2. Node pools can only be downgraded if the target version is still supported
3. Always test in a non-production environment first
4. Each upgrade step should complete successfully before proceeding to the next
5. Keep monitoring your applications throughout the process

This upgrade should take approximately 45-90 minutes total, depending on cluster size and workload complexity.