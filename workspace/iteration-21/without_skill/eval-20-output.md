# GKE Cluster Upgrade Runbook: 1.32 → 1.33

## Prerequisites & Safety Checks

### 1. Set Environment Variables
```bash
export CLUSTER_NAME="your-cluster-name"
export PROJECT_ID="your-project-id"
export ZONE="us-west1-b"
```

### 2. Authenticate and Set Context
```bash
# Authenticate with Google Cloud
gcloud auth login

# Set project
gcloud config set project $PROJECT_ID

# Get cluster credentials
gcloud container clusters get-credentials $CLUSTER_NAME --zone $ZONE --project $PROJECT_ID

# Verify connection
kubectl cluster-info
```

### 3. Pre-Upgrade Health Check
```bash
# Check cluster status
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE

# Check node status
kubectl get nodes -o wide

# Check system pods
kubectl get pods -n kube-system

# Check your workloads
kubectl get pods --all-namespaces | grep -v Running

# Check cluster events for any issues
kubectl get events --sort-by=.metadata.creationTimestamp --all-namespaces | tail -20
```

### 4. Backup Critical Data
```bash
# Export current cluster configuration
kubectl get all --all-namespaces -o yaml > cluster-backup-$(date +%Y%m%d-%H%M%S).yaml

# List all persistent volumes (document these)
kubectl get pv

# List all persistent volume claims
kubectl get pvc --all-namespaces
```

## Phase 1: Control Plane Upgrade

### 5. Check Available Versions
```bash
# Check what versions are available
gcloud container get-server-config --zone $ZONE

# Verify current cluster version
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion)"
```

### 6. Upgrade Control Plane to 1.33
```bash
# Start control plane upgrade
gcloud container clusters upgrade $CLUSTER_NAME \
    --master \
    --cluster-version=1.33 \
    --zone $ZONE

# When prompted, type 'y' to confirm
```

### 7. Monitor Control Plane Upgrade
```bash
# Check upgrade status (run this periodically)
gcloud container operations list --filter="targetLink~$CLUSTER_NAME"

# Check cluster status
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(status,currentMasterVersion)"

# This upgrade typically takes 5-10 minutes
# Wait until status shows "RUNNING" before proceeding
```

## Phase 2: Node Pool Upgrades

### 8. Check Node Pool Status
```bash
# List all node pools and their versions
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE

# Get detailed node pool information
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,INSTANCE:.spec.providerID
```

### 9. Upgrade default-pool
```bash
# Start default-pool upgrade
gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool=default-pool \
    --zone=$ZONE

# When prompted, type 'y' to confirm
```

### 10. Monitor default-pool Upgrade
```bash
# Monitor the upgrade progress
watch -n 30 'kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,STATUS:.status.conditions[-1].type'

# Check for any pod disruptions
kubectl get pods --all-namespaces | grep -E "(Pending|Error|CrashLoopBackOff)"

# Monitor upgrade operation
gcloud container operations list --filter="targetLink~$CLUSTER_NAME" --limit=5
```

### 11. Verify default-pool Upgrade
```bash
# Wait for all nodes in default-pool to be Ready and on version 1.33
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool

# Check that all pods are running
kubectl get pods --all-namespaces --field-selector=status.phase!=Running
```

### 12. Upgrade workload-pool
```bash
# Start workload-pool upgrade
gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool=workload-pool \
    --zone=$ZONE

# When prompted, type 'y' to confirm
```

### 13. Monitor workload-pool Upgrade
```bash
# Monitor the upgrade progress
watch -n 30 'kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,STATUS:.status.conditions[-1].type'

# Check for any pod disruptions
kubectl get pods --all-namespaces | grep -E "(Pending|Error|CrashLoopBackOff)"

# Monitor upgrade operation
gcloud container operations list --filter="targetLink~$CLUSTER_NAME" --limit=5
```

## Phase 3: Post-Upgrade Verification

### 14. Comprehensive Health Check
```bash
# Verify all nodes are on 1.33
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion

# Verify cluster version
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion)"

# Check all node pools
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE
```

### 15. Verify System Components
```bash
# Check kube-system pods
kubectl get pods -n kube-system

# Check for any failed pods across all namespaces
kubectl get pods --all-namespaces --field-selector=status.phase!=Running

# Check cluster events for any errors
kubectl get events --sort-by=.metadata.creationTimestamp --all-namespaces | tail -50
```

### 16. Test Workload Functionality
```bash
# Check your application namespaces
kubectl get pods --all-namespaces

# Test a simple deployment to verify cluster functionality
kubectl create deployment test-upgrade --image=nginx:latest
kubectl expose deployment test-upgrade --port=80 --target-port=80
kubectl get pods -l app=test-upgrade

# Clean up test deployment
kubectl delete deployment test-upgrade
kubectl delete service test-upgrade
```

### 17. Final Verification
```bash
# Comprehensive cluster status
echo "=== CLUSTER INFORMATION ==="
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="table(name,status,currentMasterVersion,location)"

echo "=== NODE POOL INFORMATION ==="
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE

echo "=== NODE STATUS ==="
kubectl get nodes -o wide

echo "=== SYSTEM PODS ==="
kubectl get pods -n kube-system

echo "=== ANY PROBLEMATIC PODS ==="
kubectl get pods --all-namespaces --field-selector=status.phase!=Running
```

## Troubleshooting Commands

If you encounter issues, use these commands:

```bash
# Check detailed node status
kubectl describe nodes

# Check recent events
kubectl get events --sort-by=.metadata.creationTimestamp --all-namespaces | tail -100

# Check specific pod issues
kubectl describe pod <pod-name> -n <namespace>

# Check cluster operations history
gcloud container operations list --filter="targetLink~$CLUSTER_NAME" --limit=10

# Check logs for specific pods
kubectl logs <pod-name> -n <namespace>
```

## Expected Timeline
- **Control Plane Upgrade**: 5-10 minutes
- **Each Node Pool Upgrade**: 10-20 minutes per node pool (depends on node count)
- **Total Expected Time**: 25-50 minutes

## Important Notes
- ⚠️ **Node upgrades cause pod restarts** - ensure your applications can handle rolling restarts
- ⚠️ **Don't interrupt the upgrade process** - let each phase complete fully
- ⚠️ **Have a rollback plan** - document current versions before starting
- ⚠️ **Monitor your applications** throughout the process

The upgrade is complete when all commands in the Final Verification section show healthy status and version 1.33!