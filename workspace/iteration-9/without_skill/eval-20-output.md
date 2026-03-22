# GKE Cluster Upgrade Runbook: 1.31 → 1.32

## Prerequisites
- `kubectl` configured to access your cluster
- `gcloud` CLI installed and authenticated
- Basic understanding of your application architecture
- Maintenance window planned (upgrades can take 30-60+ minutes)

## Step 1: Initial Assessment and Backup

### 1.1 Verify Current Cluster State
```bash
# Get cluster info
gcloud container clusters describe CLUSTER_NAME --zone=us-west1-b

# Check current versions
kubectl version --short

# List all nodes and their versions
kubectl get nodes -o wide

# Check node pools
gcloud container node-pools list --cluster=CLUSTER_NAME --zone=us-west1-b
```

### 1.2 Document Current Workloads
```bash
# List all pods across namespaces
kubectl get pods --all-namespaces -o wide

# Check for any unhealthy pods before starting
kubectl get pods --all-namespaces --field-selector=status.phase!=Running

# List critical workloads
kubectl get deployments,statefulsets,daemonsets --all-namespaces
```

### 1.3 Backup Critical Resources
```bash
# Create backup directory
mkdir -p gke-upgrade-backup-$(date +%Y%m%d)
cd gke-upgrade-backup-$(date +%Y%m%d)

# Backup cluster configuration
gcloud container clusters describe CLUSTER_NAME --zone=us-west1-b > cluster-config-backup.yaml

# Backup all kubernetes resources
kubectl get all --all-namespaces -o yaml > all-resources-backup.yaml

# Backup ConfigMaps and Secrets
kubectl get configmaps --all-namespaces -o yaml > configmaps-backup.yaml
kubectl get secrets --all-namespaces -o yaml > secrets-backup.yaml

# Backup PVCs
kubectl get pvc --all-namespaces -o yaml > pvc-backup.yaml
```

## Step 2: Pre-Upgrade Checks

### 2.1 Check Available Versions
```bash
# Check available master versions
gcloud container get-server-config --zone=us-west1-b

# Verify 1.32 is available for your cluster
gcloud container clusters describe CLUSTER_NAME --zone=us-west1-b --format="value(currentMasterVersion,currentNodeVersion)"
```

### 2.2 Check Cluster Health
```bash
# Check cluster status
kubectl get componentstatuses

# Verify all nodes are Ready
kubectl get nodes

# Check for any resource constraints
kubectl top nodes
kubectl top pods --all-namespaces
```

### 2.3 Review Breaking Changes
```bash
# Check for deprecated APIs (important for 1.32)
kubectl api-resources --verbs=list --namespaced -o name | xargs -n 1 kubectl get --show-kind --ignore-not-found --all-namespaces

# Look for any warnings about deprecated APIs
kubectl get events --all-namespaces | grep -i deprecat
```

## Step 3: Control Plane Upgrade

### 3.1 Upgrade Master/Control Plane
```bash
# Start the master upgrade (this will take 10-20 minutes)
gcloud container clusters upgrade CLUSTER_NAME \
    --master \
    --cluster-version=1.32 \
    --zone=us-west1-b

# Monitor upgrade progress
gcloud container operations list --filter="zone:us-west1-b"
```

### 3.2 Verify Master Upgrade
```bash
# Wait for upgrade to complete, then verify
kubectl version --short

# Check cluster status
kubectl get nodes
kubectl get pods --all-namespaces

# Verify control plane version
gcloud container clusters describe CLUSTER_NAME --zone=us-west1-b --format="value(currentMasterVersion)"
```

## Step 4: Node Pool Upgrades

### 4.1 Upgrade default-pool
```bash
# Check current node pool version
gcloud container node-pools describe default-pool \
    --cluster=CLUSTER_NAME \
    --zone=us-west1-b \
    --format="value(version)"

# Start node pool upgrade
gcloud container clusters upgrade CLUSTER_NAME \
    --node-pool=default-pool \
    --cluster-version=1.32 \
    --zone=us-west1-b

# Monitor the upgrade progress
watch kubectl get nodes
```

### 4.2 Verify default-pool Upgrade
```bash
# Check all nodes in default-pool are updated
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool

# Verify pods are running properly
kubectl get pods --all-namespaces -o wide
```

### 4.3 Upgrade workload-pool
```bash
# Check current node pool version
gcloud container node-pools describe workload-pool \
    --cluster=CLUSTER_NAME \
    --zone=us-west1-b \
    --format="value(version)"

# Start node pool upgrade
gcloud container clusters upgrade CLUSTER_NAME \
    --node-pool=workload-pool \
    --cluster-version=1.32 \
    --zone=us-west1-b

# Monitor the upgrade progress
watch kubectl get nodes
```

### 4.4 Verify workload-pool Upgrade
```bash
# Check all nodes in workload-pool are updated
kubectl get nodes -l cloud.google.com/gke-nodepool=workload-pool

# Verify pods are running properly
kubectl get pods --all-namespaces -o wide
```

## Step 5: Post-Upgrade Verification

### 5.1 Comprehensive Health Check
```bash
# Verify all components
kubectl version --short
kubectl get componentstatuses
kubectl get nodes -o wide

# Check all pods are running
kubectl get pods --all-namespaces --field-selector=status.phase!=Running

# Verify services are accessible
kubectl get services --all-namespaces

# Check for any new events or errors
kubectl get events --all-namespaces --sort-by='.lastTimestamp' | tail -20
```

### 5.2 Application Testing
```bash
# Test critical application endpoints
# (Replace with your specific application tests)

# Check ingress/load balancer status
kubectl get ingress --all-namespaces
kubectl get services --all-namespaces -o wide

# Verify persistent volumes
kubectl get pv
kubectl get pvc --all-namespaces
```

### 5.3 Performance Verification
```bash
# Check resource usage
kubectl top nodes
kubectl top pods --all-namespaces

# Verify no pods are in CrashLoopBackOff or Error state
kubectl get pods --all-namespaces | grep -E "(CrashLoopBackOff|Error|ImagePullBackOff)"
```

## Step 6: Final Documentation

### 6.1 Document Upgrade Results
```bash
# Save final state
kubectl get nodes -o yaml > post-upgrade-nodes.yaml
kubectl get pods --all-namespaces -o yaml > post-upgrade-pods.yaml

# Get final version confirmation
gcloud container clusters describe CLUSTER_NAME --zone=us-west1-b --format="value(currentMasterVersion,currentNodeVersion)"
```

## Troubleshooting Commands

### If Pods Fail to Start
```bash
# Describe problematic pods
kubectl describe pod POD_NAME -n NAMESPACE

# Check pod logs
kubectl logs POD_NAME -n NAMESPACE --previous

# Check node conditions
kubectl describe node NODE_NAME
```

### If Upgrade Fails
```bash
# Check operation status
gcloud container operations list --filter="zone:us-west1-b"

# Get operation details
gcloud container operations describe OPERATION_ID --zone=us-west1-b

# Check cluster status
gcloud container clusters describe CLUSTER_NAME --zone=us-west1-b
```

### Emergency Rollback (if needed)
```bash
# Note: Control plane cannot be rolled back, but you can:
# 1. Create new node pools with older version
# 2. Migrate workloads
# 3. Delete upgraded node pools

# Create new node pool with older version (if absolutely necessary)
gcloud container node-pools create emergency-pool \
    --cluster=CLUSTER_NAME \
    --zone=us-west1-b \
    --node-version=1.31.X \
    --num-nodes=3
```

## Important Notes

1. **Replace `CLUSTER_NAME`** with your actual cluster name in all commands
2. **Regular channel** clusters auto-upgrade, so plan accordingly
3. **Node upgrades** use rolling updates - pods will be rescheduled
4. **Backup verification** - ensure you can restore from backups if needed
5. **Monitor closely** - each step should complete successfully before proceeding
6. **Test thoroughly** - verify all applications work after each major step

## Timeline Expectations
- Master upgrade: 10-20 minutes
- Each node pool upgrade: 15-30 minutes (depending on size)
- Total time: 45-90 minutes for the entire process

**⚠️ Always perform this upgrade during a planned maintenance window!**