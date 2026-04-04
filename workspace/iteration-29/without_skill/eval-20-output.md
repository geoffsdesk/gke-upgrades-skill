# GKE Cluster Upgrade Runbook: 1.32 → 1.33

## Prerequisites
- `gcloud` CLI installed and authenticated
- `kubectl` configured to access your cluster
- Appropriate GKE permissions (container.clusters.update)

## Step 1: Initial Assessment and Backup

### 1.1 Set Environment Variables
```bash
export PROJECT_ID="your-project-id"
export CLUSTER_NAME="your-cluster-name"
export ZONE="us-west1-b"
```

### 1.2 Verify Current Cluster State
```bash
# Get cluster info
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID

# Check current versions
gcloud container clusters list --filter="name:$CLUSTER_NAME" --format="table(name,currentMasterVersion,currentNodeVersion,location)"

# List node pools
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID
```

### 1.3 Check Available Versions
```bash
# Check available versions for Regular channel
gcloud container get-server-config --zone=$ZONE --format="yaml(channels)"
```

### 1.4 Pre-upgrade Health Check
```bash
# Check cluster status
kubectl get nodes -o wide

# Check system pods
kubectl get pods -n kube-system

# Check for any failing pods
kubectl get pods --all-namespaces --field-selector=status.phase!=Running,status.phase!=Succeeded

# Check cluster events for issues
kubectl get events --sort-by=.metadata.creationTimestamp -A | tail -20
```

### 1.5 Document Current Workloads
```bash
# List all deployments
kubectl get deployments -A -o wide > pre-upgrade-deployments.txt

# List all services
kubectl get services -A -o wide > pre-upgrade-services.txt

# List all pods
kubectl get pods -A -o wide > pre-upgrade-pods.txt
```

## Step 2: Pre-upgrade Validation

### 2.1 Check for Deprecated APIs
```bash
# Check for deprecated APIs (if you have any manifests)
kubectl api-resources --verbs=list --namespaced -o name | xargs -n 1 kubectl get --show-kind --ignore-not-found -A
```

### 2.2 Verify Node Pool Configuration
```bash
# Get detailed node pool info
gcloud container node-pools describe default-pool --cluster=$CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID
gcloud container node-pools describe workload-pool --cluster=$CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID
```

## Step 3: Upgrade Control Plane

### 3.1 Start Control Plane Upgrade
```bash
# Upgrade control plane to 1.33
gcloud container clusters upgrade $CLUSTER_NAME \
    --master \
    --cluster-version=1.33 \
    --zone=$ZONE \
    --project=$PROJECT_ID
```

**Note:** This will take 10-20 minutes. The API server will be briefly unavailable during the upgrade.

### 3.2 Monitor Control Plane Upgrade
```bash
# Check upgrade status
gcloud container operations list --filter="targetLink:$CLUSTER_NAME" --limit=5

# Wait for completion - run this periodically
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID --format="value(status)"
```

### 3.3 Verify Control Plane Upgrade
```bash
# Verify master version
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID --format="value(currentMasterVersion)"

# Test kubectl connectivity
kubectl version --short
kubectl get nodes
```

## Step 4: Upgrade Node Pools

### 4.1 Upgrade default-pool
```bash
# Start node pool upgrade
gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool=default-pool \
    --zone=$ZONE \
    --project=$PROJECT_ID
```

### 4.2 Monitor default-pool Upgrade
```bash
# Monitor node status during upgrade
watch "kubectl get nodes -o wide"

# Check for any pod disruptions
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded

# Monitor upgrade operation
gcloud container operations list --filter="targetLink:$CLUSTER_NAME AND targetLink:default-pool" --limit=3
```

### 4.3 Verify default-pool Upgrade
```bash
# Verify all nodes in default-pool are upgraded
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool -o custom-columns="NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,STATUS:.status.conditions[-1].type"
```

### 4.4 Upgrade workload-pool
```bash
# Start workload-pool upgrade
gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool=workload-pool \
    --zone=$ZONE \
    --project=$PROJECT_ID
```

### 4.5 Monitor workload-pool Upgrade
```bash
# Monitor node status
watch "kubectl get nodes -o wide"

# Check pod status
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded

# Monitor operation
gcloud container operations list --filter="targetLink:$CLUSTER_NAME AND targetLink:workload-pool" --limit=3
```

### 4.6 Verify workload-pool Upgrade
```bash
# Verify all nodes in workload-pool are upgraded
kubectl get nodes -l cloud.google.com/gke-nodepool=workload-pool -o custom-columns="NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,STATUS:.status.conditions[-1].type"
```

## Step 5: Post-upgrade Validation

### 5.1 Verify All Components
```bash
# Check all nodes are on 1.33
kubectl get nodes -o custom-columns="NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,STATUS:.status.conditions[-1].type"

# Verify cluster info
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID --format="table(currentMasterVersion,currentNodeVersion,status)"
```

### 5.2 Application Health Check
```bash
# Check all pods are running
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded

# Compare with pre-upgrade state
kubectl get deployments -A -o wide > post-upgrade-deployments.txt
kubectl get services -A -o wide > post-upgrade-services.txt
kubectl get pods -A -o wide > post-upgrade-pods.txt

# Check for differences
diff pre-upgrade-deployments.txt post-upgrade-deployments.txt
```

### 5.3 System Component Verification
```bash
# Check kube-system pods
kubectl get pods -n kube-system

# Check cluster events for any issues
kubectl get events --sort-by=.metadata.creationTimestamp -A | tail -30

# Verify DNS is working
kubectl run test-dns --image=busybox --rm -it --restart=Never -- nslookup kubernetes.default
```

## Step 6: Cleanup and Documentation

### 6.1 Clean Up Test Resources
```bash
# Remove any test pods created during validation
kubectl delete pod test-dns --ignore-not-found=true
```

### 6.2 Document Completion
```bash
# Generate final cluster state report
echo "=== UPGRADE COMPLETION REPORT ===" > upgrade-completion-report.txt
echo "Date: $(date)" >> upgrade-completion-report.txt
echo "Cluster: $CLUSTER_NAME" >> upgrade-completion-report.txt
echo "Zone: $ZONE" >> upgrade-completion-report.txt
echo "" >> upgrade-completion-report.txt

gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID --format="table(name,currentMasterVersion,currentNodeVersion,status)" >> upgrade-completion-report.txt

echo "" >> upgrade-completion-report.txt
echo "Node Status:" >> upgrade-completion-report.txt
kubectl get nodes -o wide >> upgrade-completion-report.txt
```

## Emergency Rollback (If Needed)

**⚠️ Only use if there are critical issues post-upgrade**

```bash
# You cannot rollback the control plane, but you can create new node pools with older versions if absolutely necessary
# Contact Google Cloud Support for control plane issues

# For node pool issues, you might need to:
# 1. Create a new node pool with the previous version
# 2. Migrate workloads
# 3. Delete the problematic node pool

# Example (only if absolutely necessary):
gcloud container node-pools create emergency-pool \
    --cluster=$CLUSTER_NAME \
    --zone=$ZONE \
    --node-version=1.32 \
    --num-nodes=1 \
    --machine-type=e2-medium \
    --project=$PROJECT_ID
```

## Troubleshooting Common Issues

### If nodes are stuck in upgrade:
```bash
# Check node pool status
gcloud container node-pools describe POOL_NAME --cluster=$CLUSTER_NAME --zone=$ZONE

# Check for resource constraints
kubectl describe nodes

# Check for PodDisruptionBudgets blocking upgrades
kubectl get pdb -A
```

### If pods are stuck pending:
```bash
# Check node resources
kubectl top nodes

# Check pod resource requests
kubectl describe pod POD_NAME -n NAMESPACE

# Check for scheduling issues
kubectl get events --field-selector reason=FailedScheduling
```

## Success Criteria

✅ Control plane version shows 1.33  
✅ All nodes show kubelet version 1.33  
✅ All system pods in kube-system namespace are Running  
✅ All application pods are Running  
✅ kubectl commands work normally  
✅ No critical events in cluster event log  

**Total Expected Duration:** 45-90 minutes depending on cluster size and workload complexity.