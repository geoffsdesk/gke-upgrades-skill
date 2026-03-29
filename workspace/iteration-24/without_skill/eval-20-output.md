# GKE Cluster Upgrade Runbook: 1.32 → 1.33

## Prerequisites
- `kubectl` configured to access your cluster
- `gcloud` CLI installed and authenticated
- Basic kubectl knowledge
- Backup access/documentation ready

## Phase 1: Pre-Upgrade Assessment and Backup

### Step 1: Set Environment Variables
```bash
export PROJECT_ID="your-project-id"
export CLUSTER_NAME="your-cluster-name"
export ZONE="us-west1-b"
```

### Step 2: Verify Current Cluster Status
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

### Step 3: Health Check
```bash
# Check cluster health
kubectl get nodes
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

# Check for any failing pods
kubectl get pods --all-namespaces --field-selector=status.phase!=Running,status.phase!=Succeeded

# Check system components
kubectl get pods -n kube-system
```

### Step 4: Backup Critical Resources
```bash
# Create backup directory
mkdir -p gke-upgrade-backup-$(date +%Y%m%d)
cd gke-upgrade-backup-$(date +%Y%m%d)

# Backup all resources
kubectl get all --all-namespaces -o yaml > all-resources-backup.yaml

# Backup specific critical resources
kubectl get configmaps --all-namespaces -o yaml > configmaps-backup.yaml
kubectl get secrets --all-namespaces -o yaml > secrets-backup.yaml
kubectl get persistentvolumes -o yaml > pv-backup.yaml
kubectl get persistentvolumeclaims --all-namespaces -o yaml > pvc-backup.yaml

# List installed applications/helm releases (if using Helm)
helm list --all-namespaces > helm-releases.txt 2>/dev/null || echo "No Helm found"
```

### Step 5: Document Current State
```bash
# Save current cluster configuration
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="export" > cluster-config-backup.yaml

# Save node pool configurations
gcloud container node-pools describe default-pool --cluster=$CLUSTER_NAME --zone=$ZONE --format="export" > default-pool-backup.yaml
gcloud container node-pools describe workload-pool --cluster=$CLUSTER_NAME --zone=$ZONE --format="export" > workload-pool-backup.yaml
```

## Phase 2: Control Plane Upgrade

### Step 6: Check Available Versions
```bash
# List available versions for upgrade
gcloud container get-server-config --zone=$ZONE --project=$PROJECT_ID

# Specifically check if 1.33 is available
gcloud container get-server-config --zone=$ZONE --format="value(validMasterVersions[])" | grep "1.33"
```

### Step 7: Upgrade Control Plane
```bash
# Start control plane upgrade (this will take 10-20 minutes)
gcloud container clusters upgrade $CLUSTER_NAME \
    --master \
    --cluster-version=1.33 \
    --zone=$ZONE \
    --project=$PROJECT_ID

# Monitor the upgrade progress
watch -n 30 "gcloud container operations list --filter='name~$CLUSTER_NAME AND zone~$ZONE' --limit=5"
```

### Step 8: Verify Control Plane Upgrade
```bash
# Wait for upgrade to complete, then verify
kubectl version --short

# Check cluster status
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(status, currentMasterVersion)"

# Verify API server is responding
kubectl get nodes
kubectl get pods -n kube-system
```

## Phase 3: Node Pool Upgrades

### Step 9: Upgrade default-pool
```bash
# Check current node versions
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool

# Upgrade default-pool nodes
gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool=default-pool \
    --zone=$ZONE \
    --project=$PROJECT_ID

# Monitor node upgrade progress
watch -n 30 "kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool"
```

### Step 10: Verify default-pool Upgrade
```bash
# Wait for all nodes to be Ready
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool

# Check pods are running properly
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed
```

### Step 11: Upgrade workload-pool
```bash
# Check current node versions
kubectl get nodes -l cloud.google.com/gke-nodepool=workload-pool

# Upgrade workload-pool nodes
gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool=workload-pool \
    --zone=$ZONE \
    --project=$PROJECT_ID

# Monitor node upgrade progress
watch -n 30 "kubectl get nodes -l cloud.google.com/gke-nodepool=workload-pool"
```

### Step 12: Verify workload-pool Upgrade
```bash
# Wait for all nodes to be Ready
kubectl get nodes -l cloud.google.com/gke-nodepool=workload-pool

# Check pods are running properly
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed
```

## Phase 4: Post-Upgrade Verification

### Step 13: Full Cluster Verification
```bash
# Verify all nodes are on 1.33
kubectl get nodes -o wide

# Check all system pods
kubectl get pods -n kube-system

# Verify cluster info
kubectl cluster-info

# Check for any issues
kubectl get events --sort-by=.metadata.creationTimestamp | tail -20
```

### Step 14: Application Health Check
```bash
# Check all pods across namespaces
kubectl get pods --all-namespaces

# Check services
kubectl get svc --all-namespaces

# Check ingresses (if any)
kubectl get ingress --all-namespaces

# Test a sample application (adjust namespace/pod as needed)
# kubectl exec -it <pod-name> -n <namespace> -- curl localhost:<port>/health
```

### Step 15: Verify Regular Channel Status
```bash
# Confirm cluster is still on Regular channel
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(releaseChannel.channel)"

# Check for any pending updates
gcloud container get-server-config --zone=$ZONE
```

## Phase 5: Final Documentation

### Step 16: Document Upgrade Results
```bash
# Save final cluster state
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE > post-upgrade-cluster-state.yaml

# Save final node state
kubectl get nodes -o yaml > post-upgrade-nodes.yaml

# Create upgrade summary
echo "=== GKE Upgrade Summary ===" > upgrade-summary.txt
echo "Date: $(date)" >> upgrade-summary.txt
echo "Cluster: $CLUSTER_NAME" >> upgrade-summary.txt
echo "Zone: $ZONE" >> upgrade-summary.txt
echo "Upgraded from: 1.32 to 1.33" >> upgrade-summary.txt
echo "Status: $(gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format='value(status)')" >> upgrade-summary.txt
echo "Master Version: $(gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format='value(currentMasterVersion)')" >> upgrade-summary.txt
echo "Node Version: $(kubectl get nodes -o jsonpath='{.items[0].status.nodeInfo.kubeletVersion}')" >> upgrade-summary.txt
```

## Troubleshooting Commands

If issues arise during upgrade:

```bash
# Check cluster operations
gcloud container operations list --filter="zone:$ZONE"

# Get detailed operation status
gcloud container operations describe <OPERATION_ID> --zone=$ZONE

# Check node pool status
gcloud container node-pools describe default-pool --cluster=$CLUSTER_NAME --zone=$ZONE
gcloud container node-pools describe workload-pool --cluster=$CLUSTER_NAME --zone=$ZONE

# Check for stuck nodes
kubectl get nodes --sort-by=.metadata.creationTimestamp

# Describe problem nodes
kubectl describe node <NODE_NAME>

# Check pod disruption budgets
kubectl get pdb --all-namespaces
```

## Rollback (Emergency Only)
**Note**: Control plane cannot be rolled back. Only document for reference.

```bash
# If nodes need to be recreated on older version (extreme case)
# This would require recreating node pools - contact your team lead before executing

# Check what versions are available for rollback
gcloud container get-server-config --zone=$ZONE --format="value(validNodeVersions[])"
```

## Expected Timeline
- **Phase 1** (Pre-upgrade): 15-30 minutes
- **Phase 2** (Control plane): 10-20 minutes
- **Phase 3** (Node pools): 30-60 minutes (depending on node count)
- **Phase 4** (Verification): 10-15 minutes
- **Total**: 1.5-2.5 hours

## Notes
- Each node pool upgrade replaces nodes one at a time (surge upgrade)
- Your applications should experience minimal downtime if properly configured with replicas
- Monitor your applications throughout the process
- The cluster will remain on the Regular channel and auto-upgrade in the future
- Keep all backup files until you've verified everything works correctly

This runbook assumes you're following GKE best practices. If you encounter any errors, stop and consult with your team lead before proceeding.