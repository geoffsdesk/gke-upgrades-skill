# GKE Cluster Upgrade Runbook: 1.32 → 1.33

## Prerequisites & Setup

### 1. Verify Access and Set Variables
```bash
# Set your project and cluster details
export PROJECT_ID="your-project-id"
export CLUSTER_NAME="your-cluster-name"
export ZONE="us-west1-b"

# Authenticate and set project
gcloud auth login
gcloud config set project $PROJECT_ID

# Get cluster credentials
gcloud container clusters get-credentials $CLUSTER_NAME --zone=$ZONE
```

### 2. Pre-Upgrade Health Check
```bash
# Check current cluster status
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(status)"

# Verify current versions
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="table(currentMasterVersion,currentNodeVersion)"

# Check node pool status
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE

# Verify kubectl connectivity
kubectl get nodes
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed
```

### 3. Backup Critical Information
```bash
# Export current workloads (backup)
mkdir -p gke-upgrade-backup
kubectl get all --all-namespaces -o yaml > gke-upgrade-backup/all-resources-backup.yaml
kubectl get pv,pvc --all-namespaces -o yaml > gke-upgrade-backup/storage-backup.yaml
kubectl get configmaps,secrets --all-namespaces -o yaml > gke-upgrade-backup/configs-backup.yaml

# Save current cluster config
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE > gke-upgrade-backup/cluster-config.yaml
```

## Phase 1: Control Plane Upgrade

### 4. Check Available Versions
```bash
# Check what versions are available on Regular channel
gcloud container get-server-config --zone=$ZONE --format="yaml(channels)"

# Verify 1.33 is available
gcloud container get-server-config --zone=$ZONE --format="value(channels.REGULAR.validMasterVersions[])" | grep "1.33"
```

### 5. Upgrade Control Plane
```bash
# Start control plane upgrade (this is automatic on Regular channel, but we can trigger it)
gcloud container clusters upgrade $CLUSTER_NAME --zone=$ZONE --master --cluster-version=1.33.0-gke.XXX

# Note: Replace XXX with the actual patch version from step 4
# The upgrade will take 5-15 minutes
```

### 6. Monitor Control Plane Upgrade
```bash
# Check upgrade status (run this periodically)
watch -n 30 'gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(status,currentMasterVersion)"'

# Alternative: Check in separate terminal
while true; do
  STATUS=$(gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(status)")
  VERSION=$(gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(currentMasterVersion)")
  echo "$(date): Status: $STATUS, Master Version: $VERSION"
  if [ "$STATUS" = "RUNNING" ]; then
    echo "Control plane upgrade complete!"
    break
  fi
  sleep 30
done
```

### 7. Verify Control Plane Upgrade
```bash
# Confirm control plane is on 1.33
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(currentMasterVersion)"

# Test kubectl connectivity
kubectl version --short
kubectl get nodes
```

## Phase 2: Node Pool Upgrades

### 8. Upgrade default-pool
```bash
# Check current node pool version
gcloud container node-pools describe default-pool --cluster=$CLUSTER_NAME --zone=$ZONE --format="value(version,status)"

# Check for running pods on nodes we're about to upgrade
kubectl get pods --all-namespaces -o wide

# Upgrade default-pool
gcloud container clusters upgrade $CLUSTER_NAME --zone=$ZONE --node-pool=default-pool

# This will prompt for confirmation - type 'y' and press Enter
```

### 9. Monitor default-pool Upgrade
```bash
# Monitor node pool upgrade status
watch -n 30 'gcloud container node-pools describe default-pool --cluster=$CLUSTER_NAME --zone=$ZONE --format="table(version,status)" && echo "=== Nodes ===" && kubectl get nodes'

# Monitor pod disruptions
kubectl get pods --all-namespaces | grep -E "(Pending|ContainerCreating|Terminating)"
```

### 10. Verify default-pool Upgrade
```bash
# Wait for upgrade to complete, then verify
gcloud container node-pools describe default-pool --cluster=$CLUSTER_NAME --zone=$ZONE --format="value(version,status)"

# Check all nodes in default-pool are Ready
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool
```

### 11. Upgrade workload-pool
```bash
# Check workload-pool current version
gcloud container node-pools describe workload-pool --cluster=$CLUSTER_NAME --zone=$ZONE --format="value(version,status)"

# Upgrade workload-pool
gcloud container clusters upgrade $CLUSTER_NAME --zone=$ZONE --node-pool=workload-pool

# Confirm when prompted
```

### 12. Monitor workload-pool Upgrade
```bash
# Monitor the upgrade
watch -n 30 'gcloud container node-pools describe workload-pool --cluster=$CLUSTER_NAME --zone=$ZONE --format="table(version,status)" && echo "=== Nodes ===" && kubectl get nodes'

# Check for any pod issues
kubectl get pods --all-namespaces | grep -E "(Pending|ContainerCreating|Terminating|Error|CrashLoopBackOff)"
```

## Phase 3: Post-Upgrade Verification

### 13. Complete Health Check
```bash
# Verify all components are on 1.33
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="table(currentMasterVersion,currentNodeVersion)"

# Check all node pools
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE --format="table(name,version,status)"

# Verify all nodes are Ready and on correct version
kubectl get nodes -o custom-columns="NAME:.metadata.name,STATUS:.status.conditions[-1].type,VERSION:.status.nodeInfo.kubeletVersion,POOL:.metadata.labels.cloud\.google\.com/gke-nodepool"
```

### 14. Application Health Check
```bash
# Check all pods are running
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

# Check for any events indicating issues
kubectl get events --all-namespaces --sort-by='.lastTimestamp' | tail -20

# Test a few key services (adjust namespace/service names as needed)
kubectl get svc --all-namespaces
# kubectl port-forward -n your-namespace svc/your-service 8080:80  # Test specific services
```

### 15. Verify Persistent Volumes
```bash
# Check all PVs and PVCs are bound
kubectl get pv,pvc --all-namespaces | grep -v Bound
```

## Troubleshooting Commands

### If Pods Are Stuck
```bash
# Force drain a problematic node (if needed)
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data --force --grace-period=0

# Check node conditions
kubectl describe node <node-name>

# Check pod events
kubectl describe pod <pod-name> -n <namespace>
```

### If Upgrade Fails
```bash
# Check cluster operations
gcloud container operations list --filter="targetLink:$CLUSTER_NAME"

# Get operation details
gcloud container operations describe <operation-id> --zone=$ZONE

# Check cluster events
kubectl get events --all-namespaces --sort-by='.lastTimestamp'
```

## Expected Timeline

- **Control Plane Upgrade**: 5-15 minutes
- **Each Node Pool Upgrade**: 10-30 minutes (depends on node count)
- **Total Expected Time**: 30-60 minutes

## Success Criteria Checklist

- [ ] Control plane version shows 1.33.x
- [ ] All node pools show version 1.33.x and status "RUNNING"  
- [ ] All nodes show Ready status
- [ ] All pods return to Running state
- [ ] No persistent volume issues
- [ ] Application endpoints respond correctly
- [ ] No critical events in cluster

## Emergency Rollback (if needed)

```bash
# Note: You cannot rollback the control plane, but you can rollback node pools
gcloud container clusters upgrade $CLUSTER_NAME --zone=$ZONE --node-pool=<pool-name> --cluster-version=1.32.x-gke.xxx
```

## Final Notes

1. **Automatic Updates**: Since you're on the Regular channel, Google will automatically upgrade your cluster in the future. Consider switching to Rapid or Stable channel based on your needs.

2. **Maintenance Windows**: Consider setting up maintenance windows for future automatic upgrades:
```bash
gcloud container clusters update $CLUSTER_NAME --zone=$ZONE --maintenance-window-start="2023-01-01T09:00:00Z" --maintenance-window-end="2023-01-01T17:00:00Z" --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SA"
```

3. **Monitoring**: Set up monitoring for future upgrades and cluster health.

Save this runbook and the backup files created during the process for future reference!