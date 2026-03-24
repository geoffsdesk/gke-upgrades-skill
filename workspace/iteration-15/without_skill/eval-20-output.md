# GKE Cluster Upgrade Runbook: 1.32 → 1.33

## Prerequisites
- `gcloud` CLI installed and authenticated
- `kubectl` configured for your cluster
- Cluster admin permissions

## Step 1: Initial Setup and Verification

### 1.1 Set Environment Variables
```bash
export PROJECT_ID="your-project-id"
export CLUSTER_NAME="your-cluster-name"
export ZONE="us-west1-b"
```

### 1.2 Get Current Cluster Credentials
```bash
gcloud container clusters get-credentials $CLUSTER_NAME --zone $ZONE --project $PROJECT_ID
```

### 1.3 Verify Current State
```bash
# Check cluster version
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion,currentNodeVersion)"

# Check node pool versions
gcloud container node-pools list --cluster $CLUSTER_NAME --zone $ZONE

# Check node status
kubectl get nodes -o wide
```

### 1.4 Check Available Versions
```bash
gcloud container get-server-config --zone $ZONE --format="yaml(validMasterVersions,validNodeVersions)"
```

## Step 2: Pre-Upgrade Checks

### 2.1 Check Cluster Health
```bash
# Check cluster status
kubectl get nodes
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

# Check system components
kubectl get pods -n kube-system
```

### 2.2 Backup Critical Data (if applicable)
```bash
# List persistent volumes
kubectl get pv

# Export important configurations
kubectl get configmaps --all-namespaces -o yaml > configmaps-backup.yaml
kubectl get secrets --all-namespaces -o yaml > secrets-backup.yaml
```

### 2.3 Check Pod Disruption Budgets
```bash
kubectl get pdb --all-namespaces
```

## Step 3: Control Plane Upgrade

### 3.1 Upgrade Master/Control Plane
```bash
# Upgrade control plane to 1.33 (use latest patch version)
gcloud container clusters upgrade $CLUSTER_NAME \
    --master \
    --cluster-version=1.33 \
    --zone $ZONE \
    --project $PROJECT_ID
```

**Note:** This will take 10-20 minutes. The API will be briefly unavailable.

### 3.2 Verify Control Plane Upgrade
```bash
# Wait for upgrade to complete, then verify
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion)"

# Test API connectivity
kubectl get nodes
```

## Step 4: Node Pool Upgrades

### 4.1 Upgrade default-pool
```bash
# Start upgrade of default-pool
gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool=default-pool \
    --zone $ZONE \
    --project $PROJECT_ID
```

### 4.2 Monitor default-pool Upgrade
```bash
# Watch nodes being replaced (run in separate terminal)
watch kubectl get nodes

# Check upgrade status
gcloud container operations list --filter="targetLink:$CLUSTER_NAME"
```

### 4.3 Wait for default-pool Completion
```bash
# Check all nodes in default-pool are ready and on new version
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool
```

### 4.4 Upgrade workload-pool
```bash
# Start upgrade of workload-pool
gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool=workload-pool \
    --zone $ZONE \
    --project $PROJECT_ID
```

### 4.5 Monitor workload-pool Upgrade
```bash
# Watch nodes being replaced
watch kubectl get nodes

# Check specific workload-pool nodes
kubectl get nodes -l cloud.google.com/gke-nodepool=workload-pool
```

## Step 5: Post-Upgrade Verification

### 5.1 Verify All Components
```bash
# Check all nodes are on new version
kubectl get nodes -o wide

# Verify all system pods are running
kubectl get pods -n kube-system

# Check cluster info
kubectl cluster-info
```

### 5.2 Verify Application Health
```bash
# Check all application pods
kubectl get pods --all-namespaces

# Check services
kubectl get services --all-namespaces

# Test a sample application (if you have one)
kubectl get deployments --all-namespaces
```

### 5.3 Final Cluster Status Check
```bash
# Get final cluster details
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="yaml(currentMasterVersion,nodePools[].version,status)"
```

## Step 6: Cleanup and Documentation

### 6.1 Clean Up Old Resources (if any)
```bash
# Check for any old replica sets
kubectl get rs --all-namespaces | grep " 0 "

# Clean up completed jobs older than 1 day (optional)
kubectl get jobs --all-namespaces --field-selector status.successful=1
```

### 6.2 Update Documentation
Document the following:
- Upgrade completion time
- Any issues encountered
- Current cluster version: 1.33
- Next recommended upgrade window

## Troubleshooting Commands

### If Nodes Seem Stuck
```bash
# Check node conditions
kubectl describe nodes

# Check events
kubectl get events --sort-by=.metadata.creationTimestamp

# Check operation status
gcloud container operations list --filter="targetLink:$CLUSTER_NAME" --limit=5
```

### If Pods Are Pending
```bash
# Check pod status and events
kubectl describe pods <pod-name> -n <namespace>

# Check resource availability
kubectl top nodes
kubectl describe nodes
```

### Emergency Rollback (if needed)
```bash
# Note: Control plane cannot be rolled back, but you can:
# 1. Create new node pools with old version (if available)
# 2. Migrate workloads
gcloud container node-pools create emergency-pool \
    --cluster=$CLUSTER_NAME \
    --zone=$ZONE \
    --node-version=1.32.x-gke.x
```

## Important Notes

1. **Timing:** Plan for 1-2 hours total upgrade time
2. **Disruption:** Workloads will be rescheduled during node upgrades
3. **Regular Channel:** Future upgrades will happen automatically
4. **Monitoring:** Keep an eye on your applications during the upgrade
5. **Rollback:** Control plane upgrades cannot be rolled back

## Success Criteria

✅ Control plane shows version 1.33.x  
✅ All nodes show version 1.33.x  
✅ All system pods in kube-system namespace are Running  
✅ All application pods are Running  
✅ Services are accessible  
✅ No critical events in cluster  

The upgrade is complete when all criteria are met!