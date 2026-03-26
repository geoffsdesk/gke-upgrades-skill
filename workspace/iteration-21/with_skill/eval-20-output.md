# GKE Upgrade Runbook: 1.32 → 1.33

**Cluster Details:**
- Name: [YOUR_CLUSTER_NAME]
- Zone: us-west1-b
- Channel: Regular
- Current: 1.32 → Target: 1.33
- Node pools: default-pool, workload-pool

This runbook assumes you have `gcloud` CLI configured and cluster access via `kubectl`.

## Phase 1: Pre-Flight Checks (15-20 minutes)

### 1.1 Verify cluster access and current state
```bash
# Connect to your cluster
gcloud container clusters get-credentials [YOUR_CLUSTER_NAME] --zone us-west1-b

# Check current versions
gcloud container clusters describe [YOUR_CLUSTER_NAME] \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Expected: Control plane and nodes at 1.32.x
```

### 1.2 Check if 1.33 is available in Regular channel
```bash
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels.REGULAR)"

# Look for 1.33.x versions in the output
```

### 1.3 Check for deprecated API usage (critical — can block upgrade)
```bash
# Method 1: Quick kubectl check
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Method 2: GKE recommender insights
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=us-west1-b \
    --project=[YOUR_PROJECT_ID] \
    --filter="category.primary_category=RELIABILITY"

# If deprecated APIs found, fix them before proceeding
```

### 1.4 Verify cluster health
```bash
# All nodes should be Ready
kubectl get nodes -o wide

# No stuck pods
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded

# Check system pods
kubectl get pods -n kube-system

# Expected: All pods Running or Completed
```

### 1.5 Check PodDisruptionBudgets (PDBs)
```bash
# List all PDBs
kubectl get pdb -A -o wide

# Check for overly restrictive PDBs (ALLOWED DISRUPTIONS = 0)
kubectl describe pdb -A

# Note any PDBs that might block draining
```

### 1.6 Backup critical configurations
```bash
# Export cluster config
gcloud container clusters describe [YOUR_CLUSTER_NAME] \
  --zone us-west1-b > cluster-backup-$(date +%Y%m%d).yaml

# Export all PDB configs (in case we need to modify them)
kubectl get pdb -A -o yaml > pdb-backup-$(date +%Y%m%d).yaml
```

## Phase 2: Control Plane Upgrade (10-15 minutes)

⚠️ **Important:** Control plane must be upgraded BEFORE node pools. This is required.

### 2.1 Start control plane upgrade
```bash
# Upgrade control plane to 1.33
gcloud container clusters upgrade [YOUR_CLUSTER_NAME] \
  --zone us-west1-b \
  --master \
  --cluster-version 1.33

# When prompted, type 'Y' to confirm
```

### 2.2 Monitor control plane upgrade progress
```bash
# Check operation status
gcloud container operations list \
  --zone us-west1-b \
  --filter="operationType=UPGRADE_MASTER" \
  --limit=1

# Wait for DONE status (usually 10-15 minutes)
```

### 2.3 Verify control plane upgrade
```bash
# Should show 1.33.x
gcloud container clusters describe [YOUR_CLUSTER_NAME] \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"

# Check system pods restarted successfully
kubectl get pods -n kube-system

# Test basic cluster functionality
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Control plane test successful"
```

## Phase 3: Node Pool Upgrades (30-60 minutes per pool)

We'll upgrade node pools one at a time, starting with default-pool.

### 3.1 Configure surge settings for default-pool

First, check the current pool size to determine appropriate surge settings:
```bash
# Check pool size
gcloud container node-pools describe default-pool \
  --cluster [YOUR_CLUSTER_NAME] \
  --zone us-west1-b \
  --format="value(initialNodeCount)"
```

Set surge settings based on pool size (for a typical 3-node pool):
```bash
# Conservative settings: 1 surge node, no unavailable nodes
gcloud container node-pools update default-pool \
  --cluster [YOUR_CLUSTER_NAME] \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# This ensures zero downtime during upgrade
```

### 3.2 Upgrade default-pool
```bash
# Start node pool upgrade
gcloud container node-pools upgrade default-pool \
  --cluster [YOUR_CLUSTER_NAME] \
  --zone us-west1-b \
  --cluster-version 1.33

# When prompted, type 'Y' to confirm
```

### 3.3 Monitor default-pool upgrade progress
```bash
# Watch node versions change (run this in a separate terminal)
watch 'kubectl get nodes -L cloud.google.com/gke-nodepool -o wide'

# Check upgrade operation status
gcloud container operations list \
  --zone us-west1-b \
  --filter="operationType=UPGRADE_NODES AND targetLink~default-pool" \
  --limit=1

# Monitor pod distribution (optional)
kubectl get pods -A -o wide | grep -v kube-system
```

### 3.4 Verify default-pool upgrade completion
```bash
# All default-pool nodes should show 1.33.x
kubectl get nodes -L cloud.google.com/gke-nodepool | grep default-pool

# No pods should be stuck
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded
```

### 3.5 Configure and upgrade workload-pool

Check workload-pool size and set surge settings:
```bash
# Check pool size
gcloud container node-pools describe workload-pool \
  --cluster [YOUR_CLUSTER_NAME] \
  --zone us-west1-b \
  --format="value(initialNodeCount)"

# Set surge settings (adjust based on pool size)
gcloud container node-pools update workload-pool \
  --cluster [YOUR_CLUSTER_NAME] \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade workload-pool
gcloud container node-pools upgrade workload-pool \
  --cluster [YOUR_CLUSTER_NAME] \
  --zone us-west1-b \
  --cluster-version 1.33

# When prompted, type 'Y' to confirm
```

### 3.6 Monitor workload-pool upgrade
```bash
# Watch progress
watch 'kubectl get nodes -L cloud.google.com/gke-nodepool -o wide'

# Check operation status
gcloud container operations list \
  --zone us-west1-b \
  --filter="operationType=UPGRADE_NODES AND targetLink~workload-pool" \
  --limit=1
```

## Phase 4: Post-Upgrade Validation (10-15 minutes)

### 4.1 Verify all components at target version
```bash
# Control plane should be 1.33.x
gcloud container clusters describe [YOUR_CLUSTER_NAME] \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"

# All nodes should be 1.33.x
kubectl get nodes -o wide

# All node pools should show 1.33.x
gcloud container node-pools list --cluster [YOUR_CLUSTER_NAME] --zone us-west1-b
```

### 4.2 Check cluster health
```bash
# All nodes Ready
kubectl get nodes

# No stuck or failing pods
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded

# System pods healthy
kubectl get pods -n kube-system

# Check for any Warning events
kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' | tail -10
```

### 4.3 Test workload functionality
```bash
# Create a test deployment
kubectl create deployment nginx-test --image=nginx:latest --replicas=2

# Wait for pods to be ready
kubectl rollout status deployment nginx-test

# Verify pods are scheduled across nodes
kubectl get pods -l app=nginx-test -o wide

# Test pod networking
kubectl exec -it deployment/nginx-test -- curl localhost

# Cleanup test deployment
kubectl delete deployment nginx-test
```

### 4.4 Verify application-specific health
```bash
# Check your application deployments
kubectl get deployments -A

# Verify StatefulSets (if any)
kubectl get statefulsets -A

# Check services and ingress
kubectl get services -A
kubectl get ingress -A

# Test your application endpoints (replace with your actual endpoints)
# curl https://your-app-url/health
```

## Troubleshooting Common Issues

### If upgrade gets stuck on pod eviction:
```bash
# Check for overly restrictive PDBs
kubectl get pdb -A -o wide

# Temporarily relax PDB (restore after upgrade)
kubectl patch pdb [PDB_NAME] -n [NAMESPACE] \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"100%"}}'
```

### If pods won't schedule on new nodes:
```bash
# Check for resource constraints
kubectl top nodes
kubectl describe nodes | grep -A 5 "Allocated resources"

# Look for pending pods
kubectl get pods -A | grep Pending
kubectl describe pod [PENDING_POD] -n [NAMESPACE]
```

### If you need to pause the upgrade:
```bash
# List current operations
gcloud container operations list --zone us-west1-b --limit=5

# Note: GKE upgrades cannot be paused mid-operation, but you can wait before starting the next node pool
```

## Rollback Plan (Emergency Only)

If you encounter critical issues and need to rollback:

```bash
# Node pool rollback requires creating new pools at old version
# This is complex and time-consuming - only use if absolutely necessary

# 1. Create new pool at old version
gcloud container node-pools create [POOL_NAME]-rollback \
  --cluster [YOUR_CLUSTER_NAME] \
  --zone us-west1-b \
  --cluster-version 1.32 \
  --num-nodes [NODE_COUNT] \
  --machine-type [MACHINE_TYPE]

# 2. Cordon upgraded nodes
kubectl cordon -l cloud.google.com/gke-nodepool=[UPGRADED_POOL]

# 3. Drain workloads to new pool
kubectl drain [NODE_NAME] --ignore-daemonsets --delete-emptydir-data

# 4. Delete old pool after migration complete
```

## Success Criteria Checklist

- [ ] Control plane version: 1.33.x
- [ ] All nodes version: 1.33.x  
- [ ] All pods Running or Completed
- [ ] No Warning events in last 10 minutes
- [ ] Application endpoints responding
- [ ] Test deployment created and deleted successfully

**Total estimated time:** 1-2 hours depending on node pool sizes and workload complexity.

**Next steps after successful upgrade:**
1. Monitor applications for 24-48 hours
2. Update any documentation with new versions
3. Plan regular upgrade schedule to stay current
4. Consider configuring maintenance windows for future auto-upgrades

Replace `[YOUR_CLUSTER_NAME]` and `[YOUR_PROJECT_ID]` with your actual values before running commands.