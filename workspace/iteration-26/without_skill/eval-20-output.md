# GKE Standard Cluster Upgrade Runbook: 1.32 → 1.33

## Prerequisites
- `gcloud` CLI installed and authenticated
- `kubectl` configured to access your cluster
- Cluster admin permissions

## Phase 1: Pre-Upgrade Assessment

### Step 1: Set Environment Variables
```bash
export PROJECT_ID="your-project-id"
export CLUSTER_NAME="your-cluster-name"
export ZONE="us-west1-b"
```

### Step 2: Verify Current Cluster State
```bash
# Get current cluster version
gcloud container clusters describe $CLUSTER_NAME \
  --zone=$ZONE \
  --project=$PROJECT_ID \
  --format="value(currentMasterVersion,currentNodeVersion)"

# List all node pools and their versions
gcloud container node-pools list \
  --cluster=$CLUSTER_NAME \
  --zone=$ZONE \
  --project=$PROJECT_ID
```

### Step 3: Check Available Versions
```bash
# Check available master versions
gcloud container get-server-config \
  --zone=$ZONE \
  --project=$PROJECT_ID \
  --format="value(validMasterVersions[0:5])"
```

### Step 4: Pre-Upgrade Health Check
```bash
# Check cluster health
kubectl get nodes

# Check system pods
kubectl get pods -n kube-system

# Check for any failed pods across all namespaces
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

# Check cluster events for any issues
kubectl get events --sort-by='.lastTimestamp' | tail -20
```

### Step 5: Backup Critical Data
```bash
# Export current resource configurations (recommended)
kubectl get all --all-namespaces -o yaml > cluster-backup-$(date +%Y%m%d).yaml

# List persistent volumes (note any critical data)
kubectl get pv
```

## Phase 2: Control Plane Upgrade

### Step 6: Upgrade Control Plane to 1.33
```bash
# Upgrade the control plane (master)
gcloud container clusters upgrade $CLUSTER_NAME \
  --zone=$ZONE \
  --project=$PROJECT_ID \
  --master \
  --cluster-version=1.33
```

**⚠️ Important Notes:**
- This will take 10-20 minutes
- The API server will be briefly unavailable
- Type 'Y' when prompted to confirm

### Step 7: Verify Control Plane Upgrade
```bash
# Wait for upgrade to complete, then verify
gcloud container clusters describe $CLUSTER_NAME \
  --zone=$ZONE \
  --project=$PROJECT_ID \
  --format="value(currentMasterVersion)"

# Should show 1.33.x-gke.xxxx
```

## Phase 3: Node Pool Upgrades

### Step 8: Upgrade default-pool
```bash
# Start upgrade of default-pool
gcloud container clusters upgrade $CLUSTER_NAME \
  --zone=$ZONE \
  --project=$PROJECT_ID \
  --node-pool=default-pool
```

### Step 9: Monitor default-pool Upgrade
```bash
# Monitor the upgrade progress
watch "kubectl get nodes"

# In another terminal, monitor pods being rescheduled
watch "kubectl get pods --all-namespaces | grep -E '(Pending|Terminating|ContainerCreating)'"
```

**⚠️ During node upgrades:**
- Nodes will be cordoned and drained
- Pods will be rescheduled to other nodes
- Each node upgrade takes 5-10 minutes

### Step 10: Verify default-pool Upgrade
```bash
# Check that all nodes in default-pool are upgraded
gcloud container node-pools describe default-pool \
  --cluster=$CLUSTER_NAME \
  --zone=$ZONE \
  --project=$PROJECT_ID \
  --format="value(version)"

# Verify all nodes are Ready
kubectl get nodes
```

### Step 11: Upgrade workload-pool
```bash
# Start upgrade of workload-pool
gcloud container clusters upgrade $CLUSTER_NAME \
  --zone=$ZONE \
  --project=$PROJECT_ID \
  --node-pool=workload-pool
```

### Step 12: Monitor workload-pool Upgrade
```bash
# Monitor the upgrade progress
watch "kubectl get nodes"

# Monitor application pods
watch "kubectl get pods --all-namespaces"
```

### Step 13: Verify workload-pool Upgrade
```bash
# Check that all nodes in workload-pool are upgraded
gcloud container node-pools describe workload-pool \
  --cluster=$CLUSTER_NAME \
  --zone=$ZONE \
  --project=$PROJECT_ID \
  --format="value(version)"
```

## Phase 4: Post-Upgrade Verification

### Step 14: Complete System Health Check
```bash
# Verify all nodes are on 1.33
kubectl get nodes -o wide

# Check all system pods are healthy
kubectl get pods -n kube-system

# Check for any failed pods
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

# Verify cluster info
kubectl cluster-info
```

### Step 15: Application Health Verification
```bash
# List all namespaces
kubectl get namespaces

# Check pods in each application namespace (replace 'your-app-namespace')
kubectl get pods -n your-app-namespace

# Check services are accessible
kubectl get services --all-namespaces

# Test a sample application endpoint (if applicable)
# kubectl port-forward service/your-service 8080:80 -n your-namespace
```

### Step 16: Final Verification Commands
```bash
# Confirm final versions
echo "=== CLUSTER VERSION ==="
gcloud container clusters describe $CLUSTER_NAME \
  --zone=$ZONE \
  --project=$PROJECT_ID \
  --format="value(currentMasterVersion)"

echo "=== NODE POOL VERSIONS ==="
gcloud container node-pools list \
  --cluster=$CLUSTER_NAME \
  --zone=$ZONE \
  --project=$PROJECT_ID \
  --format="table(name,version,status)"

echo "=== NODE STATUS ==="
kubectl get nodes -o wide

echo "=== CLUSTER HEALTH ==="
kubectl get componentstatuses
```

## Troubleshooting Common Issues

### If Nodes Stick in "NotReady" State:
```bash
# Describe the problematic node
kubectl describe node [NODE-NAME]

# Check node events
kubectl get events --field-selector involvedObject.name=[NODE-NAME]
```

### If Pods Fail to Reschedule:
```bash
# Check pod status and events
kubectl describe pod [POD-NAME] -n [NAMESPACE]

# Check if it's a resource constraint
kubectl top nodes
```

### If Upgrade Gets Stuck:
```bash
# Check operation status
gcloud container operations list \
  --zone=$ZONE \
  --project=$PROJECT_ID
```

## Rollback Procedure (Emergency Only)

⚠️ **Control plane upgrades cannot be rolled back. Node pools can be recreated with the old version if necessary.**

```bash
# If you need to rollback a node pool (this will recreate nodes):
gcloud container node-pools create temp-pool \
  --cluster=$CLUSTER_NAME \
  --zone=$ZONE \
  --project=$PROJECT_ID \
  --node-version=1.32.x-gke.xxxx \
  --num-nodes=3

# Then drain and delete the problematic pool after workloads are moved
```

## Completion Checklist

- [ ] Control plane upgraded to 1.33
- [ ] Both node pools upgraded to 1.33  
- [ ] All nodes show "Ready" status
- [ ] All system pods are running
- [ ] Application pods are healthy
- [ ] Services are accessible
- [ ] No critical events or errors

**Total Expected Duration:** 45-90 minutes depending on cluster size and workload complexity.

**Next Steps:** Monitor the cluster for 24-48 hours to ensure stability before considering the upgrade complete.