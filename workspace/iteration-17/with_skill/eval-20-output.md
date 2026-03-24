# GKE Upgrade Runbook: 1.32 → 1.33

**Cluster:** Standard cluster on Regular channel  
**Location:** us-west1-b  
**Target:** 1.32 → 1.33  
**Node pools:** default-pool, workload-pool  

This runbook provides every command needed for your first GKE upgrade. Follow each section in order.

## Phase 1: Pre-flight Checks (30 minutes)

### 1.1 Verify current cluster state
```bash
# Check current versions
gcloud container clusters describe YOUR_CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Expected output: Control plane and nodes should show 1.32.x
```

### 1.2 Confirm target version availability
```bash
# Check available versions in Regular channel
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels.REGULAR.validVersions)"

# Look for 1.33.x versions in the output
```

### 1.3 Check for deprecated APIs (critical)
```bash
# This is the #1 cause of upgrade failures
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# If you see output, you have deprecated API usage that must be fixed first
# Also check the GKE console → Clusters → YOUR_CLUSTER → Insights tab
```

### 1.4 Verify cluster health
```bash
# All nodes should be Ready
kubectl get nodes

# No pods should be in error states
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed | grep -v Succeeded

# Check system pods are healthy
kubectl get pods -n kube-system
```

### 1.5 Check workload readiness
```bash
# Verify no bare pods (they won't be rescheduled)
kubectl get pods --all-namespaces -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Check PDBs aren't too restrictive
kubectl get pdb --all-namespaces -o wide

# Look for PDBs with ALLOWED DISRUPTIONS = 0
```

**⚠️ STOP**: If you found deprecated APIs or bare pods, fix these before proceeding.

## Phase 2: Configure Node Pool Upgrade Strategy (10 minutes)

Since this is your first upgrade and you want minimal risk, we'll use conservative surge settings.

### 2.1 Configure default-pool
```bash
# Conservative settings: 1 surge node, no unavailable nodes
gcloud container node-pools update default-pool \
  --cluster YOUR_CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### 2.2 Configure workload-pool
```bash
# Same conservative settings
gcloud container node-pools update workload-pool \
  --cluster YOUR_CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### 2.3 Verify configuration
```bash
gcloud container node-pools describe default-pool \
  --cluster YOUR_CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(upgradeSettings.maxSurge, upgradeSettings.maxUnavailable)"

gcloud container node-pools describe workload-pool \
  --cluster YOUR_CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(upgradeSettings.maxSurge, upgradeSettings.maxUnavailable)"

# Each should output: 1, 0
```

## Phase 3: Control Plane Upgrade (15-30 minutes)

The control plane must be upgraded before node pools.

### 3.1 Start control plane upgrade
```bash
gcloud container clusters upgrade YOUR_CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version 1.33

# When prompted "Do you want to continue (Y/n)?", type: Y
```

### 3.2 Monitor control plane upgrade progress
```bash
# Check upgrade operation status
gcloud container operations list \
  --cluster YOUR_CLUSTER_NAME \
  --zone us-west1-b \
  --filter="operationType=UPGRADE_MASTER" \
  --limit=1

# Wait for STATUS: DONE (typically 10-15 minutes)
# You can re-run this command to check progress
```

### 3.3 Verify control plane upgrade
```bash
# Control plane should now show 1.33.x
gcloud container clusters describe YOUR_CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"

# System pods should be healthy
kubectl get pods -n kube-system

# API should be responsive
kubectl get nodes
```

**Expected:** Control plane at 1.33.x, nodes still at 1.32.x (this is normal)

## Phase 4: Node Pool Upgrades (30-60 minutes per pool)

Now upgrade each node pool. We'll do them sequentially for safety.

### 4.1 Upgrade default-pool first
```bash
gcloud container node-pools upgrade default-pool \
  --cluster YOUR_CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33

# When prompted, type: Y
```

### 4.2 Monitor default-pool upgrade
```bash
# Watch node versions change
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Press Ctrl+C to exit watch when you see all default-pool nodes at 1.33.x
```

Alternative monitoring (if `watch` isn't available):
```bash
# Run this periodically to check progress
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,POOL:.metadata.labels.cloud\\.google\\.com/gke-nodepool

# Check upgrade operation
gcloud container operations list \
  --cluster YOUR_CLUSTER_NAME \
  --zone us-west1-b \
  --filter="operationType=UPGRADE_NODES" \
  --limit=1
```

### 4.3 Verify default-pool upgrade completed
```bash
# All default-pool nodes should be at 1.33.x
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool

# No pods should be stuck
kubectl get pods --all-namespaces | grep -E "Pending|Terminating|CrashLoop"
```

### 4.4 Upgrade workload-pool
```bash
gcloud container node-pools upgrade workload-pool \
  --cluster YOUR_CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33

# When prompted, type: Y
```

### 4.5 Monitor workload-pool upgrade
```bash
# Same monitoring as before
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Or check periodically:
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,POOL:.metadata.labels.cloud\\.google\\.com/gke-nodepool
```

### 4.6 Verify workload-pool upgrade completed
```bash
# All workload-pool nodes should be at 1.33.x
kubectl get nodes -l cloud.google.com/gke-nodepool=workload-pool

# Check operation completed
gcloud container operations list \
  --cluster YOUR_CLUSTER_NAME \
  --zone us-west1-b \
  --filter="operationType=UPGRADE_NODES" \
  --limit=1
```

## Phase 5: Post-Upgrade Validation (15 minutes)

### 5.1 Verify cluster state
```bash
# All components should be at 1.33.x
gcloud container clusters describe YOUR_CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# All nodes Ready
kubectl get nodes

# System pods healthy
kubectl get pods -n kube-system
```

### 5.2 Application health checks
```bash
# No pods in error states
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed | grep -v Succeeded

# All deployments at desired replica count
kubectl get deployments --all-namespaces

# All StatefulSets ready (if you have any)
kubectl get statefulsets --all-namespaces
```

### 5.3 Test basic functionality
```bash
# Create a test pod to verify scheduling works
kubectl run test-upgrade --image=nginx --rm -it --restart=Never -- echo "Upgrade successful"

# Should output: "Upgrade successful" and pod should be automatically deleted
```

## Troubleshooting Common Issues

### If node upgrade gets stuck:

**Check for PDB blocking drain:**
```bash
kubectl get pdb --all-namespaces -o wide
# Look for ALLOWED DISRUPTIONS = 0

# Temporarily relax the PDB:
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"100%"}}'
```

**Check for resource constraints:**
```bash
kubectl get pods --all-namespaces | grep Pending
kubectl get events --all-namespaces --field-selector reason=FailedScheduling

# Solution: Scale down non-critical workloads temporarily
kubectl scale deployment DEPLOYMENT_NAME --replicas=0 -n NAMESPACE
```

**Check for bare pods:**
```bash
kubectl get pods --all-namespaces -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Solution: Delete bare pods (they can't be rescheduled anyway)
kubectl delete pod POD_NAME -n NAMESPACE
```

### If you need to cancel an upgrade:
```bash
# List current operations
gcloud container operations list --cluster YOUR_CLUSTER_NAME --zone us-west1-b

# You cannot cancel a control plane upgrade once started
# Node pool upgrades will complete the current node and then stop
```

## Timeline Expectations

- **Control plane upgrade:** 10-15 minutes
- **Each node pool upgrade:** 30-60 minutes (depends on node count and surge settings)
- **Total upgrade time:** 1.5-2.5 hours for your 2-pool cluster

## Success Criteria

✅ Control plane at 1.33.x  
✅ All nodes at 1.33.x  
✅ All pods Running or Completed  
✅ System pods healthy in kube-system namespace  
✅ Applications responding normally  

## Next Steps After Upgrade

1. **Update your documentation** with the new version
2. **Review GKE release notes** for 1.33 features you can now use
3. **Plan your next upgrade cadence** - Regular channel gets updates monthly
4. **Consider setting up maintenance windows** for predictable future upgrades
5. **Monitor your applications** for the next 24-48 hours

**Pro tip:** Now that you've done your first upgrade, future upgrades will be much easier. GKE's auto-upgrade feature can handle routine updates automatically if you configure maintenance windows and exclusions appropriately.