# GKE Cluster Upgrade Runbook: 1.32 → 1.33

This runbook will guide you through upgrading your GKE Standard cluster from version 1.32 to 1.33.

## Prerequisites

- `gcloud` CLI installed and authenticated
- `kubectl` installed and configured
- Basic understanding of your workloads
- Maintenance window scheduled (upgrades cause temporary disruption)

## Phase 1: Pre-Upgrade Preparation

### Step 1: Set Environment Variables
```bash
export CLUSTER_NAME="your-cluster-name-here"  # Replace with your actual cluster name
export ZONE="us-west1-b"
export PROJECT_ID=$(gcloud config get-value project)

echo "Cluster: $CLUSTER_NAME"
echo "Zone: $ZONE" 
echo "Project: $PROJECT_ID"
```

### Step 2: Verify Current Cluster State
```bash
# Get cluster info
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE

# Check current versions
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(currentMasterVersion,currentNodeVersion)"

# List node pools
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE
```

### Step 3: Check Available Versions
```bash
# Check available master versions
gcloud container get-server-config --zone=$ZONE --format="yaml(validMasterVersions)"

# Verify 1.33 is available
gcloud container get-server-config --zone=$ZONE --format="value(validMasterVersions)" | grep -E "1\.33"
```

### Step 4: Pre-Upgrade Health Check
```bash
# Check cluster health
kubectl get nodes

# Check system pods
kubectl get pods -n kube-system

# Check your workloads
kubectl get pods --all-namespaces

# Check for any failed pods
kubectl get pods --all-namespaces --field-selector=status.phase=Failed

# Check cluster events for any issues
kubectl get events --sort-by='.lastTimestamp' | tail -20
```

### Step 5: Backup Important Resources (Recommended)
```bash
# Create backup directory
mkdir -p gke-upgrade-backup-$(date +%Y%m%d)
cd gke-upgrade-backup-$(date +%Y%m%d)

# Backup critical resources
kubectl get all --all-namespaces -o yaml > all-resources-backup.yaml
kubectl get configmaps --all-namespaces -o yaml > configmaps-backup.yaml
kubectl get secrets --all-namespaces -o yaml > secrets-backup.yaml
kubectl get pv -o yaml > persistent-volumes-backup.yaml
kubectl get pvc --all-namespaces -o yaml > persistent-volume-claims-backup.yaml

cd ..
```

## Phase 2: Master/Control Plane Upgrade

### Step 6: Upgrade the Master/Control Plane
```bash
# Start master upgrade to 1.33 (replace with specific 1.33 version available)
gcloud container clusters upgrade $CLUSTER_NAME \
    --master \
    --cluster-version=1.33 \
    --zone=$ZONE

# This will prompt for confirmation - type 'Y' and press Enter
```

**⚠️ Important:** The master upgrade typically takes 5-15 minutes. During this time:
- Your workloads continue running
- You cannot make API calls to the cluster
- `kubectl` commands will fail temporarily

### Step 7: Monitor Master Upgrade
```bash
# Check upgrade status (run this in a separate terminal/session)
watch gcloud container operations list --filter="name~$CLUSTER_NAME"

# Or check cluster status
watch gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(status,currentMasterVersion)"
```

Wait until the operation shows `DONE` and status shows `RUNNING`.

### Step 8: Verify Master Upgrade
```bash
# Verify master version
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(currentMasterVersion)"

# Test kubectl connectivity
kubectl get nodes

# Check cluster info
kubectl cluster-info
```

## Phase 3: Node Pool Upgrades

### Step 9: Upgrade default-pool
```bash
# Start default-pool upgrade
gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool=default-pool \
    --zone=$ZONE

# This will prompt for confirmation - type 'Y' and press Enter
```

### Step 10: Monitor default-pool Upgrade
```bash
# Monitor the upgrade progress
watch kubectl get nodes

# Check operations status
watch gcloud container operations list --filter="name~$CLUSTER_NAME"

# Monitor pods during node replacement
watch kubectl get pods --all-namespaces
```

**⚠️ Important:** During node pool upgrade:
- Nodes are replaced one by one (rolling update)
- Pods are drained and rescheduled
- This can take 15-45 minutes depending on cluster size

### Step 11: Verify default-pool Upgrade
```bash
# Check node versions
kubectl get nodes -o wide

# Verify all nodes are Ready
kubectl get nodes

# Check that all system pods are running
kubectl get pods -n kube-system
```

### Step 12: Upgrade workload-pool
```bash
# Start workload-pool upgrade
gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool=workload-pool \
    --zone=$ZONE

# This will prompt for confirmation - type 'Y' and press Enter
```

### Step 13: Monitor workload-pool Upgrade
```bash
# Monitor the upgrade progress
watch kubectl get nodes

# Monitor your application pods
watch kubectl get pods --all-namespaces

# Check for any pod scheduling issues
kubectl get events --sort-by='.lastTimestamp' | tail -20
```

### Step 14: Verify workload-pool Upgrade
```bash
# Check all node versions
kubectl get nodes -o wide

# Verify all nodes are on 1.33
kubectl get nodes --sort-by='.metadata.creationTimestamp'
```

## Phase 4: Post-Upgrade Verification

### Step 15: Comprehensive Health Check
```bash
# Verify cluster version
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(currentMasterVersion)"

# Check all nodes are Ready and on correct version
kubectl get nodes -o wide

# Verify system components
kubectl get pods -n kube-system

# Check your workloads
kubectl get pods --all-namespaces

# Verify services are accessible
kubectl get services --all-namespaces

# Check for any failed or pending pods
kubectl get pods --all-namespaces --field-selector=status.phase!=Running,status.phase!=Succeeded
```

### Step 16: Test Application Connectivity
```bash
# Test a few sample applications (adjust commands based on your workloads)
# Example: If you have a service named 'my-app' in 'default' namespace
kubectl get endpoints

# Port-forward to test an application (example)
# kubectl port-forward service/your-service-name 8080:80

# Check ingress if you have any
kubectl get ingress --all-namespaces
```

### Step 17: Final Verification
```bash
# Get final cluster summary
echo "=== UPGRADE SUMMARY ==="
echo "Cluster: $CLUSTER_NAME"
echo "Zone: $ZONE"
echo "Master Version: $(gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format='value(currentMasterVersion)')"
echo "Node Count: $(kubectl get nodes --no-headers | wc -l)"
echo "Ready Nodes: $(kubectl get nodes --no-headers | grep -c Ready)"

# Check cluster events for any warnings
kubectl get events --sort-by='.lastTimestamp' | tail -10

echo "=== UPGRADE COMPLETE ==="
```

## Troubleshooting Common Issues

### If Master Upgrade Fails:
```bash
# Check operation status and error details
gcloud container operations list --filter="name~$CLUSTER_NAME"
gcloud container operations describe OPERATION_ID --zone=$ZONE
```

### If Node Pool Upgrade Hangs:
```bash
# Check which nodes are being upgraded
kubectl get nodes --sort-by='.metadata.creationTimestamp'

# Check for pods that can't be evicted
kubectl get pods --all-namespaces --field-selector=status.phase=Pending

# Check PodDisruptionBudgets that might block eviction
kubectl get pdb --all-namespaces
```

### If Pods Won't Schedule:
```bash
# Check node resources
kubectl describe nodes

# Check for taints/tolerations issues
kubectl get nodes -o custom-columns=NAME:.metadata.name,TAINTS:.spec.taints

# Check pod events
kubectl describe pod POD_NAME -n NAMESPACE
```

## Rollback Plan (Emergency Only)

**⚠️ Note:** GKE doesn't support downgrading. If critical issues occur, you may need to:

1. **Restore from backup** (if you have cluster-level backups)
2. **Deploy a new cluster** with the old version
3. **Contact Google Cloud Support** for assistance

## Post-Upgrade Cleanup

```bash
# Clean up backup files (optional, keep for a few days)
# rm -rf gke-upgrade-backup-*

# Update any CI/CD pipelines that reference the old version
# Update documentation with new version
```

## Important Notes

- **Maintenance Windows**: Plan upgrades during low-traffic periods
- **PodDisruptionBudgets**: Ensure your critical workloads have appropriate PDBs
- **Monitoring**: Keep monitoring dashboards open during upgrade
- **Communication**: Notify your team before starting the upgrade
- **Testing**: Test your applications thoroughly after upgrade

Your upgrade is now complete! The cluster should be running Kubernetes 1.33 on both the control plane and all nodes.