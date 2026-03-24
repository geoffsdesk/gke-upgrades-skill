# GKE Cluster Upgrade Runbook: 1.32 → 1.33

## Prerequisites
- `gcloud` CLI installed and authenticated
- `kubectl` configured to connect to your cluster
- Cluster admin permissions
- Maintenance window scheduled (upgrades can take 30+ minutes)

## Phase 1: Pre-Upgrade Assessment

### 1.1 Set Environment Variables
```bash
export PROJECT_ID="your-project-id"
export CLUSTER_NAME="your-cluster-name"
export ZONE="us-west1-b"
```

### 1.2 Verify Current State
```bash
# Verify cluster connection
kubectl cluster-info

# Check current cluster version
gcloud container clusters describe $CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --format="value(currentMasterVersion,currentNodeVersion)"

# List all node pools and their versions
gcloud container node-pools list \
    --cluster=$CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID

# Check node status
kubectl get nodes -o wide
```

### 1.3 Check Available Versions
```bash
# List available master versions
gcloud container get-server-config \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --format="value(validMasterVersions[0:5])"
```

### 1.4 Pre-Upgrade Health Check
```bash
# Check cluster health
kubectl get componentstatuses

# Check pod status across all namespaces
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

# Check for any disrupted workloads
kubectl get pods --all-namespaces --field-selector=status.phase!=Running,status.phase!=Succeeded

# Document current workload distribution
kubectl get pods -o wide --all-namespaces > pre-upgrade-pods-$(date +%Y%m%d-%H%M).txt
```

### 1.5 Backup Critical Configurations
```bash
# Create backup directory
mkdir -p gke-upgrade-backup-$(date +%Y%m%d)
cd gke-upgrade-backup-$(date +%Y%m%d)

# Backup cluster configuration
gcloud container clusters describe $CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID > cluster-config-backup.yaml

# Backup all Kubernetes resources (optional but recommended)
kubectl get all --all-namespaces -o yaml > all-resources-backup.yaml
```

## Phase 2: Control Plane Upgrade

### 2.1 Upgrade Control Plane
```bash
# Upgrade control plane to 1.33
# Note: Replace "1.33.x-gke.y" with the specific version from step 1.3
gcloud container clusters upgrade $CLUSTER_NAME \
    --master \
    --cluster-version="1.33.0-gke.1" \
    --zone=$ZONE \
    --project=$PROJECT_ID
```

**⚠️ Important:** When prompted, type `Y` to confirm. This operation typically takes 10-15 minutes.

### 2.2 Verify Control Plane Upgrade
```bash
# Wait for upgrade to complete, then verify
gcloud container clusters describe $CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --format="value(currentMasterVersion)"

# Test cluster connectivity
kubectl cluster-info

# Verify API server is responsive
kubectl get nodes
```

## Phase 3: Node Pool Upgrades

### 3.1 Upgrade default-pool
```bash
# Check current node pool version
gcloud container node-pools describe default-pool \
    --cluster=$CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --format="value(version)"

# Upgrade default-pool nodes
gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool=default-pool \
    --zone=$ZONE \
    --project=$PROJECT_ID
```

**⚠️ Important:** This will drain and recreate nodes. Pods will be rescheduled automatically.

### 3.2 Monitor default-pool Upgrade
```bash
# Watch node status during upgrade
watch kubectl get nodes

# In another terminal, monitor pod rescheduling
watch kubectl get pods --all-namespaces -o wide
```

### 3.3 Verify default-pool Upgrade
```bash
# Check that all default-pool nodes are upgraded
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool

# Verify node pool version
gcloud container node-pools describe default-pool \
    --cluster=$CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --format="value(version)"
```

### 3.4 Upgrade workload-pool
```bash
# Upgrade workload-pool nodes
gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool=workload-pool \
    --zone=$ZONE \
    --project=$PROJECT_ID
```

### 3.5 Monitor workload-pool Upgrade
```bash
# Watch node status during upgrade
watch kubectl get nodes

# Monitor workload-pool specific nodes
watch kubectl get nodes -l cloud.google.com/gke-nodepool=workload-pool
```

### 3.6 Verify workload-pool Upgrade
```bash
# Check that all workload-pool nodes are upgraded
kubectl get nodes -l cloud.google.com/gke-nodepool=workload-pool

# Verify node pool version
gcloud container node-pools describe workload-pool \
    --cluster=$CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --format="value(version)"
```

## Phase 4: Post-Upgrade Verification

### 4.1 Comprehensive Health Check
```bash
# Verify all nodes are Ready and on correct version
kubectl get nodes -o wide

# Check all system pods are running
kubectl get pods -n kube-system

# Verify cluster components
kubectl get componentstatuses

# Check for any failed pods
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed
```

### 4.2 Application Health Verification
```bash
# List all deployments and their status
kubectl get deployments --all-namespaces

# Check for any deployments with unavailable replicas
kubectl get deployments --all-namespaces -o custom-columns=NAME:.metadata.name,NAMESPACE:.metadata.namespace,READY:.status.readyReplicas,AVAILABLE:.status.availableReplicas | grep -v "Ready\|Available"

# Verify services are accessible
kubectl get services --all-namespaces

# Test a sample service (replace with your actual service)
# kubectl port-forward svc/your-service-name 8080:80 -n your-namespace
```

### 4.3 Final Version Confirmation
```bash
# Get final cluster information
echo "=== CLUSTER UPGRADE COMPLETE ==="
echo "Cluster: $CLUSTER_NAME"
echo "Zone: $ZONE"
echo "Project: $PROJECT_ID"

gcloud container clusters describe $CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --format="table(currentMasterVersion:label='Master Version',currentNodeVersion:label='Node Version')"

# Show all node pools and versions
gcloud container node-pools list \
    --cluster=$CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --format="table(name:label='Pool Name',version:label='Version',status:label='Status')"
```

## Phase 5: Troubleshooting Commands

If you encounter issues, use these commands:

### 5.1 Check Upgrade Status
```bash
# Check for any ongoing operations
gcloud container operations list \
    --filter="zone:$ZONE AND targetLink:*$CLUSTER_NAME*" \
    --project=$PROJECT_ID

# Get detailed operation status
gcloud container operations describe OPERATION_ID \
    --zone=$ZONE \
    --project=$PROJECT_ID
```

### 5.2 Node Issues
```bash
# Check node conditions
kubectl describe nodes

# Check events for issues
kubectl get events --sort-by=.metadata.creationTimestamp

# Force drain a problematic node (if needed)
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data
```

### 5.3 Pod Issues
```bash
# Check pods stuck in pending state
kubectl get pods --all-namespaces --field-selector=status.phase=Pending

# Describe problematic pods
kubectl describe pod POD_NAME -n NAMESPACE

# Check resource availability
kubectl describe nodes | grep -A 5 "Allocated resources"
```

## Expected Timeline
- **Control Plane Upgrade**: 10-15 minutes
- **Each Node Pool Upgrade**: 15-30 minutes depending on node count
- **Total Expected Time**: 45-75 minutes

## Rollback Plan
If critical issues arise:

```bash
# Rollback is not directly supported, but you can:
# 1. Scale down problematic workloads
kubectl scale deployment DEPLOYMENT_NAME --replicas=0 -n NAMESPACE

# 2. Restore from backup configurations if needed
kubectl apply -f cluster-config-backup.yaml

# 3. Contact Google Cloud Support for cluster-level issues
```

## Post-Upgrade Tasks
1. Update your CI/CD pipelines with new cluster version
2. Test all critical application functionality
3. Update monitoring dashboards if needed
4. Document any issues encountered for future upgrades
5. Schedule next upgrade cycle based on your Regular channel update schedule

---
**⚠️ IMPORTANT REMINDERS:**
- Always perform upgrades during maintenance windows
- Monitor applications closely for 24-48 hours post-upgrade
- Keep this runbook and all backup files until you confirm everything is working
- The Regular channel will automatically schedule future upgrades - plan accordingly