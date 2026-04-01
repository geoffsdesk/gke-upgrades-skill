# GKE Cluster Upgrade Runbook: 1.32 → 1.33

## Prerequisites Check

Before starting, verify you have the necessary tools and permissions:

```bash
# Check gcloud is installed and authenticated
gcloud auth list

# Check kubectl is installed
kubectl version --client

# Set your project (replace YOUR_PROJECT_ID)
gcloud config set project YOUR_PROJECT_ID

# Get cluster credentials
gcloud container clusters get-credentials CLUSTER_NAME --zone us-west1-b

# Verify cluster access
kubectl get nodes
```

## Step 1: Pre-Upgrade Assessment

### 1.1 Document Current State
```bash
# Get cluster info
gcloud container clusters describe CLUSTER_NAME --zone us-west1-b > cluster-info-before.yaml

# Get current versions
echo "=== CLUSTER VERSION ==="
gcloud container clusters describe CLUSTER_NAME --zone us-west1-b --format="value(currentMasterVersion)"

echo "=== NODE POOL VERSIONS ==="
gcloud container node-pools list --cluster=CLUSTER_NAME --zone=us-west1-b --format="table(name,version,status)"

# Check node status
kubectl get nodes -o wide

# Save current workload state
kubectl get pods --all-namespaces -o wide > pods-before-upgrade.txt
kubectl get deployments --all-namespaces > deployments-before-upgrade.txt
```

### 1.2 Check Available Versions
```bash
# Check available master versions
gcloud container get-server-config --zone=us-west1-b --format="yaml(validMasterVersions)"

# Verify 1.33 is available
gcloud container get-server-config --zone=us-west1-b --format="value(validMasterVersions[*])" | tr ' ' '\n' | grep "1.33"
```

### 1.3 Health Check
```bash
# Check cluster health
kubectl get componentstatuses

# Check for any failing pods
kubectl get pods --all-namespaces --field-selector=status.phase!=Running

# Check node readiness
kubectl get nodes --no-headers | awk '{print $2}' | sort | uniq -c
```

## Step 2: Backup and Safety Measures

### 2.1 Create Backup
```bash
# Create a backup of important resources
mkdir -p cluster-backup-$(date +%Y%m%d)
cd cluster-backup-$(date +%Y%m%d)

# Backup critical resources
kubectl get all --all-namespaces -o yaml > all-resources.yaml
kubectl get configmaps --all-namespaces -o yaml > configmaps.yaml
kubectl get secrets --all-namespaces -o yaml > secrets.yaml
kubectl get pv -o yaml > persistent-volumes.yaml
kubectl get pvc --all-namespaces -o yaml > persistent-volume-claims.yaml

cd ..
```

### 2.2 Set Up Monitoring
```bash
# Open a separate terminal to monitor cluster during upgrade
# Run this in the monitoring terminal:
watch -n 10 'echo "=== NODES ==="; kubectl get nodes; echo "=== PODS ==="; kubectl get pods --all-namespaces | grep -v Running | head -20'
```

## Step 3: Upgrade Control Plane

### 3.1 Upgrade Master to 1.33
```bash
# Start master upgrade
echo "Starting control plane upgrade to 1.33..."
gcloud container clusters upgrade CLUSTER_NAME \
  --master \
  --cluster-version=1.33 \
  --zone=us-west1-b

# This will prompt for confirmation. Type 'Y' and press Enter.
```

### 3.2 Monitor Master Upgrade
```bash
# Check upgrade status (run in a loop until complete)
while true; do
  STATUS=$(gcloud container operations list --filter="name~CLUSTER_NAME AND zone:us-west1-b" --format="value(status)" --limit=1)
  echo "Upgrade status: $STATUS"
  if [ "$STATUS" = "DONE" ]; then
    break
  fi
  sleep 30
done

# Verify master version
gcloud container clusters describe CLUSTER_NAME --zone us-west1-b --format="value(currentMasterVersion)"
```

## Step 4: Upgrade Node Pools

### 4.1 Upgrade default-pool
```bash
echo "Starting upgrade of default-pool..."

# Check current node pool version
gcloud container node-pools describe default-pool --cluster=CLUSTER_NAME --zone=us-west1-b --format="value(version)"

# Upgrade default-pool
gcloud container clusters upgrade CLUSTER_NAME \
  --node-pool=default-pool \
  --zone=us-west1-b

# This will prompt for confirmation. Type 'Y' and press Enter.
```

### 4.2 Monitor default-pool Upgrade
```bash
# Monitor the upgrade progress
while true; do
  STATUS=$(gcloud container operations list --filter="name~default-pool AND zone:us-west1-b" --format="value(status)" --limit=1)
  echo "default-pool upgrade status: $STATUS"
  
  # Also check node status
  echo "Node status:"
  kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool
  
  if [ "$STATUS" = "DONE" ]; then
    break
  fi
  sleep 60
done
```

### 4.3 Upgrade workload-pool
```bash
echo "Starting upgrade of workload-pool..."

# Check current node pool version
gcloud container node-pools describe workload-pool --cluster=CLUSTER_NAME --zone=us-west1-b --format="value(version)"

# Upgrade workload-pool
gcloud container clusters upgrade CLUSTER_NAME \
  --node-pool=workload-pool \
  --zone=us-west1-b

# This will prompt for confirmation. Type 'Y' and press Enter.
```

### 4.4 Monitor workload-pool Upgrade
```bash
# Monitor the upgrade progress
while true; do
  STATUS=$(gcloud container operations list --filter="name~workload-pool AND zone:us-west1-b" --format="value(status)" --limit=1)
  echo "workload-pool upgrade status: $STATUS"
  
  # Also check node status
  echo "Node status:"
  kubectl get nodes -l cloud.google.com/gke-nodepool=workload-pool
  
  if [ "$STATUS" = "DONE" ]; then
    break
  fi
  sleep 60
done
```

## Step 5: Post-Upgrade Validation

### 5.1 Verify Versions
```bash
echo "=== FINAL VERSION CHECK ==="
echo "Master version:"
gcloud container clusters describe CLUSTER_NAME --zone us-west1-b --format="value(currentMasterVersion)"

echo "Node pool versions:"
gcloud container node-pools list --cluster=CLUSTER_NAME --zone=us-west1-b --format="table(name,version,status)"

echo "Node versions:"
kubectl get nodes -o custom-columns="NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,STATUS:.status.conditions[-1].type"
```

### 5.2 Health Validation
```bash
# Check all nodes are ready
echo "=== NODE STATUS ==="
kubectl get nodes

# Check system pods
echo "=== SYSTEM PODS ==="
kubectl get pods -n kube-system

# Check all pods across namespaces
echo "=== ALL PODS STATUS ==="
kubectl get pods --all-namespaces --field-selector=status.phase!=Running

# Check if any deployments have issues
echo "=== DEPLOYMENT STATUS ==="
kubectl get deployments --all-namespaces | grep -E "(0/|AVAILABLE.*0)"
```

### 5.3 Application Validation
```bash
# Test a sample application connectivity (adjust as needed for your apps)
echo "=== APPLICATION CONNECTIVITY TEST ==="

# List all services to identify what to test
kubectl get services --all-namespaces

# Example: Test if you can reach a service (replace with your actual service)
# kubectl run test-pod --image=busybox --rm -it --restart=Never -- wget -qO- http://YOUR_SERVICE_NAME.YOUR_NAMESPACE.svc.cluster.local
```

### 5.4 Save Post-Upgrade State
```bash
# Document final state
gcloud container clusters describe CLUSTER_NAME --zone us-west1-b > cluster-info-after.yaml
kubectl get pods --all-namespaces -o wide > pods-after-upgrade.txt
kubectl get deployments --all-namespaces > deployments-after-upgrade.txt

# Compare before/after
echo "=== UPGRADE SUMMARY ==="
echo "Upgrade completed at: $(date)"
echo "All components should now be running Kubernetes 1.33"
```

## Step 6: Cleanup and Documentation

```bash
# Clean up test resources if any were created
# kubectl delete pod test-pod --ignore-not-found

# Archive backup and logs
tar -czf cluster-upgrade-$(date +%Y%m%d)-backup.tar.gz cluster-backup-* *-upgrade.txt cluster-info-*.yaml

echo "=== UPGRADE COMPLETE ==="
echo "Backup archive: cluster-upgrade-$(date +%Y%m%d)-backup.tar.gz"
echo "Please test your applications thoroughly before considering the upgrade fully validated."
```

## Troubleshooting Commands

If you encounter issues, use these commands:

```bash
# Check recent events
kubectl get events --sort-by='.lastTimestamp' -A

# Check operation details if upgrade fails
gcloud container operations list --zone=us-west1-b --limit=5

# Get detailed operation info (replace OPERATION_ID)
gcloud container operations describe OPERATION_ID --zone=us-west1-b

# Check node pool details
gcloud container node-pools describe POOL_NAME --cluster=CLUSTER_NAME --zone=us-west1-b

# Force refresh credentials if needed
gcloud container clusters get-credentials CLUSTER_NAME --zone us-west1-b
```

## Important Notes

1. **Regular Channel**: Your cluster is on the Regular channel, so 1.33 should be available
2. **Downtime**: Node upgrades will cause pods to be rescheduled, plan for brief downtime
3. **Duration**: Complete upgrade typically takes 30-60 minutes depending on cluster size
4. **Rollback**: If critical issues occur, you may need to restore from backup or recreate the cluster
5. **Replace Variables**: Replace `CLUSTER_NAME` and `YOUR_PROJECT_ID` with your actual values throughout

Remember to test all your applications thoroughly after the upgrade completes!