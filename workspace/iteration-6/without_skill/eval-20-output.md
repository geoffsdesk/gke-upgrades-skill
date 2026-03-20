# GKE Cluster Upgrade Runbook: 1.28 → 1.30

## Prerequisites
- `gcloud` CLI installed and authenticated
- `kubectl` configured to access your cluster
- Basic understanding of your workloads and their criticality

## Phase 1: Pre-Upgrade Assessment and Backup

### Step 1: Set Environment Variables
```bash
export PROJECT_ID="your-project-id"
export CLUSTER_NAME="your-cluster-name"
export ZONE="us-west1-b"
```

### Step 2: Verify Current Cluster State
```bash
# Get cluster info
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --project=$PROJECT_ID

# Check current versions
gcloud container clusters list --filter="name=$CLUSTER_NAME"

# Verify node pools
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE

# Check node status
kubectl get nodes -o wide
```

### Step 3: Check Available Versions
```bash
# Check available master versions
gcloud container get-server-config --zone=$ZONE --format="yaml(validMasterVersions)"

# Verify upgrade path (should show 1.29.x as next available)
gcloud container get-server-config --zone=$ZONE --format="table(validMasterVersions[0:5])"
```

### Step 4: Document Current Workloads
```bash
# List all workloads
kubectl get deployments,daemonsets,statefulsets --all-namespaces -o wide > pre-upgrade-workloads.txt

# Check pod disruption budgets
kubectl get pdb --all-namespaces > pre-upgrade-pdbs.txt

# List persistent volumes
kubectl get pv,pvc --all-namespaces > pre-upgrade-storage.txt
```

### Step 5: Create Backup (if needed)
```bash
# Backup cluster configuration
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE > cluster-backup-$(date +%Y%m%d).yaml

# Export important resources (adjust namespaces as needed)
kubectl get all --all-namespaces -o yaml > all-resources-backup-$(date +%Y%m%d).yaml
```

## Phase 2: First Upgrade (1.28 → 1.29)

### Step 6: Upgrade Control Plane to 1.29
```bash
# Get the latest 1.29 version
MASTER_VERSION=$(gcloud container get-server-config --zone=$ZONE --format="value(validMasterVersions[0])" | grep "1.29")

# Start master upgrade
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --master \
    --cluster-version=$MASTER_VERSION \
    --project=$PROJECT_ID

# Monitor upgrade progress
gcloud container operations list --filter="name~upgrade AND targetLink~$CLUSTER_NAME"
```

**⏱️ Wait Time:** Master upgrade typically takes 5-10 minutes. Wait for completion before proceeding.

### Step 7: Verify Master Upgrade
```bash
# Check master version
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(currentMasterVersion)"

# Verify cluster is healthy
kubectl cluster-info
kubectl get nodes
```

### Step 8: Upgrade Node Pool 1 (default-pool)
```bash
# Upgrade default-pool nodes
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --node-pool=default-pool \
    --project=$PROJECT_ID

# Monitor node upgrade progress
watch kubectl get nodes
```

**⏱️ Wait Time:** Node upgrades take 10-20 minutes depending on pool size.

### Step 9: Verify default-pool Upgrade
```bash
# Check all nodes are on new version
kubectl get nodes -o wide

# Verify workloads are healthy
kubectl get pods --all-namespaces | grep -v Running
kubectl get deployments --all-namespaces
```

### Step 10: Upgrade Node Pool 2 (workload-pool)
```bash
# Upgrade workload-pool nodes
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --node-pool=workload-pool \
    --project=$PROJECT_ID

# Monitor progress
watch kubectl get nodes
```

### Step 11: Verify All Nodes on 1.29
```bash
# Confirm all nodes upgraded
kubectl get nodes -o wide

# Check workload health
kubectl get pods --all-namespaces --field-selector=status.phase!=Running
kubectl top nodes (if metrics-server is installed)
```

## Phase 3: Second Upgrade (1.29 → 1.30)

### Step 12: Wait and Verify Stability
**⚠️ Important:** Wait at least 30 minutes after 1.29 upgrade completion to ensure stability.

```bash
# Monitor cluster health
kubectl get nodes
kubectl get pods --all-namespaces | grep -E "(Error|CrashLoop|Pending)"

# Check cluster events for issues
kubectl get events --all-namespaces --sort-by='.lastTimestamp' | tail -20
```

### Step 13: Get 1.30 Version
```bash
# Refresh available versions and get 1.30
gcloud container get-server-config --zone=$ZONE --format="table(validMasterVersions[0:5])"

MASTER_VERSION_130=$(gcloud container get-server-config --zone=$ZONE --format="value(validMasterVersions[0])" | grep "1.30")

echo "Will upgrade to: $MASTER_VERSION_130"
```

### Step 14: Upgrade Control Plane to 1.30
```bash
# Start master upgrade to 1.30
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --master \
    --cluster-version=$MASTER_VERSION_130 \
    --project=$PROJECT_ID

# Monitor upgrade
gcloud container operations list --filter="name~upgrade AND targetLink~$CLUSTER_NAME"
```

### Step 15: Verify Master on 1.30
```bash
# Check master version
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(currentMasterVersion)"

# Test cluster connectivity
kubectl cluster-info
```

### Step 16: Upgrade default-pool to 1.30
```bash
# Upgrade default-pool to 1.30
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --node-pool=default-pool \
    --project=$PROJECT_ID

# Monitor progress
watch kubectl get nodes -o wide
```

### Step 17: Upgrade workload-pool to 1.30
```bash
# Upgrade workload-pool to 1.30
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --node-pool=workload-pool \
    --project=$PROJECT_ID

# Monitor progress
watch kubectl get nodes -o wide
```

## Phase 4: Post-Upgrade Verification

### Step 18: Final Verification
```bash
# Verify all components on 1.30
kubectl get nodes -o wide
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(currentMasterVersion,currentNodeVersion)"

# Check all workloads
kubectl get deployments,daemonsets,statefulsets --all-namespaces
kubectl get pods --all-namespaces | grep -v Running

# Compare with pre-upgrade state
diff pre-upgrade-workloads.txt <(kubectl get deployments,daemonsets,statefulsets --all-namespaces -o wide)
```

### Step 19: Functional Testing
```bash
# Test a simple pod deployment
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Cluster is working"

# Check DNS resolution
kubectl run test-dns --image=busybox --rm -it --restart=Never -- nslookup kubernetes.default

# Verify ingress/services (adjust based on your setup)
kubectl get services --all-namespaces
kubectl get ingress --all-namespaces
```

## Phase 5: Cleanup and Documentation

### Step 20: Clean Up
```bash
# Remove backup files (optional, keep for safety)
# rm cluster-backup-*.yaml
# rm all-resources-backup-*.yaml
# rm pre-upgrade-*.txt

# Check for any stuck resources
kubectl get events --all-namespaces --sort-by='.lastTimestamp' | tail -10
```

### Step 21: Update Documentation
```bash
# Document final state
echo "Upgrade completed on $(date)" > upgrade-completion.log
kubectl get nodes -o wide >> upgrade-completion.log
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(currentMasterVersion)" >> upgrade-completion.log
```

## Troubleshooting Commands

If issues arise during upgrade:

```bash
# Check operation status
gcloud container operations list --filter="targetLink~$CLUSTER_NAME"

# Describe specific operation (replace OPERATION_ID)
gcloud container operations describe OPERATION_ID --zone=$ZONE

# Check node pool status
gcloud container node-pools describe POOL_NAME --cluster=$CLUSTER_NAME --zone=$ZONE

# Force refresh credentials if kubectl stops working
gcloud container clusters get-credentials $CLUSTER_NAME --zone=$ZONE

# Check cluster events
kubectl get events --all-namespaces --sort-by='.lastTimestamp'
```

## Expected Timeline
- **Phase 1 (Assessment):** 15-30 minutes
- **Phase 2 (1.28→1.29):** 45-90 minutes
- **Phase 3 (1.29→1.30):** 45-90 minutes  
- **Phase 4-5 (Verification):** 15-30 minutes
- **Total:** 2-4 hours (including wait times)

## Emergency Rollback
GKE doesn't support direct rollbacks. If critical issues occur:
1. Restore from backups created in Step 5
2. Consider creating a new cluster with old version if needed
3. Contact Google Cloud Support for assistance

Remember to test this process in a development environment first if possible!