# GKE Upgrade Runbook: 1.28 → 1.30

**Cluster:** Standard cluster on Regular channel  
**Location:** us-west1-b  
**Current version:** 1.28  
**Target version:** 1.30  
**Node pools:** default-pool, workload-pool

⚠️ **IMPORTANT:** We'll upgrade through 1.29 first (1.28→1.29→1.30). Sequential minor version upgrades are safer for catching compatibility issues.

## Prerequisites

- `gcloud` CLI authenticated with cluster admin permissions
- `kubectl` configured for your cluster
- Maintenance window planned (allow 2-4 hours total)

## Pre-Flight Checks

### 1. Verify current state
```bash
# Check current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check available versions in Regular channel
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels.REGULAR.validVersions)"

# Verify cluster is healthy
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed
```

**✅ Expected:** All nodes Ready, minimal non-Running pods

### 2. Check for deprecated APIs (critical!)
```bash
# Check for deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Common deprecated resources to check manually
kubectl get ingresses.extensions -A 2>/dev/null || echo "No deprecated ingresses found"
kubectl get deployments.extensions -A 2>/dev/null || echo "No deprecated deployments found"
```

**✅ Expected:** No deprecated API usage. If found, update those resources first.

### 3. Verify workload readiness
```bash
# Check for bare pods (not managed by controllers)
kubectl get pods -A -o json | jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Check PodDisruptionBudgets
kubectl get pdb -A -o wide

# Verify no overly restrictive PDBs (ALLOWED DISRUPTIONS should not be 0 everywhere)
```

**✅ Expected:** Few/no bare pods, PDBs allow some disruptions

## Phase 1: Control Plane Upgrade to 1.29

### 1. Upgrade control plane to 1.29
```bash
# Start control plane upgrade
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version 1.29

# This will prompt for confirmation - type 'Y' and press Enter
```

**⏱️ Duration:** 10-15 minutes

### 2. Monitor control plane upgrade
```bash
# Check operation status
gcloud container operations list --cluster CLUSTER_NAME --zone us-west1-b --limit=1

# Wait for completion, then verify
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"

# Check system pods are healthy
kubectl get pods -n kube-system
```

**✅ Expected:** Control plane shows 1.29.x, all system pods Running

## Phase 2: Node Pool Upgrades to 1.29

### 1. Configure surge settings (safer approach)
```bash
# Set conservative surge settings for default-pool
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Set conservative surge settings for workload-pool  
gcloud container node-pools update workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### 2. Upgrade default-pool to 1.29
```bash
# Start node pool upgrade
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.29

# Monitor progress (run in separate terminal)
watch 'kubectl get nodes -o wide'
```

**⏱️ Duration:** 20-40 minutes depending on node count

### 3. Validate default-pool upgrade
```bash
# Check all nodes in default-pool are at 1.29
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool

# Check no pods are stuck
kubectl get pods -A | grep -E "Terminating|Pending|CrashLoop"

# If pods are stuck, see troubleshooting section below
```

### 4. Upgrade workload-pool to 1.29
```bash
# Start workload-pool upgrade
gcloud container node-pools upgrade workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.29

# Monitor progress
watch 'kubectl get nodes -o wide'
```

### 5. Validate complete 1.29 upgrade
```bash
# Verify all components at 1.29
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed
kubectl get deployments -A | grep -v "READY"
```

**✅ Checkpoint:** Control plane and all nodes should show 1.29.x

## Phase 3: Upgrade to 1.30 (Repeat Process)

### 1. Control plane to 1.30
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version 1.30

# Wait and verify
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"

kubectl get pods -n kube-system
```

### 2. Node pools to 1.30
```bash
# Upgrade default-pool
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.30

# Monitor and wait for completion
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool'

# Upgrade workload-pool
gcloud container node-pools upgrade workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.30

# Monitor and wait for completion  
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=workload-pool'
```

## Final Validation

```bash
# Verify final state
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# All should show 1.30.x
kubectl get nodes

# Check application health
kubectl get pods -A
kubectl get deployments -A
kubectl get services -A

# Test a sample application if possible
kubectl run test-pod --image=nginx --rm -it --restart=Never -- curl -I http://your-app-service
```

## Troubleshooting Common Issues

### If upgrade gets stuck

**1. Check for blocking PDBs:**
```bash
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# Temporarily relax if needed
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

**2. Check for pending pods:**
```bash
kubectl get pods -A | grep Pending
kubectl describe pods PENDING_POD -n NAMESPACE

# Often resource constraints - check node capacity
kubectl describe nodes
```

**3. Check for bare pods blocking drain:**
```bash
kubectl get pods -A -o json | jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Delete bare pods (they won't reschedule anyway)
kubectl delete pod POD_NAME -n NAMESPACE
```

**4. Check operation status:**
```bash
gcloud container operations list --cluster CLUSTER_NAME --zone us-west1-b --limit=5
```

### Emergency rollback (node pools only)

If you need to rollback a node pool (control plane can't be downgraded):

```bash
# Create new node pool at old version
gcloud container node-pools create POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version OLD_VERSION \
  --num-nodes 3 \
  --machine-type e2-standard-4

# Cordon old nodes and migrate workloads
kubectl cordon -l cloud.google.com/gke-nodepool=POOL_NAME
# Wait for pods to migrate to new nodes, then delete old pool
```

## Post-Upgrade Tasks

- [ ] Document upgrade completion and any issues encountered
- [ ] Update any CI/CD references to cluster version
- [ ] Monitor applications for 24-48 hours
- [ ] Consider setting up maintenance windows for future auto-upgrades:

```bash
# Example: Saturday 2-6 AM UTC maintenance window
gcloud container clusters update CLUSTER_NAME \
  --zone us-west1-b \
  --maintenance-window-start 2024-01-01T02:00:00Z \
  --maintenance-window-end 2024-01-01T06:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Total expected duration:** 2-4 hours  
**Safe abort points:** After each major phase completion  
**Support:** If stuck >2 hours on any single operation, contact GKE support with cluster name and operation ID