# GKE Standard Cluster Upgrade: 1.28 → 1.30
**Complete Runbook for Regular Channel Cluster**

## Overview
- **Cluster**: Standard mode, Regular channel
- **Location**: us-west1-b
- **Upgrade path**: 1.28 → 1.29 → 1.30 (sequential minor versions for safety)
- **Node pools**: default-pool, workload-pool
- **Strategy**: Control plane first, then node pools with surge upgrades

⚠️ **Important**: This upgrade will take 45-90 minutes total. Plan accordingly.

---

## Phase 1: Pre-Flight Checks (15 minutes)

### Step 1.1: Verify current state
```bash
# Set variables (replace with your actual cluster name)
export CLUSTER_NAME="your-cluster-name"
export ZONE="us-west1-b"

# Check current versions
gcloud container clusters describe $CLUSTER_NAME \
  --zone $ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"
```
**Expected**: Control plane and both node pools should show 1.28.x

### Step 1.2: Verify available versions
```bash
# Check what 1.29 and 1.30 versions are available in Regular channel
gcloud container get-server-config --zone $ZONE \
  --format="yaml(channels.REGULAR.validVersions)" | grep -E "1\.(29|30)"
```
**Expected**: You should see versions like 1.29.x and 1.30.x listed

### Step 1.3: Check cluster health
```bash
# All nodes should be Ready
kubectl get nodes

# No failing pods (ignore Completed jobs)
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded
```
**Expected**: All nodes Ready, no stuck pods

### Step 1.4: Check for deprecated APIs
```bash
# Look for deprecated API usage (this is the #1 upgrade killer)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated || echo "No deprecated APIs found"
```
**Expected**: Ideally "No deprecated APIs found" — if you see output, investigate those APIs

### Step 1.5: Backup critical workload info
```bash
# Save current deployment states
kubectl get deployments -A -o yaml > deployments-backup.yaml
kubectl get statefulsets -A -o yaml > statefulsets-backup.yaml

# Check for Pod Disruption Budgets
kubectl get pdb -A
```
**Expected**: Files created successfully. Note any PDBs shown.

---

## Phase 2: Control Plane Upgrade to 1.29 (10-15 minutes)

### Step 2.1: Start control plane upgrade
```bash
# Get the exact 1.29 version from step 1.2 output and replace below
export TARGET_129="1.29.x-gke.xxxx"  # Use actual version from step 1.2

gcloud container clusters upgrade $CLUSTER_NAME \
  --zone $ZONE \
  --master \
  --cluster-version $TARGET_129
```
**Expected**: You'll be prompted to confirm. Type 'y' and press Enter.

### Step 2.2: Monitor control plane upgrade
```bash
# Check upgrade progress (run every 2-3 minutes)
gcloud container operations list --cluster $CLUSTER_NAME --zone $ZONE --limit=1

# When complete, verify new control plane version
gcloud container clusters describe $CLUSTER_NAME \
  --zone $ZONE \
  --format="value(currentMasterVersion)"
```
**Expected**: Shows 1.29.x when complete

### Step 2.3: Verify control plane health
```bash
# System pods should be running
kubectl get pods -n kube-system | grep -v Running || echo "All system pods running"

# API server responsive
kubectl get nodes
```
**Expected**: All system pods Running, nodes list displays normally

---

## Phase 3: Node Pool Upgrades to 1.29 (20-30 minutes)

### Step 3.1: Configure surge settings for default-pool
```bash
# Conservative settings for first upgrade
gcloud container node-pools update default-pool \
  --cluster $CLUSTER_NAME \
  --zone $ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### Step 3.2: Upgrade default-pool
```bash
gcloud container node-pools upgrade default-pool \
  --cluster $CLUSTER_NAME \
  --zone $ZONE \
  --cluster-version $TARGET_129
```
**Expected**: Prompted to confirm. Type 'y' and press Enter.

### Step 3.3: Monitor default-pool upgrade
```bash
# Watch node status (Ctrl+C to exit when done)
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "NAME|default-pool"'
```
**Expected**: You'll see old nodes cordoned/drained, new 1.29 nodes join

### Step 3.4: Configure and upgrade workload-pool
```bash
# Same settings for workload-pool
gcloud container node-pools update workload-pool \
  --cluster $CLUSTER_NAME \
  --zone $ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Start upgrade
gcloud container node-pools upgrade workload-pool \
  --cluster $CLUSTER_NAME \
  --zone $ZONE \
  --cluster-version $TARGET_129
```

### Step 3.5: Monitor workload-pool upgrade
```bash
# Watch until all nodes show 1.29
watch 'kubectl get nodes -o wide'
```

### Step 3.6: Verify 1.29 upgrade complete
```bash
# All components should show 1.29.x
gcloud container clusters describe $CLUSTER_NAME \
  --zone $ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check workload health
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded || echo "All pods healthy"
```

---

## Phase 4: Upgrade to 1.30 (15-20 minutes)

### Step 4.1: Control plane to 1.30
```bash
# Get exact 1.30 version
export TARGET_130="1.30.x-gke.xxxx"  # Use actual version from step 1.2

gcloud container clusters upgrade $CLUSTER_NAME \
  --zone $ZONE \
  --master \
  --cluster-version $TARGET_130
```

### Step 4.2: Monitor and verify control plane
```bash
# Wait for completion
gcloud container operations list --cluster $CLUSTER_NAME --zone $ZONE --limit=1

# Verify version
gcloud container clusters describe $CLUSTER_NAME \
  --zone $ZONE \
  --format="value(currentMasterVersion)"
```
**Expected**: Shows 1.30.x

### Step 4.3: Upgrade both node pools to 1.30
```bash
# default-pool first
gcloud container node-pools upgrade default-pool \
  --cluster $CLUSTER_NAME \
  --zone $ZONE \
  --cluster-version $TARGET_130

# Wait for completion, then workload-pool
gcloud container node-pools upgrade workload-pool \
  --cluster $CLUSTER_NAME \
  --zone $ZONE \
  --cluster-version $TARGET_130
```

### Step 4.4: Final verification
```bash
# All components at 1.30
gcloud container clusters describe $CLUSTER_NAME \
  --zone $ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# All nodes Ready
kubectl get nodes

# Workload health check
kubectl get deployments -A
kubectl get statefulsets -A
```

---

## Phase 5: Post-Upgrade Validation (10 minutes)

### Step 5.1: System health checks
```bash
# No failed pods
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded | grep -v NAMESPACE || echo "All pods healthy"

# System pods running
kubectl get pods -n kube-system | grep -v Running || echo "All system pods healthy"

# PDBs not blocking
kubectl get pdb -A
```

### Step 5.2: Application smoke tests
```bash
# If you have ingresses/services, test them
kubectl get ingress -A
kubectl get services -A --field-selector spec.type=LoadBalancer

# Check your specific applications
kubectl get deployment -n your-app-namespace  # Replace with actual namespace
```

### Step 5.3: Clean up
```bash
# Remove backup files if everything looks good
rm deployments-backup.yaml statefulsets-backup.yaml

# Document the upgrade
echo "GKE upgrade completed: $(date)" >> upgrade-log.txt
```

---

## Troubleshooting

If anything gets stuck during the upgrade:

### Pods won't drain from nodes
```bash
# Check what's blocking
kubectl get pdb -A
kubectl get pods -A | grep Terminating

# If PDB is too restrictive, temporarily patch it:
kubectl patch pdb YOUR_PDB_NAME -n NAMESPACE -p '{"spec":{"maxUnavailable":"100%"}}'
```

### Upgrade operation seems stuck
```bash
# Check operation status
gcloud container operations list --cluster $CLUSTER_NAME --zone $ZONE --limit=5

# If stuck for >30 minutes with no node changes, contact Google Cloud Support
```

### Workload issues after upgrade
```bash
# Compare with backups
kubectl get deployments -A -o yaml > deployments-current.yaml
diff deployments-backup.yaml deployments-current.yaml

# Check events for errors
kubectl get events -A --sort-by='.firstTimestamp' | tail -20
```

---

## Summary

This runbook upgrades your cluster through:
1. **1.28 → 1.29**: Control plane + both node pools
2. **1.29 → 1.30**: Control plane + both node pools

**Total expected time**: 60-90 minutes

**What to watch for**:
- Each phase completing before moving to the next
- All nodes showing as Ready
- No pods stuck in Terminating or Pending states
- Your applications remaining accessible throughout

The sequential approach (1.28→1.29→1.30) is safer than jumping directly to 1.30, as it catches any compatibility issues at the first minor version bump.