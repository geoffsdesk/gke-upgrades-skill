# GKE Standard Cluster Upgrade Runbook: 1.28 → 1.30

## Overview
This runbook will guide you through upgrading a GKE Standard cluster from version 1.28 to 1.30. The process involves upgrading the control plane first, then each node pool.

## Prerequisites
- `gcloud` CLI installed and authenticated
- `kubectl` configured for your cluster
- Cluster admin permissions
- Maintenance window scheduled (expect 30-60 minutes total)

## Step 1: Initial Setup and Information Gathering

### 1.1 Set Environment Variables
```bash
# Replace with your actual values
export CLUSTER_NAME="your-cluster-name"
export PROJECT_ID="your-project-id"
export ZONE="us-west1-b"

# Verify these are set correctly
echo "Cluster: $CLUSTER_NAME"
echo "Project: $PROJECT_ID" 
echo "Zone: $ZONE"
```

### 1.2 Get Current Cluster Information
```bash
# Get current cluster version
gcloud container clusters describe $CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --format="value(currentMasterVersion,currentNodeVersion)"

# List all node pools and their versions
gcloud container node-pools list \
    --cluster=$CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID
```

### 1.3 Check Available Versions
```bash
# Check available master versions
gcloud container get-server-config \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --format="value(validMasterVersions[0:5])"
```

## Step 2: Pre-Upgrade Verification

### 2.1 Check Cluster Health
```bash
# Check node status
kubectl get nodes -o wide

# Check system pods
kubectl get pods -n kube-system

# Check for any failed pods across all namespaces
kubectl get pods --all-namespaces --field-selector=status.phase!=Running,status.phase!=Succeeded
```

### 2.2 Check Workload Health
```bash
# List all deployments and their status
kubectl get deployments --all-namespaces

# Check for any disruption budgets (important for upgrade planning)
kubectl get poddisruptionbudgets --all-namespaces
```

### 2.3 Backup Critical Information
```bash
# Export current cluster config (optional but recommended)
kubectl cluster-info dump > cluster-info-backup-$(date +%Y%m%d).txt

# List all persistent volumes
kubectl get pv > pv-backup-$(date +%Y%m%d).txt
```

## Step 3: Control Plane Upgrade

### 3.1 Upgrade Master to 1.29 (Intermediate Step)
```bash
# Upgrade control plane to 1.29 first
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --master \
    --cluster-version=1.29 \
    --quiet

# This will take 5-10 minutes. Wait for completion.
```

### 3.2 Verify Master Upgrade
```bash
# Check master version
gcloud container clusters describe $CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --format="value(currentMasterVersion)"

# Verify cluster is healthy
kubectl get nodes
kubectl get pods -n kube-system
```

### 3.3 Upgrade Master to 1.30
```bash
# Upgrade control plane to 1.30
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --master \
    --cluster-version=1.30 \
    --quiet

# This will take 5-10 minutes. Wait for completion.
```

### 3.4 Verify Final Master Upgrade
```bash
# Confirm master is on 1.30
gcloud container clusters describe $CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --format="value(currentMasterVersion)"
```

## Step 4: Node Pool Upgrades

### 4.1 Upgrade default-pool to 1.29
```bash
# Upgrade default-pool to 1.29
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --node-pool=default-pool \
    --cluster-version=1.29 \
    --quiet

# This will take 10-20 minutes depending on node count
```

### 4.2 Monitor default-pool Upgrade Progress
```bash
# Watch node status during upgrade
watch kubectl get nodes

# In another terminal, monitor pods
watch "kubectl get pods --all-namespaces | grep -v Running | grep -v Completed"
```

### 4.3 Upgrade default-pool to 1.30
```bash
# Upgrade default-pool to 1.30
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --node-pool=default-pool \
    --cluster-version=1.30 \
    --quiet
```

### 4.4 Upgrade workload-pool to 1.29
```bash
# Upgrade workload-pool to 1.29
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --node-pool=workload-pool \
    --cluster-version=1.29 \
    --quiet
```

### 4.5 Upgrade workload-pool to 1.30
```bash
# Upgrade workload-pool to 1.30
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --node-pool=workload-pool \
    --cluster-version=1.30 \
    --quiet
```

## Step 5: Post-Upgrade Verification

### 5.1 Verify All Versions
```bash
# Check cluster and node versions
gcloud container clusters describe $CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --format="table(currentMasterVersion,currentNodeVersion)"

# Check individual node pool versions
gcloud container node-pools list \
    --cluster=$CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --format="table(name,version,status)"
```

### 5.2 Health Checks
```bash
# Verify all nodes are ready
kubectl get nodes

# Check system pods
kubectl get pods -n kube-system

# Verify all workload pods are running
kubectl get pods --all-namespaces --field-selector=status.phase!=Running,status.phase!=Succeeded

# Check deployments
kubectl get deployments --all-namespaces
```

### 5.3 Test Application Functionality
```bash
# Test a simple pod deployment
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Cluster is working"

# If you have ingress, test external connectivity
kubectl get ingress --all-namespaces
```

## Step 6: Clean Up and Documentation

### 6.1 Clean Up Test Resources
```bash
# Remove any test pods if they weren't auto-removed
kubectl delete pods -l run=test-pod
```

### 6.2 Document the Upgrade
```bash
# Get final cluster state for documentation
gcloud container clusters describe $CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --format="yaml" > cluster-state-post-upgrade-$(date +%Y%m%d).yaml

echo "Upgrade completed on $(date)"
echo "Cluster $CLUSTER_NAME is now running Kubernetes 1.30"
```

## Troubleshooting Commands

### If Nodes Are Stuck in Upgrade:
```bash
# Check node pool status
gcloud container operations list --filter="targetLink:$CLUSTER_NAME"

# Get detailed node information
kubectl describe nodes

# Check events for issues
kubectl get events --sort-by='.lastTimestamp' -A
```

### If Pods Won't Start:
```bash
# Check pod events
kubectl describe pod <pod-name> -n <namespace>

# Check resource constraints
kubectl top nodes
kubectl top pods --all-namespaces
```

## Important Notes:

1. **Gradual Upgrade**: Always upgrade one minor version at a time (1.28 → 1.29 → 1.30)
2. **Control Plane First**: Always upgrade the control plane before node pools
3. **One Node Pool at a Time**: Upgrade node pools sequentially, not simultaneously
4. **Monitor Throughout**: Watch for any issues during each step
5. **Regular Channel**: Your cluster will continue receiving automatic updates on the Regular channel

## Emergency Rollback:
If you encounter critical issues, you cannot rollback the control plane, but you can:
```bash
# Create a new node pool with the previous version (if needed)
gcloud container node-pools create emergency-pool \
    --cluster=$CLUSTER_NAME \
    --zone=$ZONE \
    --node-version=1.28 \
    --num-nodes=1
```

This runbook should take approximately 45-90 minutes to complete depending on your cluster size and workload complexity.