# GKE Upgrade Runbook: 1.32 → 1.33

**Cluster:** Standard cluster on Regular channel  
**Current version:** 1.32  
**Target version:** 1.33  
**Location:** us-west1-b  
**Node pools:** default-pool, workload-pool  

This runbook provides complete step-by-step commands for your first GKE upgrade.

## Phase 1: Pre-flight Checks (15-20 minutes)

### 1.1 Verify current cluster state
```bash
# Check current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Expected: Control plane and nodes at 1.32.x
```

### 1.2 Confirm target version availability
```bash
# Check what versions are available in Regular channel
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels.REGULAR.validVersions)"

# Look for 1.33.x versions in the output
```

### 1.3 Check for deprecated APIs (critical)
```bash
# This is the #1 cause of upgrade failures
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# If you see output, you have deprecated API usage that must be fixed first
# Also check the GKE console → your cluster → Insights tab for deprecation warnings
```

### 1.4 Verify cluster health
```bash
# All nodes should be Ready
kubectl get nodes

# No failing pods
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded

# System components healthy
kubectl get pods -n kube-system
```

### 1.5 Check resource capacity
```bash
# Current node utilization
kubectl top nodes

# Available compute quota (you'll need surge capacity)
gcloud compute project-info describe --format="yaml(quotas)" | grep -A2 -B2 CPUS
```

## Phase 2: Configure Upgrade Settings (5 minutes)

### 2.1 Set maintenance window (optional but recommended)
```bash
# Set maintenance window for weekends 2-6 AM PST
gcloud container clusters update CLUSTER_NAME \
  --zone us-west1-b \
  --maintenance-window-start "2024-01-06T10:00:00Z" \
  --maintenance-window-end "2024-01-06T14:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# This only affects auto-upgrades; manual upgrades bypass this window
```

### 2.2 Configure surge settings for node pools
```bash
# For most workloads: conservative settings
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

gcloud container node-pools update workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# maxSurge=2: Creates 2 extra nodes during upgrade
# maxUnavailable=0: Never removes nodes before replacements are ready
```

## Phase 3: Control Plane Upgrade (15-20 minutes)

### 3.1 Start control plane upgrade
```bash
# Upgrade control plane first (always required before nodes)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version 1.33

# When prompted, type 'y' to confirm
# This typically takes 10-15 minutes
```

### 3.2 Monitor control plane upgrade
```bash
# Check operation status
gcloud container operations list \
  --zone us-west1-b \
  --filter="targetLink~CLUSTER_NAME AND operationType=UPGRADE_MASTER"

# Wait for status: DONE
```

### 3.3 Verify control plane upgrade
```bash
# Confirm control plane is now at 1.33.x
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"

# Test API access
kubectl get nodes

# Check system pods restarted successfully
kubectl get pods -n kube-system
```

## Phase 4: Node Pool Upgrades (30-60 minutes)

### 4.1 Upgrade default-pool
```bash
# Start node pool upgrade
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --node-version 1.33

# When prompted, type 'y' to confirm
```

### 4.2 Monitor default-pool upgrade
```bash
# Watch node versions change (run in separate terminal)
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check for any stuck pods
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded

# Monitor upgrade operation
gcloud container operations list \
  --zone us-west1-b \
  --filter="targetLink~default-pool AND operationType=UPGRADE_NODES" \
  --limit=1
```

### 4.3 Verify default-pool completion
```bash
# All nodes in default-pool should show 1.33.x
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool

# Wait for operation status: DONE before proceeding
```

### 4.4 Upgrade workload-pool
```bash
# Start second node pool upgrade
gcloud container node-pools upgrade workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --node-version 1.33

# When prompted, type 'y' to confirm
```

### 4.5 Monitor workload-pool upgrade
```bash
# Continue watching node versions
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check operation progress
gcloud container operations list \
  --zone us-west1-b \
  --filter="targetLink~workload-pool AND operationType=UPGRADE_NODES" \
  --limit=1
```

## Phase 5: Post-Upgrade Validation (10 minutes)

### 5.1 Verify all components at target version
```bash
# All nodes should now be at 1.33.x
kubectl get nodes -o wide

# Confirm both node pools upgraded
gcloud container node-pools list --cluster CLUSTER_NAME --zone us-west1-b

# Control plane version
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"
```

### 5.2 Check cluster health
```bash
# All nodes Ready
kubectl get nodes

# All pods running (no CrashLoopBackOff or Pending)
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded

# System components healthy
kubectl get pods -n kube-system

# No PDB issues remaining
kubectl get pdb -A
```

### 5.3 Application smoke tests
```bash
# Test a simple pod creation
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "Upgrade successful"

# Check your application endpoints
# curl http://YOUR_APP_URL/health
# kubectl get ingress -A
```

## Troubleshooting Common Issues

### If upgrade gets stuck on a node pool:

**Check for blocking PDBs:**
```bash
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# Temporarily relax if found
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

**Check for resource constraints:**
```bash
kubectl get pods -A | grep Pending
kubectl describe nodes | grep -A 5 "Allocated resources"

# If nodes are full, temporarily scale down non-critical workloads:
kubectl scale deployment NON_CRITICAL_APP --replicas=0
```

**Check for bare pods:**
```bash
# These won't reschedule and block drain
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Delete bare pods (they won't reschedule anyway)
kubectl delete pod POD_NAME -n NAMESPACE
```

### Rollback (if critical issues discovered):

```bash
# For control plane: contact GKE support
# For node pools: create new pool at old version
gcloud container node-pools create default-pool-rollback \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --node-version 1.32 \
  --num-nodes 3 \
  --machine-type e2-medium
```

## Timeline Expectations

- **Control plane upgrade:** 10-15 minutes
- **Each node pool upgrade:** 15-30 minutes (depends on pool size and maxSurge setting)
- **Total time:** 45-75 minutes for your 2-pool cluster

## Key Points to Remember

1. **Control plane MUST be upgraded before node pools** — this is required
2. **Surge upgrades create temporary extra nodes** — you'll see more nodes during upgrade
3. **Mixed node versions are normal and safe** during the upgrade process
4. **Manual upgrades ignore maintenance windows** — they start immediately
5. **If something goes wrong, don't panic** — the cluster remains operational during upgrades

Replace `CLUSTER_NAME` with your actual cluster name in all commands. Good luck with your first upgrade!