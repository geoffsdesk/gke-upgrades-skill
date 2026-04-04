# GKE Cluster Upgrade Runbook: Standard Cluster 1.32 → 1.33

## Prerequisites
- `gcloud` CLI installed and authenticated
- `kubectl` configured to access the cluster
- Cluster admin permissions
- Maintenance window planned (upgrades can take 30-60+ minutes)

## Phase 1: Pre-Upgrade Preparation

### Step 1: Set Environment Variables
```bash
export PROJECT_ID="your-project-id"
export CLUSTER_NAME="your-cluster-name"
export ZONE="us-west1-b"
export TARGET_VERSION="1.33"

# Verify these are correct
echo "Project: $PROJECT_ID"
echo "Cluster: $CLUSTER_NAME"
echo "Zone: $ZONE"
echo "Target Version: $TARGET_VERSION"
```

### Step 2: Authenticate and Set Context
```bash
# Authenticate with GCP
gcloud auth login

# Set project
gcloud config set project $PROJECT_ID

# Get cluster credentials
gcloud container clusters get-credentials $CLUSTER_NAME --zone $ZONE --project $PROJECT_ID
```

### Step 3: Document Current State
```bash
# Check current cluster version
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion,currentNodeVersion)"

# List all node pools and their versions
gcloud container node-pools list --cluster $CLUSTER_NAME --zone $ZONE

# Check cluster status
kubectl get nodes -o wide

# Save current workload state
kubectl get pods --all-namespaces -o wide > pre-upgrade-pods.txt
kubectl get services --all-namespaces > pre-upgrade-services.txt
```

### Step 4: Check Available Versions
```bash
# Check available master versions
gcloud container get-server-config --zone $ZONE --format="value(validMasterVersions[0:5])"

# Verify 1.33 is available
gcloud container get-server-config --zone $ZONE --format="table(validMasterVersions:label=AVAILABLE_VERSIONS)" | grep 1.33
```

### Step 5: Pre-Upgrade Health Checks
```bash
# Check cluster health
kubectl get componentstatuses

# Check node health
kubectl get nodes
kubectl describe nodes | grep -E "Ready|OutOfDisk|MemoryPressure|DiskPressure"

# Check for unhealthy pods
kubectl get pods --all-namespaces --field-selector=status.phase!=Running,status.phase!=Succeeded

# Check PodDisruptionBudgets (important for upgrade planning)
kubectl get pdb --all-namespaces
```

## Phase 2: Control Plane Upgrade

### Step 6: Upgrade the Control Plane (Master)
```bash
# Start control plane upgrade
gcloud container clusters upgrade $CLUSTER_NAME \
    --master \
    --cluster-version $TARGET_VERSION \
    --zone $ZONE \
    --quiet

# Monitor upgrade progress (run in separate terminal)
watch -n 30 "gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format='value(status,currentMasterVersion)'"
```

**⏰ Wait Time:** Control plane upgrade typically takes 10-20 minutes.

### Step 7: Verify Control Plane Upgrade
```bash
# Check master version
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion)"

# Verify kubectl connectivity
kubectl cluster-info

# Check API server health
kubectl get --raw '/healthz'
```

## Phase 3: Node Pool Upgrades

### Step 8: Upgrade default-pool
```bash
# Check current node pool version
gcloud container node-pools describe default-pool --cluster $CLUSTER_NAME --zone $ZONE --format="value(version)"

# Start node pool upgrade
gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool default-pool \
    --zone $ZONE \
    --quiet

# Monitor node pool upgrade
watch -n 30 "kubectl get nodes -o custom-columns='NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,STATUS:.status.conditions[-1].type'"
```

**⏰ Wait Time:** Node pool upgrades take 15-45 minutes depending on pool size.

### Step 9: Verify default-pool Upgrade
```bash
# Check node versions
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool -o custom-columns='NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion'

# Check node pool status
gcloud container node-pools describe default-pool --cluster $CLUSTER_NAME --zone $ZONE --format="value(status,version)"
```

### Step 10: Upgrade workload-pool
```bash
# Check current node pool version
gcloud container node-pools describe workload-pool --cluster $CLUSTER_NAME --zone $ZONE --format="value(version)"

# Start node pool upgrade
gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool workload-pool \
    --zone $ZONE \
    --quiet

# Monitor node pool upgrade
watch -n 30 "kubectl get nodes -o custom-columns='NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,STATUS:.status.conditions[-1].type'"
```

### Step 11: Verify workload-pool Upgrade
```bash
# Check node versions
kubectl get nodes -l cloud.google.com/gke-nodepool=workload-pool -o custom-columns='NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion'

# Check node pool status
gcloud container node-pools describe workload-pool --cluster $CLUSTER_NAME --zone $ZONE --format="value(status,version)"
```

## Phase 4: Post-Upgrade Validation

### Step 12: Comprehensive Health Check
```bash
# Verify all nodes are ready and on correct version
kubectl get nodes -o wide

# Check cluster component health
kubectl get componentstatuses

# Verify all node pools are on target version
gcloud container node-pools list --cluster $CLUSTER_NAME --zone $ZONE

# Check overall cluster status
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(status,currentMasterVersion)"
```

### Step 13: Application Health Verification
```bash
# Check all pods are running
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

# Compare pod state to pre-upgrade
kubectl get pods --all-namespaces -o wide > post-upgrade-pods.txt

# Check services
kubectl get services --all-namespaces

# Test a sample application endpoint (replace with your app)
# kubectl port-forward service/your-service 8080:80 &
# curl http://localhost:8080/health
```

### Step 14: Final Validation Commands
```bash
# Confirm master and all nodes are on 1.33
echo "=== MASTER VERSION ==="
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion)"

echo "=== NODE VERSIONS ==="
kubectl get nodes -o custom-columns='NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,POOL:.metadata.labels.cloud\.google\.com/gke-nodepool'

echo "=== NODE POOL SUMMARY ==="
gcloud container node-pools list --cluster $CLUSTER_NAME --zone $ZONE --format="table(name,version,status)"

echo "=== CLUSTER STATUS ==="
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(status)"
```

## Troubleshooting

### If Control Plane Upgrade Fails:
```bash
# Check cluster events
kubectl get events --all-namespaces --sort-by='.lastTimestamp'

# Check cluster description for error details
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(status,statusMessage)"
```

### If Node Pool Upgrade Fails:
```bash
# Check specific node pool status
gcloud container node-pools describe POOL_NAME --cluster $CLUSTER_NAME --zone $ZONE

# Check node events
kubectl describe nodes | grep -A 10 -B 10 "Warning\|Error"

# If stuck, you may need to recreate problematic nodes
# gcloud container clusters resize $CLUSTER_NAME --node-pool POOL_NAME --num-nodes 0 --zone $ZONE
# gcloud container clusters resize $CLUSTER_NAME --node-pool POOL_NAME --num-nodes ORIGINAL_SIZE --zone $ZONE
```

### Rollback (Emergency Only):
**⚠️ Warning:** GKE doesn't support master version rollback. Node pools can be rolled back only if the operation hasn't completed.

```bash
# Cancel ongoing node pool upgrade (only works if still in progress)
gcloud container operations list --filter="operationType=UPGRADE_NODES AND status=RUNNING"
# Note the operation ID and cancel if needed
```

## Success Criteria Checklist:
- [ ] Control plane reports version 1.33.x
- [ ] All nodes in default-pool report version 1.33.x
- [ ] All nodes in workload-pool report version 1.33.x
- [ ] All nodes show status "Ready"
- [ ] All application pods are running
- [ ] Services are accessible
- [ ] No critical cluster events

**Total Expected Duration:** 45-90 minutes

**Next Steps After Success:**
- Update your infrastructure-as-code definitions
- Schedule regular upgrade windows
- Consider setting up automated upgrade notifications