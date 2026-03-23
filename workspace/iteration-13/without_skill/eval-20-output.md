# GKE Standard Cluster Upgrade Runbook: 1.32 → 1.33

## Prerequisites & Setup

First, set up your environment variables and verify access:

```bash
# Set your project and cluster details
export PROJECT_ID="your-project-id"
export CLUSTER_NAME="your-cluster-name"
export ZONE="us-west1-b"

# Authenticate with Google Cloud
gcloud auth login

# Set the project
gcloud config set project $PROJECT_ID

# Get cluster credentials
gcloud container clusters get-credentials $CLUSTER_NAME --zone $ZONE

# Verify you can access the cluster
kubectl cluster-info
kubectl get nodes
```

## Phase 1: Pre-Upgrade Assessment

### 1.1 Check Current Cluster State
```bash
# Check cluster version
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion,currentNodeVersion)"

# Check node pool versions
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE

# Check all nodes are ready
kubectl get nodes -o wide

# Check for any unhealthy pods
kubectl get pods --all-namespaces --field-selector=status.phase!=Running,status.phase!=Succeeded
```

### 1.2 Verify Available Versions
```bash
# Check available master versions
gcloud container get-server-config --zone=$ZONE --format="yaml(validMasterVersions)"

# Confirm 1.33 is available
gcloud container get-server-config --zone=$ZONE --format="value(validMasterVersions[0:10])" | grep "1.33"
```

### 1.3 Pre-Upgrade Health Check
```bash
# Check cluster health
kubectl get componentstatuses

# Check system pods
kubectl get pods -n kube-system

# Check your application pods
kubectl get pods --all-namespaces

# Check PodDisruptionBudgets (important for safe upgrades)
kubectl get pdb --all-namespaces

# Check resource usage
kubectl top nodes
kubectl top pods --all-namespaces
```

## Phase 2: Create Backup & Emergency Plan

### 2.1 Document Current State
```bash
# Save current cluster config
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE > cluster-config-backup.yaml

# Save current workloads
kubectl get all --all-namespaces -o yaml > workloads-backup.yaml

# Save persistent volumes (if any)
kubectl get pv,pvc --all-namespaces -o yaml > storage-backup.yaml
```

### 2.2 Test Application Health
```bash
# If you have ingresses, test external connectivity
kubectl get ingress --all-namespaces

# Check services
kubectl get svc --all-namespaces

# Test a sample pod (replace with your actual workload)
kubectl get pods -l app=your-app-label
```

## Phase 3: Master Upgrade

### 3.1 Upgrade Control Plane
```bash
# Find the latest 1.33 version
LATEST_133=$(gcloud container get-server-config --zone=$ZONE --format="value(validMasterVersions[])" | grep "1.33" | head -1)
echo "Upgrading to: $LATEST_133"

# Upgrade the master (this takes 5-10 minutes)
gcloud container clusters upgrade $CLUSTER_NAME --zone $ZONE --master --cluster-version=$LATEST_133

# Monitor the upgrade
gcloud container operations list --zone=$ZONE
```

### 3.2 Verify Master Upgrade
```bash
# Check master version (should now be 1.33.x)
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion)"

# Verify kubectl connectivity
kubectl cluster-info

# Check system components
kubectl get pods -n kube-system
```

## Phase 4: Node Pool Upgrades

### 4.1 Upgrade default-pool
```bash
# Check current node pool status
gcloud container node-pools describe default-pool --cluster=$CLUSTER_NAME --zone=$ZONE

# Start the upgrade (this will cordon, drain, and replace nodes one by one)
gcloud container node-pools upgrade default-pool --cluster=$CLUSTER_NAME --zone=$ZONE

# Monitor progress
watch 'kubectl get nodes -o wide'
```

### 4.2 Monitor default-pool Upgrade
```bash
# In a separate terminal, monitor the upgrade
watch 'gcloud container operations list --zone=$ZONE | head -5'

# Watch pods being rescheduled
watch 'kubectl get pods --all-namespaces | grep -v Running | grep -v Completed'

# Check node versions during upgrade
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,STATUS:.status.conditions[-1].type
```

### 4.3 Verify default-pool Upgrade
```bash
# Wait for upgrade to complete, then verify
gcloud container node-pools describe default-pool --cluster=$CLUSTER_NAME --zone=$ZONE --format="value(version,status)"

# All nodes should be Ready and on 1.33.x
kubectl get nodes -o wide
```

### 4.4 Upgrade workload-pool
```bash
# Check workload-pool status
gcloud container node-pools describe workload-pool --cluster=$CLUSTER_NAME --zone=$ZONE

# Start workload-pool upgrade
gcloud container node-pools upgrade workload-pool --cluster=$CLUSTER_NAME --zone=$ZONE

# Monitor progress
watch 'kubectl get nodes -o wide'
```

### 4.5 Monitor workload-pool Upgrade
```bash
# Monitor the operation
watch 'gcloud container operations list --zone=$ZONE | head -5'

# Watch for any pod issues
kubectl get events --sort-by='.lastTimestamp' | tail -20

# Check for pods stuck in terminating state
kubectl get pods --all-namespaces | grep Terminating
```

## Phase 5: Post-Upgrade Verification

### 5.1 Verify Complete Upgrade
```bash
# Check final cluster version
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion,currentNodeVersion)"

# All nodes should be on 1.33.x and Ready
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,STATUS:.status.conditions[-1].type

# Verify both node pools
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE
```

### 5.2 Application Health Check
```bash
# Check all pods are running
kubectl get pods --all-namespaces --field-selector=status.phase!=Running,status.phase!=Succeeded

# Check services
kubectl get svc --all-namespaces

# Check ingresses (if any)
kubectl get ingress --all-namespaces

# Test application connectivity (replace with your actual service)
kubectl get endpoints --all-namespaces
```

### 5.3 System Health Check
```bash
# Check system pods
kubectl get pods -n kube-system

# Check cluster info
kubectl cluster-info

# Check component status
kubectl get componentstatuses

# Check for any events/errors
kubectl get events --sort-by='.lastTimestamp' --all-namespaces | tail -20
```

## Phase 6: Final Validation

### 6.1 Performance Validation
```bash
# Check resource usage
kubectl top nodes
kubectl top pods --all-namespaces --sort-by=cpu

# Check for any resource constraints
kubectl describe nodes | grep -A 5 "Allocated resources"
```

### 6.2 Create Post-Upgrade Documentation
```bash
# Document final state
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE > cluster-config-post-upgrade.yaml

# Save final workload state
kubectl get all --all-namespaces -o yaml > workloads-post-upgrade.yaml

echo "Upgrade completed successfully!"
echo "Master version: $(gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format='value(currentMasterVersion)')"
echo "Node version: $(kubectl get nodes -o jsonpath='{.items[0].status.nodeInfo.kubeletVersion}')"
```

## Troubleshooting Common Issues

### If upgrade fails or pods won't start:
```bash
# Check for resource constraints
kubectl describe nodes

# Check events for errors
kubectl get events --sort-by='.lastTimestamp' --all-namespaces

# Check specific pod issues
kubectl describe pod <pod-name> -n <namespace>

# Force delete stuck pods (use carefully)
kubectl delete pod <pod-name> -n <namespace> --force --grace-period=0
```

### Emergency rollback (if supported):
```bash
# Note: Master upgrades cannot be rolled back, but you can check node pool status
gcloud container node-pools describe <pool-name> --cluster=$CLUSTER_NAME --zone=$ZONE

# For critical issues, you may need to recreate node pools with older versions
# This is a last resort and should be done with Google Cloud support
```

## Expected Timeline
- **Master upgrade**: 5-10 minutes
- **Each node pool upgrade**: 15-30 minutes (depending on node count)
- **Total estimated time**: 45-90 minutes

## Safety Notes
1. **Business hours**: Perform during maintenance windows
2. **Monitoring**: Keep monitoring dashboards open during upgrade
3. **Communication**: Notify stakeholders before starting
4. **Rollback plan**: Have contact info for Google Cloud support ready
5. **Testing**: Test application functionality after each phase

The upgrade process is automated and handles pod rescheduling, but always monitor for any application-specific issues that might arise from the Kubernetes version change.