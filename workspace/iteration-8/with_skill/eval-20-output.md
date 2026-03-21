# GKE Upgrade Runbook: 1.32 → 1.32 (Same Version)

## Important Note

Your cluster is already at version 1.32. This runbook will show you how to verify your cluster state and understand the upgrade process for future use. If you meant to upgrade to a different version (like 1.33), please specify the target version.

## Overview
- **Cluster**: Standard mode, Regular channel
- **Location**: us-west1-b 
- **Current version**: 1.32
- **Target version**: 1.32 (no upgrade needed)
- **Node pools**: default-pool, workload-pool

---

## Phase 1: Pre-flight Checks

### 1.1 Verify current cluster state
```bash
# Check current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Expected output: All should show 1.32.x
```

### 1.2 Check available versions
```bash
# See what versions are available in Regular channel
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels.REGULAR)"

# This shows what versions you could upgrade to
```

### 1.3 Verify cluster health
```bash
# All nodes should be Ready
kubectl get nodes -o wide

# System pods should be Running
kubectl get pods -n kube-system

# Check for any problematic pods
kubectl get pods -A | grep -v Running | grep -v Completed
```

### 1.4 Check for deprecated APIs (important for future upgrades)
```bash
# This command checks if you're using any deprecated Kubernetes APIs
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# If this returns results, you'll need to fix those before future upgrades
```

---

## Phase 2: Understanding Your Current Configuration

### 2.1 Check maintenance windows
```bash
# See if you have maintenance windows configured
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="yaml(maintenancePolicy)"
```

### 2.2 Check auto-upgrade status
```bash
# See when your cluster might auto-upgrade next
gcloud container clusters get-upgrade-info CLUSTER_NAME --zone us-west1-b
```

### 2.3 Check node pool upgrade settings
```bash
# Check current surge settings for both pools
gcloud container node-pools describe default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --format="yaml(upgradeSettings)"

gcloud container node-pools describe workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --format="yaml(upgradeSettings)"
```

---

## Phase 3: Future Upgrade Preparation

Since your cluster is already at 1.32, here's how to prepare for the next upgrade:

### 3.1 Configure maintenance window (recommended)
```bash
# Set maintenance window for Saturday 2 AM - 6 AM
gcloud container clusters update CLUSTER_NAME \
  --zone us-west1-b \
  --maintenance-window-start "2024-12-14T02:00:00Z" \
  --maintenance-window-end "2024-12-14T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### 3.2 Configure surge settings for faster upgrades
```bash
# For default-pool (assuming stateless workloads)
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# For workload-pool (conservative settings for safety)
gcloud container node-pools update workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### 3.3 Verify workload readiness
```bash
# Check for PodDisruptionBudgets
kubectl get pdb -A

# Check for bare pods (not managed by controllers)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# If this returns any pods, you should wrap them in Deployments
```

---

## Phase 4: When You Actually Need to Upgrade

**For future reference when you want to upgrade to 1.33 or later:**

### 4.1 Control plane upgrade first
```bash
# Upgrade control plane to target version (example: 1.33.1-gke.1000)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version TARGET_VERSION

# Wait 10-15 minutes, then verify
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"
```

### 4.2 Node pool upgrades (after control plane is done)
```bash
# Upgrade default-pool
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version TARGET_VERSION

# Monitor progress (Ctrl+C to exit)
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Upgrade workload-pool (wait until default-pool is complete)
gcloud container node-pools upgrade workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version TARGET_VERSION
```

### 4.3 Post-upgrade validation
```bash
# Verify all versions match
gcloud container node-pools list --cluster CLUSTER_NAME --zone us-west1-b

# Check all nodes are ready
kubectl get nodes

# Check all pods are healthy
kubectl get pods -A | grep -v Running | grep -v Completed

# Should return nothing if all is well
```

---

## Important Notes

1. **Your cluster is already at 1.32** - no upgrade needed right now
2. **Auto-upgrades are enabled** - GKE will automatically upgrade your cluster when new versions become available in the Regular channel
3. **Control plane upgrades first** - Always upgrade the control plane before node pools
4. **One node pool at a time** - Don't upgrade both node pools simultaneously
5. **Monitor throughout** - Watch for stuck pods or nodes during upgrades

## Emergency Contacts

- **If upgrade gets stuck**: Check troubleshooting section below
- **If pods won't drain**: Look for PodDisruptionBudgets that are too restrictive
- **If nodes won't come up**: Check compute quotas and network connectivity

## Quick Troubleshooting

```bash
# If pods are stuck terminating
kubectl get pods -A | grep Terminating

# If PDBs are blocking drain
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# If upgrade operation is stuck
gcloud container operations list --cluster CLUSTER_NAME --zone us-west1-b
```

---

**Replace `CLUSTER_NAME` with your actual cluster name in all commands above.**

Since your cluster is already at the target version, use this runbook as a reference for future upgrades. The Regular channel will automatically propose upgrades when 1.33 becomes available (typically 4-6 weeks after 1.32).