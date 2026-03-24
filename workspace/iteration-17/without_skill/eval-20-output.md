# GKE Cluster Upgrade Runbook: 1.32 → 1.33

## Prerequisites & Setup

### 1. Verify Current Setup
```bash
# Set your project and cluster variables
export PROJECT_ID="your-project-id"
export CLUSTER_NAME="your-cluster-name"
export ZONE="us-west1-b"

# Get current cluster info
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID

# Verify current versions
gcloud container clusters list --filter="name:$CLUSTER_NAME" --format="table(name,currentMasterVersion,currentNodeVersion,location)"

# Check node pool versions
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE --format="table(name,version,status)"
```

### 2. Pre-Upgrade Health Check
```bash
# Check cluster status
kubectl get nodes

# Check system pods
kubectl get pods -n kube-system

# Check workload health
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

# Check for any disrupted pods
kubectl get poddisruptionbudgets --all-namespaces
```

## Phase 1: Control Plane Upgrade

### 3. Check Available Versions
```bash
# See available versions for your cluster
gcloud container get-server-config --zone=$ZONE --format="yaml(validMasterVersions,validNodeVersions)"

# Verify 1.33 is available
gcloud container get-server-config --zone=$ZONE --format="value(validMasterVersions)" | grep "1.33"
```

### 4. Upgrade Control Plane
```bash
# Start control plane upgrade (this will take 5-15 minutes)
gcloud container clusters upgrade $CLUSTER_NAME \
    --master \
    --cluster-version=1.33.0-gke.latest \
    --zone=$ZONE \
    --project=$PROJECT_ID

# Monitor upgrade progress
gcloud container operations list --zone=$ZONE --filter="operationType:UPGRADE_MASTER AND targetLink~$CLUSTER_NAME"
```

### 5. Verify Control Plane Upgrade
```bash
# Wait for upgrade to complete, then verify
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(currentMasterVersion)"

# Test cluster connectivity
kubectl cluster-info

# Verify API server is responsive
kubectl get nodes
```

## Phase 2: Node Pool Upgrades

### 6. Pre-Node Upgrade Preparation
```bash
# Check current node pool status
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE

# Identify pods that might need special attention
kubectl get pods --all-namespaces -o wide | grep -E "(DaemonSet|StatefulSet)"

# Check for any single-replica deployments (these will have downtime)
kubectl get deployments --all-namespaces --field-selector spec.replicas=1
```

### 7. Upgrade default-pool
```bash
# Upgrade default-pool (this recreates nodes, expect 10-30 minutes depending on size)
gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool=default-pool \
    --cluster-version=1.33.0-gke.latest \
    --zone=$ZONE \
    --project=$PROJECT_ID

# Monitor the upgrade
watch "kubectl get nodes"

# Or monitor via gcloud
gcloud container operations list --zone=$ZONE --filter="operationType:UPGRADE_NODES AND targetLink~default-pool"
```

### 8. Verify default-pool Upgrade
```bash
# Check node versions
kubectl get nodes -o wide

# Verify pods are rescheduled and running
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

# Check for any failed pods
kubectl get events --sort-by='.lastTimestamp' | tail -20
```

### 9. Upgrade workload-pool
```bash
# Upgrade workload-pool
gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool=workload-pool \
    --cluster-version=1.33.0-gke.latest \
    --zone=$ZONE \
    --project=$PROJECT_ID

# Monitor the upgrade
watch "kubectl get nodes"
```

### 10. Verify workload-pool Upgrade
```bash
# Final verification - all nodes should be on 1.33
kubectl get nodes -o wide

# Check node pool status
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE --format="table(name,version,status)"
```

## Phase 3: Post-Upgrade Validation

### 11. Comprehensive Health Check
```bash
# Verify all nodes are Ready
kubectl get nodes

# Check all system pods are running
kubectl get pods -n kube-system

# Check all workload pods
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed | grep -v Succeeded

# Verify cluster info
kubectl cluster-info

# Check for any events indicating issues
kubectl get events --sort-by='.lastTimestamp' --all-namespaces | tail -30
```

### 12. Application Validation
```bash
# Test a few key workloads (customize these commands for your apps)
kubectl get deployments --all-namespaces
kubectl get services --all-namespaces

# Port-forward to test a service (example)
# kubectl port-forward service/your-service 8080:80 -n your-namespace

# Check ingress/load balancers if you have them
kubectl get ingress --all-namespaces
```

### 13. Final Verification
```bash
# Confirm final versions
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="table(currentMasterVersion,currentNodeVersion)"

# Verify cluster is fully operational
kubectl top nodes 2>/dev/null || echo "Metrics server may still be starting"
```

## Troubleshooting Commands

### If Nodes Appear Stuck
```bash
# Check node conditions
kubectl describe nodes

# Look for specific errors
kubectl get events --field-selector type=Warning --all-namespaces

# Check node pool operation status
gcloud container operations list --zone=$ZONE
```

### If Pods Won't Start
```bash
# Check pod events
kubectl describe pod <pod-name> -n <namespace>

# Check resource constraints
kubectl top nodes
kubectl describe nodes | grep -A 5 "Allocated resources"
```

### Emergency Rollback (Only for node pools, master cannot be rolled back)
```bash
# If you need to rollback node pools (this will recreate nodes again)
gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool=<pool-name> \
    --cluster-version=1.32.x-gke.xxx \
    --zone=$ZONE \
    --project=$PROJECT_ID
```

## Expected Timeline
- **Control Plane Upgrade**: 5-15 minutes
- **Each Node Pool Upgrade**: 10-30 minutes (depends on node count)
- **Total Expected Time**: 30-60 minutes

## Important Notes
- **Node upgrades involve replacing nodes** - pods will be drained and rescheduled
- **Single-replica deployments will experience downtime** during node replacement
- **DaemonSets and system pods** will be automatically rescheduled
- **Regular channel clusters** auto-upgrade eventually, but manual upgrades give you control over timing
- **Always test in non-production first** if possible

## Post-Upgrade Cleanup
```bash
# Clean up any evicted pods (if any)
kubectl get pods --all-namespaces --field-selector=status.phase=Failed

# If you see evicted pods, clean them up:
kubectl get pods --all-namespaces --field-selector=status.phase=Failed -o json | kubectl delete -f -
```

Save this runbook and execute each phase sequentially. Don't proceed to the next phase until the current one completes successfully.