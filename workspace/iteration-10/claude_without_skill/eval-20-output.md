# GKE Cluster Upgrade Runbook: 1.31 to 1.32

## Prerequisites Checklist
- [ ] kubectl installed and configured
- [ ] gcloud CLI installed and authenticated
- [ ] Access to the GKE cluster
- [ ] Backup/rollback plan prepared
- [ ] Maintenance window scheduled

## Step 1: Initial Setup and Verification

### 1.1 Set Environment Variables
```bash
export PROJECT_ID="your-project-id"
export CLUSTER_NAME="your-cluster-name"
export ZONE="us-west1-b"
```

### 1.2 Authenticate and Set Context
```bash
# Authenticate with Google Cloud
gcloud auth login

# Set the project
gcloud config set project $PROJECT_ID

# Get cluster credentials
gcloud container clusters get-credentials $CLUSTER_NAME --zone $ZONE

# Verify connection
kubectl cluster-info
```

### 1.3 Document Current State
```bash
# Check current cluster version
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion,currentNodeVersion)"

# Check node pool versions
gcloud container node-pools list --cluster $CLUSTER_NAME --zone $ZONE

# Check available versions
gcloud container get-server-config --zone $ZONE --format="yaml(validMasterVersions,validNodeVersions)"

# Save current workloads info
kubectl get nodes -o wide > pre-upgrade-nodes.txt
kubectl get pods --all-namespaces > pre-upgrade-pods.txt
```

## Step 2: Pre-Upgrade Health Check

### 2.1 Check Cluster Health
```bash
# Check node status
kubectl get nodes

# Check system pods
kubectl get pods -n kube-system

# Check for unhealthy pods
kubectl get pods --all-namespaces --field-selector=status.phase!=Running

# Check cluster events for any issues
kubectl get events --all-namespaces --sort-by='.lastTimestamp' | tail -20
```

### 2.2 Check Application Health
```bash
# Check all deployments
kubectl get deployments --all-namespaces

# Check services
kubectl get services --all-namespaces

# Check ingress (if any)
kubectl get ingress --all-namespaces
```

## Step 3: Backup Critical Data

### 3.1 Backup Kubernetes Resources
```bash
# Create backup directory
mkdir -p gke-upgrade-backup-$(date +%Y%m%d)
cd gke-upgrade-backup-$(date +%Y%m%d)

# Backup all namespaces and resources
kubectl get all --all-namespaces -o yaml > all-resources-backup.yaml

# Backup ConfigMaps and Secrets
kubectl get configmaps --all-namespaces -o yaml > configmaps-backup.yaml
kubectl get secrets --all-namespaces -o yaml > secrets-backup.yaml

# Backup RBAC
kubectl get clusterroles,clusterrolebindings,roles,rolebindings --all-namespaces -o yaml > rbac-backup.yaml
```

## Step 4: Upgrade Control Plane (Master)

### 4.1 Upgrade Master to 1.32
```bash
# List available versions to confirm 1.32 is available
gcloud container get-server-config --zone $ZONE --format="value(validMasterVersions)" | grep "1\.32"

# Upgrade the master
gcloud container clusters upgrade $CLUSTER_NAME --zone $ZONE --master --cluster-version=1.32 --quiet

# Monitor the upgrade progress
while true; do
  VERSION=$(gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion)")
  echo "Current master version: $VERSION"
  if [[ $VERSION == 1.32* ]]; then
    echo "Master upgrade completed!"
    break
  fi
  sleep 30
done
```

### 4.2 Verify Master Upgrade
```bash
# Check master version
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion)"

# Test kubectl connectivity
kubectl version --short

# Check system pods are running
kubectl get pods -n kube-system
```

## Step 5: Upgrade Node Pools

### 5.1 Upgrade default-pool
```bash
# Check current node pool version
gcloud container node-pools describe default-pool --cluster $CLUSTER_NAME --zone $ZONE --format="value(version)"

# Upgrade default-pool
gcloud container clusters upgrade $CLUSTER_NAME --zone $ZONE --node-pool=default-pool --cluster-version=1.32 --quiet

# Monitor node pool upgrade
while true; do
  VERSION=$(gcloud container node-pools describe default-pool --cluster $CLUSTER_NAME --zone $ZONE --format="value(version)")
  STATUS=$(gcloud container node-pools describe default-pool --cluster $CLUSTER_NAME --zone $ZONE --format="value(status)")
  echo "default-pool version: $VERSION, status: $STATUS"
  
  if [[ $VERSION == 1.32* ]] && [[ $STATUS == "RUNNING" ]]; then
    echo "default-pool upgrade completed!"
    break
  fi
  sleep 60
done
```

### 5.2 Verify default-pool Upgrade
```bash
# Check nodes are ready
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool

# Check pods are rescheduled properly
kubectl get pods --all-namespaces -o wide | grep default-pool
```

### 5.3 Upgrade workload-pool
```bash
# Check current node pool version
gcloud container node-pools describe workload-pool --cluster $CLUSTER_NAME --zone $ZONE --format="value(version)"

# Upgrade workload-pool
gcloud container clusters upgrade $CLUSTER_NAME --zone $ZONE --node-pool=workload-pool --cluster-version=1.32 --quiet

# Monitor node pool upgrade
while true; do
  VERSION=$(gcloud container node-pools describe workload-pool --cluster $CLUSTER_NAME --zone $ZONE --format="value(version)")
  STATUS=$(gcloud container node-pools describe workload-pool --cluster $CLUSTER_NAME --zone $ZONE --format="value(status)")
  echo "workload-pool version: $VERSION, status: $STATUS"
  
  if [[ $VERSION == 1.32* ]] && [[ $STATUS == "RUNNING" ]]; then
    echo "workload-pool upgrade completed!"
    break
  fi
  sleep 60
done
```

### 5.4 Verify workload-pool Upgrade
```bash
# Check nodes are ready
kubectl get nodes -l cloud.google.com/gke-nodepool=workload-pool

# Check pods are rescheduled properly
kubectl get pods --all-namespaces -o wide | grep workload-pool
```

## Step 6: Post-Upgrade Verification

### 6.1 Verify Complete Upgrade
```bash
# Check all versions are 1.32
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="table(currentMasterVersion,currentNodeVersion)"

# Check all node pool versions
gcloud container node-pools list --cluster $CLUSTER_NAME --zone $ZONE --format="table(name,version,status)"

# Verify all nodes are running 1.32
kubectl get nodes -o custom-columns="NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,STATUS:.status.conditions[?(@.type=='Ready')].status"
```

### 6.2 Health Check Applications
```bash
# Check all pods are running
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

# Check deployments
kubectl get deployments --all-namespaces

# Check services
kubectl get services --all-namespaces

# Run a test pod to verify cluster functionality
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Cluster is working"
```

### 6.3 Compare with Pre-upgrade State
```bash
# Check if all previous pods are back
kubectl get nodes -o wide > post-upgrade-nodes.txt
kubectl get pods --all-namespaces > post-upgrade-pods.txt

# Compare (manual review)
echo "=== NODES COMPARISON ==="
diff pre-upgrade-nodes.txt post-upgrade-nodes.txt

echo "=== PODS COUNT COMPARISON ==="
echo "Before: $(wc -l < pre-upgrade-pods.txt) pods"
echo "After: $(wc -l < post-upgrade-pods.txt) pods"
```

## Step 7: Cleanup and Documentation

### 7.1 Clean up test resources
```bash
# Remove any test pods if they exist
kubectl get pods | grep test-pod | awk '{print $1}' | xargs -r kubectl delete pod
```

### 7.2 Document the upgrade
```bash
# Save final state
echo "=== UPGRADE COMPLETED ===" > upgrade-summary.txt
echo "Date: $(date)" >> upgrade-summary.txt
echo "Cluster: $CLUSTER_NAME" >> upgrade-summary.txt
echo "Zone: $ZONE" >> upgrade-summary.txt
echo "" >> upgrade-summary.txt
echo "Final versions:" >> upgrade-summary.txt
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion,currentNodeVersion)" >> upgrade-summary.txt
```

## Troubleshooting Commands

If issues arise during upgrade:

```bash
# Check upgrade operations
gcloud container operations list --filter="zone:$ZONE"

# Get detailed operation info
gcloud container operations describe [OPERATION-ID] --zone $ZONE

# Check cluster events
kubectl get events --all-namespaces --sort-by='.lastTimestamp'

# Check pod logs if pods are failing
kubectl logs [POD-NAME] -n [NAMESPACE]

# Describe problematic pods
kubectl describe pod [POD-NAME] -n [NAMESPACE]

# Check node conditions
kubectl describe nodes
```

## Rollback Plan (Emergency)

If critical issues occur:

```bash
# Note: You cannot downgrade a GKE cluster version
# You would need to restore from backup or recreate cluster

# To restore resources from backup:
kubectl apply -f gke-upgrade-backup-[DATE]/all-resources-backup.yaml
```

## Success Criteria

✅ All components upgraded to 1.32:
- Control plane: 1.32.x
- default-pool: 1.32.x  
- workload-pool: 1.32.x

✅ All nodes in Ready state
✅ All application pods running
✅ Services responding normally
✅ No critical errors in cluster events

---

**Important Notes:**
- The upgrade process can take 15-45 minutes depending on cluster size
- Node pool upgrades replace nodes one by one (rolling update)
- Applications with proper health checks and multiple replicas should have no downtime
- Always test this process in a staging environment first