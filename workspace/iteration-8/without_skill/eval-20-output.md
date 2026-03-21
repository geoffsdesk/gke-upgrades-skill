# GKE Cluster Upgrade Runbook: 1.32 to 1.32

## Prerequisites Check

First, let's verify your current cluster status and prepare for the upgrade.

### 1. Set Environment Variables
```bash
export CLUSTER_NAME="your-cluster-name"  # Replace with actual cluster name
export ZONE="us-west1-b"
export PROJECT_ID="your-project-id"      # Replace with actual project ID
```

### 2. Authenticate and Set Context
```bash
# Authenticate with Google Cloud
gcloud auth login

# Set your project
gcloud config set project $PROJECT_ID

# Get cluster credentials
gcloud container clusters get-credentials $CLUSTER_NAME --zone $ZONE

# Verify connection
kubectl cluster-info
```

### 3. Check Current Cluster Status
```bash
# Check cluster version
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion,currentNodeVersion)"

# Check node pool versions
gcloud container node-pools list --cluster $CLUSTER_NAME --zone $ZONE

# Check node status
kubectl get nodes -o wide
```

## Pre-Upgrade Safety Checks

### 4. Backup Critical Resources
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
```

### 5. Check Application Health
```bash
# Check pod status
kubectl get pods --all-namespaces | grep -v Running

# Check services
kubectl get services --all-namespaces

# Check ingress
kubectl get ingress --all-namespaces
```

### 6. Check for PodDisruptionBudgets
```bash
# List PodDisruptionBudgets
kubectl get pdb --all-namespaces

# If you have critical applications without PDBs, consider creating them
# Example PDB (adjust as needed):
# kubectl create pdb my-app-pdb --selector=app=my-app --min-available=1
```

## Control Plane Upgrade

### 7. Check Available Versions
```bash
# Check available versions for your cluster
gcloud container get-server-config --zone $ZONE --format="yaml(channels,validMasterVersions)"
```

### 8. Upgrade Control Plane
```bash
# Since you're already on 1.32 and want to stay on 1.32, check if there's a patch version available
# Get the specific target version (e.g., 1.32.0-gke.1234)
TARGET_VERSION=$(gcloud container get-server-config --zone $ZONE --format="value(channels.REGULAR.validVersions[0])" | grep "^1\.32\.")

echo "Target version: $TARGET_VERSION"

# Upgrade control plane (if a newer patch version is available)
if [ ! -z "$TARGET_VERSION" ]; then
  gcloud container clusters upgrade $CLUSTER_NAME \
    --master \
    --cluster-version $TARGET_VERSION \
    --zone $ZONE
else
  echo "No newer 1.32 version available, control plane is current"
fi
```

### 9. Verify Control Plane Upgrade
```bash
# Wait for upgrade to complete, then verify
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion)"

# Check cluster health
kubectl get nodes
kubectl get pods --all-namespaces | grep -v Running
```

## Node Pool Upgrades

### 10. Upgrade default-pool
```bash
# Check current node pool version
gcloud container node-pools describe default-pool --cluster $CLUSTER_NAME --zone $ZONE --format="value(version)"

# Upgrade default-pool
gcloud container clusters upgrade $CLUSTER_NAME \
  --node-pool default-pool \
  --zone $ZONE

# Monitor the upgrade progress
watch "kubectl get nodes -o wide"
```

### 11. Verify default-pool Upgrade
```bash
# Check node versions
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool

# Check pod redistribution
kubectl get pods --all-namespaces -o wide | grep default-pool
```

### 12. Upgrade workload-pool
```bash
# Check current node pool version
gcloud container node-pools describe workload-pool --cluster $CLUSTER_NAME --zone $ZONE --format="value(version)"

# Upgrade workload-pool
gcloud container clusters upgrade $CLUSTER_NAME \
  --node-pool workload-pool \
  --zone $ZONE

# Monitor the upgrade progress
watch "kubectl get nodes -o wide"
```

### 13. Verify workload-pool Upgrade
```bash
# Check node versions
kubectl get nodes -l cloud.google.com/gke-nodepool=workload-pool

# Check pod redistribution
kubectl get pods --all-namespaces -o wide | grep workload-pool
```

## Post-Upgrade Verification

### 14. Final Health Checks
```bash
# Verify all nodes are ready
kubectl get nodes

# Check all pods are running
kubectl get pods --all-namespaces | grep -v Running

# Verify services are accessible
kubectl get services --all-namespaces

# Check cluster info
kubectl cluster-info

# Verify cluster version
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion)"

# Verify all node pools
gcloud container node-pools list --cluster $CLUSTER_NAME --zone $ZONE
```

### 15. Application Testing
```bash
# Test critical applications
# Replace with your actual application endpoints/services
kubectl get ingress --all-namespaces  # Test external endpoints
kubectl get services --all-namespaces # Test internal services

# Run application-specific health checks here
# Examples:
# curl http://your-app-endpoint/health
# kubectl exec -it <pod-name> -- your-health-check-command
```

## Troubleshooting Commands

### If Issues Arise:

```bash
# Check cluster events
kubectl get events --sort-by=.metadata.creationTimestamp

# Check node conditions
kubectl describe nodes

# Check pod logs for failing pods
kubectl logs <pod-name> -n <namespace>

# Check cluster operation status
gcloud container operations list --filter="targetLink~$CLUSTER_NAME"

# Roll back if necessary (contact your team lead first)
# gcloud container clusters upgrade $CLUSTER_NAME --node-pool <pool-name> --cluster-version <previous-version> --zone $ZONE
```

## Clean Up
```bash
# After successful upgrade, clean up old backup files (optional)
# cd .. && rm -rf gke-upgrade-backup-$(date +%Y%m%d)
```

## Important Notes:

1. **Timing**: Schedule this during a maintenance window as pods will be rescheduled
2. **Duration**: Expect 15-30 minutes per node pool depending on size
3. **Monitoring**: Keep monitoring dashboards open during the upgrade
4. **Rollback**: Have a rollback plan ready (contact senior team members)
5. **Documentation**: Document any issues encountered for future reference

## Emergency Contacts:
- Your team lead: [contact info]
- On-call engineer: [contact info]
- Google Cloud Support: [support case number if available]

**Before starting**: Ensure you have approval from your team lead and have scheduled this during an approved maintenance window.