# GKE Standard Cluster Upgrade Runbook: 1.32 → 1.33

## Prerequisites
- `gcloud` CLI installed and authenticated
- `kubectl` configured to access your cluster
- Basic understanding of kubectl commands

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
gcloud container clusters list --filter="name:$CLUSTER_NAME"

# Verify node pools
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE
```

### 1.3 Check Workload Health
```bash
# Check all pods status
kubectl get pods --all-namespaces

# Check for any failing pods
kubectl get pods --all-namespaces --field-selector=status.phase!=Running

# Check node status
kubectl get nodes -o wide

# Check cluster events for issues
kubectl get events --sort-by=.metadata.creationTimestamp
```

### 1.4 Document Current State
```bash
# Save current workload state
kubectl get deployments,statefulsets,daemonsets --all-namespaces -o yaml > pre-upgrade-workloads.yaml

# Save node information
kubectl get nodes -o yaml > pre-upgrade-nodes.yaml
```

## Step 2: Pre-Upgrade Validation

### 2.1 Check Available Versions
```bash
# List available master versions
gcloud container get-server-config --zone=$ZONE --format="value(validMasterVersions[0:5])"

# Verify 1.33 is available
gcloud container get-server-config --zone=$ZONE --format="yaml(validMasterVersions)" | grep "1.33"
```

### 2.2 Verify Application Health
```bash
# Check if applications have health checks
kubectl get deployments --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.spec.template.spec.containers[*].readinessProbe}{"\n"}{end}'

# Check PodDisruptionBudgets
kubectl get pdb --all-namespaces
```

## Step 3: Upgrade Control Plane

### 3.1 Upgrade Master Node
```bash
# Upgrade control plane to 1.33
gcloud container clusters upgrade $CLUSTER_NAME \
    --master \
    --cluster-version=1.33 \
    --zone=$ZONE \
    --project=$PROJECT_ID
```

**Note**: This operation typically takes 5-10 minutes. The cluster API will be briefly unavailable.

### 3.2 Verify Control Plane Upgrade
```bash
# Wait for upgrade to complete, then verify
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(currentMasterVersion)"

# Test cluster connectivity
kubectl cluster-info

# Check cluster status
kubectl get componentstatuses
```

## Step 4: Upgrade Node Pools

### 4.1 Check Node Pool Versions
```bash
# List current node pool versions
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE --format="table(name,version,status)"
```

### 4.2 Upgrade default-pool
```bash
# Upgrade default-pool nodes
gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool=default-pool \
    --cluster-version=1.33 \
    --zone=$ZONE \
    --project=$PROJECT_ID
```

**Monitor the upgrade:**
```bash
# Watch node status during upgrade
watch kubectl get nodes

# Check upgrade progress
gcloud container operations list --filter="targetLink:$CLUSTER_NAME"
```

### 4.3 Verify default-pool Upgrade
```bash
# Wait for all nodes to be Ready
kubectl get nodes

# Verify all nodes are on new version
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.nodeInfo.kubeletVersion}{"\n"}{end}'

# Check workload health after first pool upgrade
kubectl get pods --all-namespaces | grep -v Running
```

### 4.4 Upgrade workload-pool
```bash
# Upgrade workload-pool nodes
gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool=workload-pool \
    --cluster-version=1.33 \
    --zone=$ZONE \
    --project=$PROJECT_ID
```

**Monitor the upgrade:**
```bash
# Watch node status during upgrade
watch kubectl get nodes

# Monitor pod disruptions
kubectl get pods --all-namespaces -w
```

### 4.5 Verify workload-pool Upgrade
```bash
# Verify all nodes are upgraded
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.nodeInfo.kubeletVersion}{"\n"}{end}'

# Check all nodes are Ready
kubectl get nodes
```

## Step 5: Post-Upgrade Validation

### 5.1 Comprehensive Health Check
```bash
# Check all system pods
kubectl get pods -n kube-system

# Check all application pods
kubectl get pods --all-namespaces

# Verify no pods are stuck or failing
kubectl get pods --all-namespaces --field-selector=status.phase!=Running

# Check node conditions
kubectl describe nodes | grep -A 5 "Conditions:"
```

### 5.2 Application Validation
```bash
# Test a sample application endpoint (replace with your app)
kubectl get services --all-namespaces

# Check ingress status if you have ingresses
kubectl get ingress --all-namespaces

# Verify persistent volumes
kubectl get pv,pvc --all-namespaces
```

### 5.3 Verify Final State
```bash
# Confirm cluster version
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(currentMasterVersion)"

# Confirm all node pools are upgraded
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE --format="table(name,version,status)"

# Final cluster overview
kubectl get nodes,pods --all-namespaces
```

## Step 6: Cleanup and Documentation

### 6.1 Save Post-Upgrade State
```bash
# Save current state for comparison
kubectl get deployments,statefulsets,daemonsets --all-namespaces -o yaml > post-upgrade-workloads.yaml
kubectl get nodes -o yaml > post-upgrade-nodes.yaml
```

### 6.2 Clean Up Backup Files (Optional)
```bash
# Remove backup files if everything is working
rm pre-upgrade-workloads.yaml pre-upgrade-nodes.yaml post-upgrade-workloads.yaml post-upgrade-nodes.yaml
```

## Troubleshooting Common Issues

### If Control Plane Upgrade Fails:
```bash
# Check operation status
gcloud container operations list --filter="targetLink:$CLUSTER_NAME"

# Get operation details
gcloud container operations describe OPERATION_ID --zone=$ZONE
```

### If Node Pool Upgrade Fails:
```bash
# Check node pool status
gcloud container node-pools describe POOL_NAME --cluster=$CLUSTER_NAME --zone=$ZONE

# Check for node issues
kubectl describe nodes | grep -A 10 "Events:"

# Force refresh node status
kubectl get nodes --no-headers | awk '{print $1}' | xargs -I {} kubectl describe node {}
```

### If Pods Don't Start After Upgrade:
```bash
# Check pod events
kubectl describe pod POD_NAME -n NAMESPACE

# Check resource availability
kubectl top nodes
kubectl top pods --all-namespaces

# Check for scheduling issues
kubectl get pods --all-namespaces -o wide | grep Pending
```

## Expected Timeline
- **Control Plane Upgrade**: 5-10 minutes
- **Each Node Pool Upgrade**: 10-20 minutes per pool (depends on pool size)
- **Total Expected Time**: 25-50 minutes

## Success Criteria
✅ Control plane shows version 1.33  
✅ All node pools show version 1.33  
✅ All nodes are in "Ready" state  
✅ All pods are "Running" (except completed jobs)  
✅ Applications are accessible and functional  
✅ No cluster events showing errors  

Your upgrade is complete when all success criteria are met!