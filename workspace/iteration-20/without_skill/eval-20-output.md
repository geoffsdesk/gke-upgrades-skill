# GKE Cluster Upgrade Runbook: 1.32 → 1.33

## Prerequisites
- `gcloud` CLI installed and authenticated
- `kubectl` configured for your cluster
- Cluster admin permissions

## Step 1: Initial Setup and Information Gathering

### 1.1 Set Environment Variables
```bash
export PROJECT_ID="your-project-id"
export CLUSTER_NAME="your-cluster-name"
export ZONE="us-west1-b"
```

### 1.2 Get Current Cluster Information
```bash
# Get cluster details
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID

# Check current versions
gcloud container clusters list --filter="name:$CLUSTER_NAME" --format="table(name,currentMasterVersion,currentNodeVersion,zone)"

# List node pools
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE
```

### 1.3 Verify Available Versions
```bash
# Check available master versions
gcloud container get-server-config --zone=$ZONE --format="value(validMasterVersions[0:10])"

# Verify 1.33 is available
gcloud container get-server-config --zone=$ZONE --format="yaml(validMasterVersions)" | grep "1.33"
```

## Step 2: Pre-Upgrade Health Checks

### 2.1 Check Cluster Health
```bash
# Check cluster status
kubectl get nodes
kubectl get pods --all-namespaces --field-selector=status.phase!=Running,status.phase!=Succeeded

# Check for any failing pods
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

# Check cluster events for any issues
kubectl get events --all-namespaces --sort-by='.lastTimestamp' | tail -20
```

### 2.2 Document Current State
```bash
# Save current state for rollback reference
kubectl get nodes -o wide > pre-upgrade-nodes.txt
kubectl get pods --all-namespaces -o wide > pre-upgrade-pods.txt
```

### 2.3 Check for Pod Disruption Budgets
```bash
kubectl get poddisruptionbudgets --all-namespaces
```

## Step 3: Backup Critical Resources

### 3.1 Export Important Configurations
```bash
# Export all configmaps and secrets (optional but recommended)
mkdir -p backup/$(date +%Y%m%d-%H%M%S)
cd backup/$(date +%Y%m%d-%H%M%S)

# Export cluster resources
kubectl get all --all-namespaces -o yaml > all-resources.yaml
kubectl get configmaps --all-namespaces -o yaml > configmaps.yaml
kubectl get secrets --all-namespaces -o yaml > secrets.yaml
```

## Step 4: Upgrade Control Plane (Master)

### 4.1 Upgrade Master to 1.33
```bash
# Start master upgrade
gcloud container clusters upgrade $CLUSTER_NAME \
    --master \
    --cluster-version=1.33 \
    --zone=$ZONE \
    --project=$PROJECT_ID
```

**⏰ This typically takes 5-15 minutes. Wait for completion before proceeding.**

### 4.2 Verify Master Upgrade
```bash
# Check master version
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(currentMasterVersion)"

# Verify cluster connectivity
kubectl cluster-info
kubectl get nodes
```

## Step 5: Upgrade Node Pools

### 5.1 Upgrade default-pool
```bash
# Check current node pool version
gcloud container node-pools describe default-pool --cluster=$CLUSTER_NAME --zone=$ZONE --format="value(version)"

# Upgrade default-pool
gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool=default-pool \
    --cluster-version=1.33 \
    --zone=$ZONE \
    --project=$PROJECT_ID
```

**⏰ Monitor the upgrade progress:**
```bash
# Watch nodes being recreated
watch kubectl get nodes

# Check upgrade status
gcloud container operations list --filter="targetLink:$CLUSTER_NAME"
```

### 5.2 Verify default-pool Upgrade
```bash
# Wait for all nodes to be Ready
kubectl get nodes

# Check node versions
kubectl get nodes -o custom-columns="NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion"

# Verify pods are running
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed
```

### 5.3 Upgrade workload-pool
```bash
# Check current workload-pool version
gcloud container node-pools describe workload-pool --cluster=$CLUSTER_NAME --zone=$ZONE --format="value(version)"

# Upgrade workload-pool
gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool=workload-pool \
    --cluster-version=1.33 \
    --zone=$ZONE \
    --project=$PROJECT_ID
```

**⏰ Monitor the upgrade progress:**
```bash
# Watch nodes being recreated
watch kubectl get nodes

# Check for any pod scheduling issues
kubectl get pods --all-namespaces -o wide | grep workload-pool
```

### 5.4 Verify workload-pool Upgrade
```bash
# Ensure all nodes are Ready and on 1.33
kubectl get nodes -o custom-columns="NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,POOL:.metadata.labels.cloud\.google\.com/gke-nodepool"

# Check that workload pods are running
kubectl get pods --all-namespaces --field-selector=spec.nodeName=$(kubectl get nodes -l cloud.google.com/gke-nodepool=workload-pool -o jsonpath='{.items[0].metadata.name}')
```

## Step 6: Post-Upgrade Verification

### 6.1 Comprehensive Health Check
```bash
# Check all nodes are Ready and on correct version
kubectl get nodes -o wide

# Verify all system pods are running
kubectl get pods -n kube-system

# Check all application pods
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

# Test cluster functionality
kubectl run test-pod --image=nginx --restart=Never
kubectl wait --for=condition=Ready pod/test-pod --timeout=60s
kubectl delete pod test-pod
```

### 6.2 Verify Cluster Information
```bash
# Final version check
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="table(currentMasterVersion,currentNodeVersion)"

# Check cluster is healthy
kubectl cluster-info
kubectl get componentstatuses
```

### 6.3 Application Testing
```bash
# Test a sample service (adjust as needed for your applications)
kubectl get services --all-namespaces

# If you have ingresses, check them
kubectl get ingresses --all-namespaces

# Check persistent volumes are still accessible
kubectl get pv,pvc --all-namespaces
```

## Step 7: Cleanup and Documentation

### 7.1 Clean Up Test Resources
```bash
# Remove any test pods if they still exist
kubectl delete pod test-pod --ignore-not-found=true
```

### 7.2 Document Upgrade
```bash
# Save post-upgrade state
kubectl get nodes -o wide > post-upgrade-nodes.txt
kubectl get pods --all-namespaces -o wide > post-upgrade-pods.txt

# Record final versions
echo "Upgrade completed on $(date)" > upgrade-log.txt
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(currentMasterVersion,currentNodeVersion)" >> upgrade-log.txt
```

## Troubleshooting Common Issues

### If Node Pool Upgrade Fails:
```bash
# Check operation status
gcloud container operations list --filter="targetLink:$CLUSTER_NAME" --limit=5

# Get operation details
gcloud container operations describe OPERATION_NAME --zone=$ZONE
```

### If Pods Are Not Scheduling:
```bash
# Check node capacity
kubectl describe nodes

# Check for taints
kubectl get nodes -o custom-columns="NAME:.metadata.name,TAINTS:.spec.taints"

# Check pod events
kubectl describe pods -n NAMESPACE POD_NAME
```

### Emergency Rollback (if needed):
```bash
# Note: You cannot rollback the master, but you can rollback node pools
# This should only be done if there are critical issues

gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool=POOL_NAME \
    --cluster-version=1.32.X \
    --zone=$ZONE \
    --project=$PROJECT_ID
```

## Success Criteria
✅ Master version shows 1.33.x  
✅ All nodes show kubelet version 1.33.x  
✅ All nodes are in Ready state  
✅ All application pods are Running  
✅ Services are accessible  
✅ No critical errors in cluster events  

## Estimated Timeline
- **Total Duration**: 45-90 minutes
- Master upgrade: 5-15 minutes
- Each node pool upgrade: 15-30 minutes
- Verification: 10-15 minutes

**⚠️ Important Notes:**
- The Regular channel should have 1.33 available, but verify first
- Node pool upgrades will recreate nodes, causing brief pod disruptions
- Have your team's contact information ready in case issues arise
- Consider doing this during a maintenance window

Your upgrade is complete! 🎉