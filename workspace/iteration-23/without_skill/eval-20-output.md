# GKE Cluster Upgrade Runbook: 1.32 → 1.33

## Prerequisites
- `gcloud` CLI installed and authenticated
- `kubectl` configured for your cluster
- Cluster admin permissions

## Step 1: Set Environment Variables
```bash
export PROJECT_ID="your-project-id"
export CLUSTER_NAME="your-cluster-name"
export ZONE="us-west1-b"
```

## Step 2: Configure gcloud and kubectl
```bash
# Set the project
gcloud config set project $PROJECT_ID

# Get cluster credentials
gcloud container clusters get-credentials $CLUSTER_NAME --zone $ZONE

# Verify connection
kubectl get nodes
```

## Step 3: Pre-Upgrade Health Check
```bash
# Check cluster status
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(status)"

# Check node status
kubectl get nodes -o wide

# Check system pods
kubectl get pods -n kube-system

# Check your workloads
kubectl get pods --all-namespaces | grep -v Running

# Check cluster events for any issues
kubectl get events --sort-by='.lastTimestamp' --all-namespaces | tail -20
```

## Step 4: Backup Critical Information
```bash
# Export current cluster configuration
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE > cluster-backup-$(date +%Y%m%d).yaml

# Export node pool configurations
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE > nodepools-backup-$(date +%Y%m%d).yaml

# Backup important workload configurations
kubectl get deployments --all-namespaces -o yaml > deployments-backup-$(date +%Y%m%d).yaml
kubectl get services --all-namespaces -o yaml > services-backup-$(date +%Y%m%d).yaml
kubectl get configmaps --all-namespaces -o yaml > configmaps-backup-$(date +%Y%m%d).yaml
kubectl get secrets --all-namespaces -o yaml > secrets-backup-$(date +%Y%m%d).yaml
```

## Step 5: Check Available Versions
```bash
# Check available versions for Regular channel
gcloud container get-server-config --zone $ZONE --format="yaml(channels)"

# Verify 1.33 is available
gcloud container get-server-config --zone $ZONE --format="value(channels.REGULAR.validVersions)" | grep "1.33"
```

## Step 6: Scale Down Non-Critical Workloads (Optional but Recommended)
```bash
# List all deployments to identify non-critical ones
kubectl get deployments --all-namespaces

# Scale down non-critical deployments (example)
# kubectl scale deployment <deployment-name> --replicas=0 -n <namespace>
```

## Step 7: Upgrade Control Plane
```bash
# Start the control plane upgrade
gcloud container clusters upgrade $CLUSTER_NAME --zone $ZONE --master --cluster-version=1.33

# This will prompt for confirmation. Type 'Y' to proceed.
```

**⚠️ WAIT**: This typically takes 5-15 minutes. Monitor progress:
```bash
# Check upgrade status
watch -n 30 "gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format='value(status)'"
```

Wait until status shows "RUNNING" before proceeding.

## Step 8: Verify Control Plane Upgrade
```bash
# Check control plane version
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion)"

# Verify cluster connectivity
kubectl get nodes
kubectl get pods -n kube-system
```

## Step 9: Upgrade Node Pool 1 (default-pool)
```bash
# Check current node pool version
gcloud container node-pools describe default-pool --cluster=$CLUSTER_NAME --zone=$ZONE --format="value(version)"

# Start node pool upgrade
gcloud container clusters upgrade $CLUSTER_NAME --zone $ZONE --node-pool=default-pool

# This will prompt for confirmation. Type 'Y' to proceed.
```

**⚠️ WAIT**: Monitor the upgrade progress:
```bash
# Watch nodes being replaced
watch -n 30 "kubectl get nodes -o wide"

# Check node pool status
watch -n 30 "gcloud container node-pools describe default-pool --cluster=$CLUSTER_NAME --zone=$ZONE --format='value(status)'"
```

Wait until all nodes in default-pool show version 1.33 and status is RUNNING.

## Step 10: Verify default-pool Upgrade
```bash
# Check node versions
kubectl get nodes -o wide

# Check that pods are running properly
kubectl get pods --all-namespaces | grep -v Running

# Test cluster functionality
kubectl run test-pod --image=nginx --rm -i --tty -- /bin/bash
# If the pod starts successfully, type 'exit' to remove it
```

## Step 11: Upgrade Node Pool 2 (workload-pool)
```bash
# Check current node pool version
gcloud container node-pools describe workload-pool --cluster=$CLUSTER_NAME --zone=$ZONE --format="value(version)"

# Start node pool upgrade
gcloud container clusters upgrade $CLUSTER_NAME --zone $ZONE --node-pool=workload-pool

# This will prompt for confirmation. Type 'Y' to proceed.
```

**⚠️ WAIT**: Monitor the upgrade progress:
```bash
# Watch nodes being replaced
watch -n 30 "kubectl get nodes -o wide"

# Check node pool status
watch -n 30 "gcloud container node-pools describe workload-pool --cluster=$CLUSTER_NAME --zone=$ZONE --format='value(status)'"
```

## Step 12: Final Verification
```bash
# Verify all components are on 1.33
echo "=== Cluster Version ==="
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE --format="value(currentMasterVersion)"

echo "=== Node Versions ==="
kubectl get nodes -o wide

echo "=== Node Pool Versions ==="
gcloud container node-pools list --cluster=$CLUSTER_NAME --zone=$ZONE --format="table(name,version,status)"

# Check cluster health
echo "=== Cluster Health ==="
kubectl get componentstatuses
kubectl get nodes
kubectl get pods -n kube-system

# Check your workloads
echo "=== Application Status ==="
kubectl get pods --all-namespaces | grep -v Running
```

## Step 13: Scale Up Previously Scaled Down Workloads
```bash
# If you scaled down any deployments in Step 6, scale them back up
# kubectl scale deployment <deployment-name> --replicas=<original-count> -n <namespace>
```

## Step 14: Post-Upgrade Testing
```bash
# Test basic cluster functionality
kubectl create deployment test-upgrade --image=nginx
kubectl expose deployment test-upgrade --port=80 --type=ClusterIP
kubectl get service test-upgrade

# Test pod scheduling on both node pools
kubectl get pods -o wide

# Cleanup test resources
kubectl delete deployment test-upgrade
kubectl delete service test-upgrade
```

## Troubleshooting Commands

If something goes wrong:

```bash
# Check cluster events
kubectl get events --sort-by='.lastTimestamp' --all-namespaces

# Check node conditions
kubectl describe nodes

# Check for stuck upgrades
gcloud container operations list --zone=$ZONE

# Check system pod logs
kubectl logs -n kube-system <pod-name>

# Force refresh credentials if kubectl stops working
gcloud container clusters get-credentials $CLUSTER_NAME --zone $ZONE
```

## Emergency Rollback (if needed)
**Note**: Control plane cannot be rolled back, but you can troubleshoot node issues:

```bash
# If nodes are having issues, you can recreate a node pool
# (This is a last resort - contact your team lead first)

# Check if any nodes are in NotReady state
kubectl get nodes | grep NotReady
```

## Success Criteria Checklist
- [ ] Control plane shows version 1.33
- [ ] All nodes show version 1.33
- [ ] All nodes are in Ready state
- [ ] All system pods in kube-system namespace are Running
- [ ] All application pods are Running
- [ ] No critical events in cluster event log
- [ ] Basic pod creation and deletion works

## Expected Timeline
- **Pre-checks and backup**: 10-15 minutes
- **Control plane upgrade**: 5-15 minutes
- **Node pool 1 upgrade**: 10-20 minutes
- **Node pool 2 upgrade**: 10-20 minutes
- **Verification**: 5-10 minutes
- **Total**: 40-80 minutes

## Important Notes
1. **Regular channel**: Upgrades are automatic eventually, but manual upgrade gives you control over timing
2. **Single zone cluster**: All nodes are in one zone, so plan for potential service interruption
3. **Rolling upgrade**: Nodes are replaced one at a time to minimize disruption
4. **Pod Disruption**: Pods will be rescheduled during node upgrades

Contact your team lead if any step fails or if you see unexpected errors.