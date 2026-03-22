# GKE Standard Cluster Upgrade Runbook: 1.31 → 1.32

## Prerequisites Check

First, let's gather information about your current cluster:

```bash
# Set your project and cluster variables
export PROJECT_ID="your-project-id"
export CLUSTER_NAME="your-cluster-name"
export ZONE="us-west1-b"

# Get current cluster info
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID
```

## Step 1: Pre-Upgrade Assessment

### 1.1 Check Current Versions
```bash
# Check control plane version
kubectl version --short

# Check node versions
kubectl get nodes -o wide

# Check node pool details
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE
```

### 1.2 Check Available Upgrades
```bash
# Check what versions are available
gcloud container get-server-config --zone=$ZONE

# Check specifically for your cluster
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(currentMasterVersion,currentNodeVersion)"
```

### 1.3 Application Health Check
```bash
# Check all pods are running
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

# Check for any unhealthy deployments
kubectl get deployments --all-namespaces

# Check node status
kubectl get nodes

# Save current state for comparison
kubectl get pods --all-namespaces -o wide > pre-upgrade-pods.txt
kubectl get nodes -o wide > pre-upgrade-nodes.txt
```

## Step 2: Backup and Preparation

### 2.1 Backup Critical Resources
```bash
# Create backup directory
mkdir -p gke-upgrade-backup/$(date +%Y%m%d)
cd gke-upgrade-backup/$(date +%Y%m%d)

# Backup all resources
kubectl get all --all-namespaces -o yaml > all-resources-backup.yaml
kubectl get configmaps --all-namespaces -o yaml > configmaps-backup.yaml
kubectl get secrets --all-namespaces -o yaml > secrets-backup.yaml
kubectl get persistentvolumes -o yaml > pv-backup.yaml
kubectl get persistentvolumeclaims --all-namespaces -o yaml > pvc-backup.yaml
```

### 2.2 Check for Deprecated APIs
```bash
# Check for deprecated APIs (if you have kubectl-deprecations plugin)
# If not installed: kubectl krew install deprecations
kubectl deprecations --k8s-version=v1.32.0
```

## Step 3: Control Plane Upgrade

### 3.1 Upgrade Control Plane
```bash
# Upgrade control plane to 1.32 (latest patch version will be selected automatically)
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --master \
    --cluster-version=1.32 \
    --project=$PROJECT_ID

# This will take 10-20 minutes. Wait for completion.
```

### 3.2 Verify Control Plane Upgrade
```bash
# Check control plane version
kubectl version --short

# Verify cluster is accessible
kubectl get nodes

# Check cluster status
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(status,currentMasterVersion)"
```

## Step 4: Node Pool Upgrades

### 4.1 Check Node Pool Status
```bash
# List all node pools and their versions
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE

# Get detailed info for each pool
gcloud container node-pools describe default-pool --cluster=$CLUSTER_NAME --zone=$ZONE
gcloud container node-pools describe workload-pool --cluster=$CLUSTER_NAME --zone=$ZONE
```

### 4.2 Upgrade default-pool
```bash
# Check current workload distribution
kubectl get pods --all-namespaces -o wide | grep -E "default-pool|workload-pool"

# Upgrade default-pool (this will replace nodes one by one)
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --node-pool=default-pool \
    --cluster-version=1.32 \
    --project=$PROJECT_ID

# Monitor the upgrade progress
watch "kubectl get nodes -o wide"
```

### 4.3 Verify default-pool Upgrade
```bash
# Check node versions
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool -o wide

# Check pod health
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

# Wait for all nodes in default-pool to be Ready before proceeding
kubectl wait --for=condition=Ready nodes --selector=cloud.google.com/gke-nodepool=default-pool --timeout=600s
```

### 4.4 Upgrade workload-pool
```bash
# Upgrade workload-pool
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --node-pool=workload-pool \
    --cluster-version=1.32 \
    --project=$PROJECT_ID

# Monitor the upgrade progress
watch "kubectl get nodes -o wide"
```

### 4.5 Verify workload-pool Upgrade
```bash
# Check node versions
kubectl get nodes -l cloud.google.com/gke-nodepool=workload-pool -o wide

# Wait for all nodes in workload-pool to be Ready
kubectl wait --for=condition=Ready nodes --selector=cloud.google.com/gke-nodepool=workload-pool --timeout=600s
```

## Step 5: Post-Upgrade Verification

### 5.1 Comprehensive Health Check
```bash
# Check all nodes are running 1.32
kubectl get nodes -o wide

# Verify all pods are running
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

# Check system pods
kubectl get pods -n kube-system

# Check deployments
kubectl get deployments --all-namespaces

# Check services
kubectl get services --all-namespaces
```

### 5.2 Application Testing
```bash
# Test a simple pod deployment
kubectl run test-pod --image=nginx --restart=Never
kubectl wait --for=condition=Ready pod/test-pod --timeout=300s
kubectl delete pod test-pod

# If you have ingress controllers or load balancers, test them
kubectl get ingress --all-namespaces
kubectl get services --all-namespaces -o wide
```

### 5.3 Compare Pre and Post Upgrade
```bash
# Save current state
kubectl get pods --all-namespaces -o wide > post-upgrade-pods.txt
kubectl get nodes -o wide > post-upgrade-nodes.txt

# Compare (basic diff)
echo "=== NODE COMPARISON ==="
diff pre-upgrade-nodes.txt post-upgrade-nodes.txt

echo "=== POD COUNT COMPARISON ==="
echo "Before: $(wc -l < pre-upgrade-pods.txt)"
echo "After: $(wc -l < post-upgrade-pods.txt)"
```

## Step 6: Final Verification

### 6.1 Cluster Information
```bash
# Final cluster status
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="table(currentMasterVersion,currentNodeVersion,status,location)"

# Node pool status
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE --format="table(name,version,status,instanceGroupUrls)"

# Kubernetes version verification
kubectl version --short
```

### 6.2 Clean Up
```bash
# Remove test resources if any were created
# kubectl delete [any-test-resources]

# Archive backup files
cd ../../
tar -czf gke-upgrade-backup-$(date +%Y%m%d).tar.gz gke-upgrade-backup/
```

## Troubleshooting Commands

If you encounter issues during the upgrade:

```bash
# Check cluster events
kubectl get events --sort-by='.lastTimestamp' --all-namespaces

# Check node conditions
kubectl describe nodes

# Check pod events for failed pods
kubectl describe pod <pod-name> -n <namespace>

# Get cluster operation status
gcloud container operations list --filter="targetId:$CLUSTER_NAME"

# Get detailed operation info
gcloud container operations describe <operation-id> --zone=$ZONE
```

## Rollback Procedure (Emergency Only)

**Note: GKE doesn't support downgrading. This is for reference only.**

```bash
# You cannot rollback a GKE upgrade
# If issues occur, you'll need to:
# 1. Fix the application compatibility issues
# 2. Restore from backups if necessary
# 3. Create a new cluster with the old version if absolutely necessary
```

## Expected Timeline

- **Control Plane Upgrade**: 10-20 minutes
- **default-pool Upgrade**: 15-30 minutes (depends on node count)
- **workload-pool Upgrade**: 15-30 minutes (depends on node count)
- **Total Time**: 40-80 minutes

## Important Notes

1. **Workload Disruption**: Node upgrades will cause pod restarts as nodes are replaced
2. **PodDisruptionBudgets**: Ensure your critical applications have PDBs configured
3. **Regular Channel**: Being on Regular channel means you'll get stable, tested versions
4. **Monitoring**: Keep an eye on your monitoring/alerting systems during the upgrade

Execute each step carefully and wait for completion before proceeding to the next step.