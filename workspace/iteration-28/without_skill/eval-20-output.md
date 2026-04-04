# GKE Standard Cluster Upgrade Runbook: 1.32 → 1.33

## Prerequisites
- kubectl configured and authenticated to your cluster
- gcloud CLI installed and authenticated
- Basic understanding of your applications running on the cluster

## Step 1: Initial Assessment and Backup

### 1.1 Set Environment Variables
```bash
export PROJECT_ID=$(gcloud config get-value project)
export CLUSTER_NAME="your-cluster-name"  # Replace with actual cluster name
export ZONE="us-west1-b"
```

### 1.2 Verify Current Cluster Status
```bash
# Get cluster info
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE

# Check current versions
kubectl version --short

# List all nodes and their versions
kubectl get nodes -o wide
```

### 1.3 Document Current State
```bash
# Save current node pool information
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE > pre-upgrade-nodepools.txt

# Save current workload information
kubectl get deployments,daemonsets,statefulsets --all-namespaces > pre-upgrade-workloads.txt

# Check for any problematic pods
kubectl get pods --all-namespaces --field-selector=status.phase!=Running
```

### 1.4 Backup Critical Resources (Recommended)
```bash
# Backup all deployments
kubectl get deployments --all-namespaces -o yaml > backup-deployments.yaml

# Backup all services
kubectl get services --all-namespaces -o yaml > backup-services.yaml

# Backup all configmaps and secrets (be careful with secrets)
kubectl get configmaps --all-namespaces -o yaml > backup-configmaps.yaml
```

## Step 2: Pre-Upgrade Health Checks

### 2.1 Check Cluster Health
```bash
# Check cluster status
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(status)"

# Verify all nodes are ready
kubectl get nodes
kubectl top nodes  # Check resource usage
```

### 2.2 Check Application Health
```bash
# Check for any failing pods
kubectl get pods --all-namespaces --field-selector=status.phase!=Running

# Check recent events for any issues
kubectl get events --all-namespaces --sort-by='.lastTimestamp' | tail -20
```

### 2.3 Verify Available Versions
```bash
# Check available master versions
gcloud container get-server-config --zone=$ZONE --format="value(validMasterVersions[0:5])"

# Verify 1.33 is available
gcloud container get-server-config --zone=$ZONE --format="yaml(validMasterVersions)" | grep "1.33"
```

## Step 3: Plan the Upgrade Strategy

### 3.1 Check Pod Disruption Budgets
```bash
# List all PodDisruptionBudgets
kubectl get pdb --all-namespaces

# Review each PDB to understand disruption tolerance
kubectl describe pdb --all-namespaces
```

### 3.2 Plan Maintenance Window
- **Master upgrade**: ~10-20 minutes (API server briefly unavailable)
- **Node pool upgrade**: ~20-40 minutes per node pool
- **Total estimated time**: 1-2 hours

## Step 4: Upgrade the Control Plane (Master)

### 4.1 Start Master Upgrade
```bash
# Upgrade master to 1.33 (use specific patch version)
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --master \
    --cluster-version=1.33.0-gke.1000  # Use actual available version
```

**⚠️ IMPORTANT**: During master upgrade (5-20 minutes):
- kubectl commands will fail intermittently
- Applications continue running normally
- No new deployments/scaling possible

### 4.2 Monitor Master Upgrade
```bash
# Check upgrade status (run in separate terminal)
watch "gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format='value(status)'"
```

### 4.3 Verify Master Upgrade
```bash
# Verify master version after upgrade completes
kubectl version --short

# Ensure cluster is running
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(status)"

# Test basic functionality
kubectl get nodes
kubectl get pods --all-namespaces
```

## Step 5: Upgrade Node Pools

### 5.1 Choose Upgrade Strategy

**Option A: Rolling Update (Recommended - Less Disruptive)**
```bash
# Upgrade default-pool with rolling update
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --node-pool=default-pool \
    --cluster-version=1.33.0-gke.1000

# Wait for completion, then upgrade workload-pool
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --node-pool=workload-pool \
    --cluster-version=1.33.0-gke.1000
```

**Option B: Blue-Green Update (More Control)**
```bash
# This approach creates new nodes before removing old ones
# We'll use Option A for simplicity in this runbook
```

### 5.2 Monitor Node Pool Upgrade Progress

**Open a separate terminal for monitoring:**
```bash
# Terminal 1: Watch nodes
watch "kubectl get nodes -o wide"

# Terminal 2: Watch pods
watch "kubectl get pods --all-namespaces | grep -v Running"

# Terminal 3: Watch events
kubectl get events --all-namespaces -w
```

### 5.3 Upgrade First Node Pool (default-pool)
```bash
echo "Starting upgrade of default-pool..."
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --node-pool=default-pool \
    --cluster-version=1.33.0-gke.1000
```

**During node pool upgrade, you'll see:**
- New nodes appearing with v1.33
- Pods being drained from old nodes
- Old nodes being deleted
- Pods rescheduled to new nodes

### 5.4 Verify First Node Pool Upgrade
```bash
# Check that all nodes in default-pool are upgraded
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool

# Verify applications are healthy
kubectl get pods --all-namespaces --field-selector=status.phase!=Running
```

### 5.5 Upgrade Second Node Pool (workload-pool)
```bash
echo "Starting upgrade of workload-pool..."
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --node-pool=workload-pool \
    --cluster-version=1.33.0-gke.1000
```

### 5.6 Verify Second Node Pool Upgrade
```bash
# Check that all nodes in workload-pool are upgraded
kubectl get nodes -l cloud.google.com/gke-nodepool=workload-pool

# Verify all nodes are now on v1.33
kubectl get nodes -o wide
```

## Step 6: Post-Upgrade Verification

### 6.1 Comprehensive Health Check
```bash
# Verify cluster status
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(status)"

# Check all nodes are Ready and on correct version
kubectl get nodes -o wide

# Verify all system pods are running
kubectl get pods -n kube-system

# Check for any failing pods across all namespaces
kubectl get pods --all-namespaces --field-selector=status.phase!=Running
```

### 6.2 Application Verification
```bash
# Test a simple deployment to verify functionality
kubectl create deployment test-upgrade --image=nginx:latest
kubectl wait --for=condition=available --timeout=300s deployment/test-upgrade
kubectl delete deployment test-upgrade

# Check your specific applications
kubectl get deployments --all-namespaces
kubectl get services --all-namespaces
```

### 6.3 Performance Check
```bash
# Check node resource usage
kubectl top nodes

# Check pod resource usage
kubectl top pods --all-namespaces
```

## Step 7: Cleanup and Documentation

### 7.1 Save Post-Upgrade State
```bash
# Document final state
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE > post-upgrade-nodepools.txt
kubectl get deployments,daemonsets,statefulsets --all-namespaces > post-upgrade-workloads.txt
kubectl version --short > post-upgrade-versions.txt
```

### 7.2 Compare Before/After
```bash
# Compare node pools
diff pre-upgrade-nodepools.txt post-upgrade-nodepools.txt

# Compare workloads
diff pre-upgrade-workloads.txt post-upgrade-workloads.txt
```

## Troubleshooting Common Issues

### If Master Upgrade Fails:
```bash
# Check cluster status
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE

# Try the upgrade again
gcloud container clusters upgrade $CLUSTER_NAME --zone=$ZONE --master --cluster-version=1.33.0-gke.1000
```

### If Node Pool Upgrade Stalls:
```bash
# Check for pods that can't be evicted
kubectl get pods --all-namespaces --field-selector=status.phase=Pending

# Check PodDisruptionBudgets
kubectl get pdb --all-namespaces

# Manually drain problematic nodes if needed (advanced)
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data
```

### If Pods Won't Start After Upgrade:
```bash
# Check pod events
kubectl describe pod POD_NAME -n NAMESPACE

# Check node resources
kubectl describe node NODE_NAME

# Check for image pull issues
kubectl get events --all-namespaces | grep -i "pull"
```

## Emergency Rollback (If Needed)

**⚠️ Note**: GKE doesn't support downgrading. If major issues occur:

1. **For applications**: Redeploy previous application versions
2. **For node pools**: Create new node pools with older versions (not recommended)
3. **For cluster**: May need to restore from backup to new cluster

## Success Criteria Checklist

- [ ] Master is running Kubernetes v1.33.x
- [ ] All nodes are running Kubernetes v1.33.x
- [ ] All nodes show "Ready" status
- [ ] All system pods in kube-system namespace are Running
- [ ] No pods stuck in Pending/CrashLoopBackOff state
- [ ] Applications are accessible and functioning normally
- [ ] Cluster status shows "RUNNING"

## Final Notes

- **Total upgrade time**: Typically 1-2 hours
- **API availability**: Brief interruptions during master upgrade only
- **Application availability**: Maintained throughout (with proper PDBs)
- **Monitoring**: Keep monitoring applications for 24-48 hours post-upgrade

Remember to update your CI/CD pipelines and documentation to reflect the new Kubernetes version!