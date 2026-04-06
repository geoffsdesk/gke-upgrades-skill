# GKE Cluster Upgrade Runbook: 1.32 → 1.33

## Prerequisites Checklist
- [ ] kubectl installed and configured
- [ ] gcloud CLI installed and authenticated
- [ ] Access to the GKE cluster
- [ ] Maintenance window scheduled
- [ ] Backup of critical application configurations

## Step 1: Initial Setup and Verification

### 1.1 Set Environment Variables
```bash
export PROJECT_ID="your-project-id"
export CLUSTER_NAME="your-cluster-name"
export ZONE="us-west1-b"
```

### 1.2 Authenticate and Set Context
```bash
# Authenticate with Google Cloud
gcloud auth login

# Set the project
gcloud config set project $PROJECT_ID

# Get cluster credentials
gcloud container clusters get-credentials $CLUSTER_NAME --zone $ZONE --project $PROJECT_ID
```

### 1.3 Verify Current State
```bash
# Check current cluster version
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion,currentNodeVersion)"

# Check node pool versions
gcloud container node-pools list --cluster $CLUSTER_NAME --zone $ZONE

# Check cluster health
kubectl get nodes
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed
```

## Step 2: Pre-Upgrade Checks

### 2.1 Check Available Versions
```bash
# List available versions
gcloud container get-server-config --zone $ZONE --format="yaml(validMasterVersions,validNodeVersions)"

# Verify 1.33 is available
gcloud container get-server-config --zone $ZONE --format="value(validMasterVersions)" | grep "1.33"
```

### 2.2 Check for Deprecated APIs
```bash
# Check for deprecated API usage (if you have workloads)
kubectl get all --all-namespaces -o wide
kubectl api-resources --verbs=list --namespaced -o name | xargs -n 1 kubectl get --show-kind --ignore-not-found --all-namespaces
```

### 2.3 Document Current State
```bash
# Save current cluster info
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE > cluster-state-before-upgrade.yaml

# Save current workloads
kubectl get all --all-namespaces -o yaml > workloads-before-upgrade.yaml
```

## Step 3: Upgrade Control Plane

### 3.1 Start Control Plane Upgrade
```bash
# Upgrade the master/control plane to 1.33
gcloud container clusters upgrade $CLUSTER_NAME --master --cluster-version=1.33 --zone $ZONE

# This will prompt for confirmation. Type 'Y' and press Enter when asked.
```

### 3.2 Monitor Control Plane Upgrade
```bash
# Check upgrade status
gcloud container operations list --filter="targetLink:$CLUSTER_NAME"

# Wait for control plane upgrade to complete (this can take 10-20 minutes)
# You can also monitor in the GCP Console
```

### 3.3 Verify Control Plane Upgrade
```bash
# Verify master is upgraded
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion)"

# Test cluster connectivity
kubectl get nodes
kubectl cluster-info
```

## Step 4: Upgrade Node Pools

### 4.1 Upgrade default-pool
```bash
# Start upgrade of default-pool
gcloud container clusters upgrade $CLUSTER_NAME --node-pool=default-pool --cluster-version=1.33 --zone $ZONE

# This will prompt for confirmation. Type 'Y' and press Enter.
```

### 4.2 Monitor default-pool Upgrade
```bash
# Watch node status during upgrade
watch kubectl get nodes

# Check operations status
gcloud container operations list --filter="targetLink:$CLUSTER_NAME AND targetLink:default-pool"

# Monitor pods during node replacement
watch "kubectl get pods --all-namespaces | grep -v Running | grep -v Completed"
```

### 4.3 Verify default-pool Upgrade
```bash
# Check that all nodes in default-pool are upgraded
kubectl get nodes -o wide

# Verify node pool version
gcloud container node-pools describe default-pool --cluster=$CLUSTER_NAME --zone=$ZONE --format="value(version)"
```

### 4.4 Upgrade workload-pool
```bash
# Start upgrade of workload-pool
gcloud container clusters upgrade $CLUSTER_NAME --node-pool=workload-pool --cluster-version=1.33 --zone $ZONE

# This will prompt for confirmation. Type 'Y' and press Enter.
```

### 4.5 Monitor workload-pool Upgrade
```bash
# Watch node status during upgrade
watch kubectl get nodes

# Check operations status
gcloud container operations list --filter="targetLink:$CLUSTER_NAME AND targetLink:workload-pool"

# Monitor pods during node replacement
watch "kubectl get pods --all-namespaces | grep -v Running | grep -v Completed"
```

### 4.6 Verify workload-pool Upgrade
```bash
# Check that all nodes in workload-pool are upgraded
kubectl get nodes -o wide

# Verify node pool version
gcloud container node-pools describe workload-pool --cluster=$CLUSTER_NAME --zone=$ZONE --format="value(version)"
```

## Step 5: Post-Upgrade Verification

### 5.1 Verify All Components
```bash
# Check cluster version
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion)"

# Check all node versions
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion

# Verify all node pools
gcloud container node-pools list --cluster $CLUSTER_NAME --zone $ZONE
```

### 5.2 Check System Components
```bash
# Check system pods
kubectl get pods -n kube-system

# Check node status
kubectl get nodes -o wide

# Check for any issues
kubectl get events --sort-by=.metadata.creationTimestamp
```

### 5.3 Test Application Functionality
```bash
# List all workloads
kubectl get deployments --all-namespaces
kubectl get pods --all-namespaces

# Check for any failed pods
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

# Test a simple pod deployment (optional)
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Cluster is working"
```

## Step 6: Final Documentation

### 6.1 Document New State
```bash
# Save final cluster info
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE > cluster-state-after-upgrade.yaml

# Compare before and after (optional)
diff cluster-state-before-upgrade.yaml cluster-state-after-upgrade.yaml
```

### 6.2 Clean Up
```bash
# Remove temporary files (optional)
rm cluster-state-before-upgrade.yaml workloads-before-upgrade.yaml cluster-state-after-upgrade.yaml
```

## Troubleshooting Commands

If you encounter issues during the upgrade:

```bash
# Check cluster status
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE

# Check operations
gcloud container operations list --filter="targetLink:$CLUSTER_NAME"

# Check specific operation details
gcloud container operations describe [OPERATION_ID] --zone $ZONE

# Check node pool health
kubectl describe nodes

# Check for stuck pods
kubectl get pods --all-namespaces -o wide | grep -E "(Pending|Failed|Unknown)"

# Get detailed pod information
kubectl describe pod [POD_NAME] -n [NAMESPACE]

# Check cluster events
kubectl get events --sort-by=.metadata.creationTimestamp --all-namespaces
```

## Rollback Plan (Emergency Only)

If you need to rollback (note: this is complex and should be avoided):

```bash
# You cannot rollback the control plane, but you can rollback node pools
gcloud container clusters upgrade $CLUSTER_NAME --node-pool=[POOL_NAME] --cluster-version=1.32 --zone $ZONE
```

## Important Notes

1. **Timing**: Control plane upgrades typically take 10-20 minutes. Node pool upgrades depend on the number of nodes and can take 5-10 minutes per node.

2. **Disruption**: Node pool upgrades will cause pods to be rescheduled. Ensure your applications can handle this.

3. **Order**: Always upgrade the control plane first, then node pools.

4. **Monitoring**: Keep an eye on your applications throughout the process.

5. **Support**: If you encounter issues, check the GCP Console for detailed error messages.

## Success Criteria

✅ Control plane version shows 1.33  
✅ All nodes show kubelet version 1.33  
✅ All node pools show version 1.33  
✅ All system pods are running  
✅ Application workloads are running normally  
✅ No failed or pending pods (except expected ones)

Your upgrade is complete when all success criteria are met!