# GKE Upgrade Runbook: 1.28 → 1.30

**Cluster:** Standard mode, Regular channel, us-west1-b  
**Upgrade path:** 1.28 → 1.29 → 1.30 (sequential minor versions recommended)  
**Node pools:** default-pool, workload-pool

This runbook assumes you have `gcloud` and `kubectl` configured with cluster access.

## Phase 1: Pre-flight Checks

### 1.1 Verify current state
```bash
# Check current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check available versions in Regular channel
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels.REGULAR.validVersions)"

# Verify cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed
```

**✅ Expected:** All nodes Ready, minimal non-Running pods, versions 1.28.x visible.

### 1.2 Check for deprecated APIs (critical!)
```bash
# Check for deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# If you see output, identify the resources using deprecated APIs
kubectl api-resources --verbs=list --namespaced -o name | \
  xargs -n 1 kubectl get --show-kind --ignore-not-found -A
```

**🚨 Stop here if deprecated APIs found.** Fix them before proceeding - they'll cause upgrade failures.

### 1.3 Verify workload readiness
```bash
# Check for bare pods (not managed by controllers)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Check PodDisruptionBudgets
kubectl get pdb -A -o wide

# Check for adequate resource requests (especially important)
kubectl get pods -A -o json | \
  jq '.items[] | select(.spec.containers[].resources.requests == null) | {ns:.metadata.namespace, name:.metadata.name}'
```

**⚠️ Action required if:**
- Bare pods found → wrap in Deployments or accept they'll be deleted
- PDBs showing `ALLOWED DISRUPTIONS: 0` → temporarily relax them during upgrade
- Missing resource requests → add them to pod specs

## Phase 2: Configure Upgrade Settings

### 2.1 Set maintenance window (recommended)
```bash
# Set weekend maintenance window (Saturday 2-6 AM PST)
gcloud container clusters update CLUSTER_NAME \
  --zone us-west1-b \
  --maintenance-window-start 2024-01-01T10:00:00Z \
  --maintenance-window-end 2024-01-01T14:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### 2.2 Configure node pool upgrade strategy
```bash
# Configure surge settings for default-pool (conservative)
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Configure surge settings for workload-pool (balanced)
gcloud container node-pools update workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

**Note:** `maxSurge=1-2, maxUnavailable=0` means new nodes are created before old ones are drained - safer but uses more quota temporarily.

## Phase 3: Upgrade to 1.29

### 3.1 Upgrade control plane to 1.29
```bash
# Start control plane upgrade
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version 1.29

# Monitor progress (this takes ~10-15 minutes)
watch 'gcloud container clusters describe CLUSTER_NAME --zone us-west1-b --format="value(currentMasterVersion, status)"'
```

**✅ Wait for:** Control plane shows version 1.29.x and status RUNNING.

### 3.2 Verify control plane health
```bash
# Check control plane version
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"

# Check system pods
kubectl get pods -n kube-system
kubectl get pods -n gke-system 2>/dev/null || echo "gke-system namespace not found (normal for some versions)"
```

**✅ Expected:** Control plane at 1.29.x, all system pods Running.

### 3.3 Upgrade default-pool to 1.29
```bash
# Start node pool upgrade
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.29

# Monitor node upgrade progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

**✅ Monitor for:** New nodes appearing, old nodes cordoned, pods rescheduling.

### 3.4 Upgrade workload-pool to 1.29
```bash
# Start second node pool upgrade
gcloud container node-pools upgrade workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.29

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

### 3.5 Verify 1.29 upgrade completion
```bash
# Check all versions are 1.29
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed

# Run application smoke tests
# TODO: Add your specific application health checks here
```

**✅ Expected:** All components at 1.29.x, all nodes Ready, workloads healthy.

**⏸️ CHECKPOINT:** Take a 30-minute break here. Monitor applications for stability before proceeding to 1.30.

## Phase 4: Upgrade to 1.30

### 4.1 Upgrade control plane to 1.30
```bash
# Start control plane upgrade to 1.30
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version 1.30

# Monitor progress
watch 'gcloud container clusters describe CLUSTER_NAME --zone us-west1-b --format="value(currentMasterVersion, status)"'
```

### 4.2 Verify control plane health
```bash
# Check control plane version
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"

# Check system pods
kubectl get pods -n kube-system
```

### 4.3 Upgrade default-pool to 1.30
```bash
# Start node pool upgrade
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.30

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

### 4.4 Upgrade workload-pool to 1.30
```bash
# Start second node pool upgrade
gcloud container node-pools upgrade workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.30

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

## Phase 5: Post-Upgrade Validation

### 5.1 Verify final state
```bash
# Confirm all versions are 1.30
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check node status
kubectl get nodes -o wide

# Check for any stuck or failed pods
kubectl get pods -A | grep -v Running | grep -v Completed
```

### 5.2 Application health checks
```bash
# Check deployments are at desired replica count
kubectl get deployments -A

# Check services are accessible
kubectl get services -A

# Check ingress/load balancers
kubectl get ingress -A
```

### 5.3 Clean up and documentation
```bash
# Check for any orphaned resources
kubectl get events -A --field-selector type=Warning | head -20

# Document the upgrade completion
echo "GKE upgrade completed on $(date)"
echo "Cluster: CLUSTER_NAME in us-west1-b"
echo "Final version: $(gcloud container clusters describe CLUSTER_NAME --zone us-west1-b --format='value(currentMasterVersion)')"
```

## Troubleshooting Common Issues

### If upgrade gets stuck:

**Check for PDB issues:**
```bash
kubectl get pdb -A -o wide
# If ALLOWED DISRUPTIONS = 0, temporarily patch:
kubectl patch pdb PDB_NAME -n NAMESPACE -p '{"spec":{"maxUnavailable":"50%"}}'
```

**Check for pending pods:**
```bash
kubectl get pods -A | grep Pending
kubectl describe pod PENDING_POD_NAME -n NAMESPACE
```

**Check for bare pods:**
```bash
kubectl get pods -A -o json | jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
# Delete bare pods: kubectl delete pod POD_NAME -n NAMESPACE
```

**Check upgrade operation status:**
```bash
gcloud container operations list --cluster CLUSTER_NAME --zone us-west1-b --limit=5
```

### Emergency rollback (node pools only):
If you need to rollback node pools (control plane cannot be downgraded):

```bash
# Create new node pool at previous version
gcloud container node-pools create POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version PREVIOUS_VERSION \
  --num-nodes 3

# Cordon problematic nodes
kubectl cordon -l cloud.google.com/gke-nodepool=PROBLEMATIC_POOL

# Wait for workloads to reschedule, then delete old pool
gcloud container node-pools delete PROBLEMATIC_POOL \
  --cluster CLUSTER_NAME \
  --zone us-west1-b
```

## Success Criteria

- ✅ Control plane and all node pools at 1.30.x
- ✅ All nodes in Ready state  
- ✅ All application pods Running
- ✅ Application smoke tests passing
- ✅ No deprecated API warnings in logs

**Estimated total time:** 2-4 hours depending on cluster size and workload complexity.

**Remember:** Replace `CLUSTER_NAME` with your actual cluster name in all commands!