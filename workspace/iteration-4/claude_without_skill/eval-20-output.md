# GKE Cluster Upgrade Runbook: 1.28 → 1.30

This runbook will guide you through upgrading your GKE Standard cluster from version 1.28 to 1.30 safely.

## Prerequisites

- `gcloud` CLI installed and authenticated
- `kubectl` configured to access your cluster
- Cluster admin permissions
- Maintenance window scheduled (expect 30-60 minutes)

## Phase 1: Pre-Upgrade Assessment

### Step 1: Set Environment Variables
```bash
export PROJECT_ID="your-project-id"
export CLUSTER_NAME="your-cluster-name"
export ZONE="us-west1-b"
export TARGET_VERSION="1.30"
```

### Step 2: Verify Current Cluster State
```bash
# Get cluster info
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID

# Check current versions
kubectl version --short

# List all nodes and their versions
kubectl get nodes -o wide

# Check node pools
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID
```

### Step 3: Check Available Versions
```bash
# Check available master versions
gcloud container get-server-config --zone=$ZONE --project=$PROJECT_ID

# Verify 1.30 is available for Regular channel
gcloud container get-server-config --zone=$ZONE --project=$PROJECT_ID --format="value(channels.REGULAR.validVersions[])" | grep "1.30"
```

### Step 4: Pre-Upgrade Health Check
```bash
# Check cluster health
kubectl get nodes
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

# Check for any failing pods
kubectl get pods --all-namespaces --field-selector=status.phase!=Running,status.phase!=Succeeded

# Verify system components
kubectl get pods -n kube-system

# Check for PodDisruptionBudgets
kubectl get pdb --all-namespaces
```

### Step 5: Backup Critical Resources
```bash
# Create backup directory
mkdir -p gke-upgrade-backup-$(date +%Y%m%d)
cd gke-upgrade-backup-$(date +%Y%m%d)

# Backup cluster configuration
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID > cluster-config-backup.yaml

# Backup all resources (optional but recommended)
kubectl get all --all-namespaces -o yaml > all-resources-backup.yaml

# Backup custom resources
kubectl get crd -o yaml > custom-resources-backup.yaml

# Backup persistent volumes
kubectl get pv,pvc --all-namespaces -o yaml > storage-backup.yaml
```

## Phase 2: Control Plane Upgrade

### Step 6: Upgrade Master/Control Plane
```bash
# Start master upgrade to 1.30
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --master \
    --cluster-version=$TARGET_VERSION \
    --quiet

# Monitor upgrade progress
watch -n 30 "gcloud container operations list --filter='operationType=UPGRADE_MASTER AND targetLink~$CLUSTER_NAME' --project=$PROJECT_ID"
```

**⏱️ Expected Time:** 10-15 minutes  
**⚠️ Note:** The API server will be briefly unavailable during this step.

### Step 7: Verify Master Upgrade
```bash
# Check cluster version
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID --format="value(currentMasterVersion)"

# Verify API server is responding
kubectl version --short

# Check system pods are running
kubectl get pods -n kube-system
```

## Phase 3: Node Pool Upgrades

### Step 8: Upgrade default-pool
```bash
# Check current node pool version
gcloud container node-pools describe default-pool \
    --cluster=$CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --format="value(version)"

# Start node pool upgrade
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --node-pool=default-pool \
    --cluster-version=$TARGET_VERSION \
    --quiet

# Monitor progress
watch -n 30 "kubectl get nodes -o wide"
```

**⏱️ Expected Time:** 15-20 minutes per node pool

### Step 9: Monitor default-pool Upgrade
```bash
# Watch nodes during upgrade
kubectl get nodes -w

# Check for any pod eviction issues
kubectl get pods --all-namespaces | grep -E "(Evicted|Pending)"

# Monitor cluster events
kubectl get events --sort-by='.firstTimestamp' -A
```

### Step 10: Upgrade workload-pool
```bash
# Wait for default-pool to complete, then upgrade workload-pool
gcloud container node-pools describe workload-pool \
    --cluster=$CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --format="value(version)"

# Start workload-pool upgrade
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --node-pool=workload-pool \
    --cluster-version=$TARGET_VERSION \
    --quiet
```

### Step 11: Monitor workload-pool Upgrade
```bash
# Monitor remaining upgrade
watch -n 30 "kubectl get nodes -o wide"

# Check all operations are complete
gcloud container operations list --project=$PROJECT_ID --filter="status=RUNNING"
```

## Phase 4: Post-Upgrade Verification

### Step 12: Verify All Components
```bash
# Check all nodes are on new version
kubectl get nodes -o wide

# Verify all node pools
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID

# Check cluster summary
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID --format="table(name,status,currentMasterVersion,currentNodeVersion,location)"
```

### Step 13: Application Health Check
```bash
# Check all pods are running
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

# Verify system components
kubectl get pods -n kube-system

# Check services
kubectl get svc --all-namespaces

# Verify ingress controllers (if any)
kubectl get ingress --all-namespaces

# Test DNS resolution
kubectl run test-dns --image=busybox --rm -it --restart=Never -- nslookup kubernetes.default.svc.cluster.local
```

### Step 14: Validate Application Functionality
```bash
# Check deployment status
kubectl get deployments --all-namespaces

# Verify replica counts
kubectl get rs --all-namespaces

# Check for any issues with persistent volumes
kubectl get pv,pvc --all-namespaces

# Test application endpoints (customize for your applications)
# Example: kubectl port-forward service/your-service 8080:80
```

## Phase 5: Cleanup and Documentation

### Step 15: Final Verification
```bash
# Generate upgrade report
echo "=== GKE Upgrade Report ===" > upgrade-report.txt
echo "Date: $(date)" >> upgrade-report.txt
echo "Cluster: $CLUSTER_NAME" >> upgrade-report.txt
echo "Zone: $ZONE" >> upgrade-report.txt
echo "Target Version: $TARGET_VERSION" >> upgrade-report.txt
echo "" >> upgrade-report.txt

# Final cluster state
kubectl version >> upgrade-report.txt
kubectl get nodes -o wide >> upgrade-report.txt
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID >> upgrade-report.txt

cat upgrade-report.txt
```

## Emergency Rollback Procedure

If issues occur during node pool upgrades:

```bash
# Check available versions for rollback
gcloud container get-server-config --zone=$ZONE --project=$PROJECT_ID

# Rollback node pool (only works if master wasn't upgraded)
# Note: You cannot rollback the master, only node pools
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --node-pool=POOL_NAME \
    --cluster-version=PREVIOUS_VERSION
```

## Troubleshooting Common Issues

### Issue: Pods stuck in Pending state
```bash
# Check node resources
kubectl describe nodes

# Check pod events
kubectl describe pod POD_NAME -n NAMESPACE

# Check for resource constraints
kubectl top nodes
kubectl top pods --all-namespaces
```

### Issue: Services not accessible
```bash
# Check service endpoints
kubectl get endpoints --all-namespaces

# Verify kube-proxy
kubectl get pods -n kube-system -l k8s-app=kube-proxy

# Check iptables rules (on nodes)
# This requires node SSH access
```

## Important Notes

- ✅ **Master upgrades are automatic and cannot be rolled back**
- ✅ **Node pool upgrades replace nodes one by one**
- ✅ **Workloads will be rescheduled during node upgrades**
- ✅ **PodDisruptionBudgets will be respected**
- ⚠️ **Plan for brief API server downtime during master upgrade**
- ⚠️ **Ensure applications can handle pod restarts**

## Success Criteria

The upgrade is successful when:
- [ ] All nodes show version 1.30.x
- [ ] All pods are Running/Completed
- [ ] All services are accessible
- [ ] Applications respond correctly
- [ ] No degraded system components

**Total Expected Duration:** 45-75 minutes

Save this runbook and execute each phase in order. Take your time and don't skip the verification steps!