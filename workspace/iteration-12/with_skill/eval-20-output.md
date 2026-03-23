# GKE Upgrade Runbook: 1.32 → 1.32 (Patch Update)

**Cluster:** `your-cluster-name` | **Zone:** `us-west1-b` | **Channel:** Regular  
**Current:** 1.32.x | **Target:** Latest 1.32 patch

> ⚠️ **Replace `your-cluster-name` with your actual cluster name in all commands below**

## Phase 1: Pre-flight Checks (15 minutes)

### 1.1 Get current cluster information
```bash
# Check current versions
gcloud container clusters describe your-cluster-name \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"
```
**Expected output:** Shows control plane and both node pools at some 1.32.x version

### 1.2 Check available versions
```bash
# See what 1.32 patch versions are available
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels.regular.validVersions)" | grep "1.32"
```

### 1.3 Verify cluster health
```bash
# All nodes should be Ready
kubectl get nodes
```
**Expected:** All nodes show `STATUS: Ready`

```bash
# Check for any problematic pods
kubectl get pods -A | grep -v Running | grep -v Completed
```
**Expected:** Should return empty or only completed jobs

### 1.4 Check for PodDisruptionBudgets
```bash
# List all PDBs - these can block upgrades
kubectl get pdb -A -o wide
```
**Note any PDBs with ALLOWED DISRUPTIONS = 0** - we may need to relax these temporarily

### 1.5 Check for bare pods (pods without controllers)
```bash
# Find any bare pods that won't be rescheduled
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```
**If any bare pods exist, delete them now or they'll block the upgrade**

## Phase 2: Configure Upgrade Strategy (10 minutes)

### 2.1 Set conservative surge settings for both node pools
```bash
# Configure default-pool for safe upgrade
gcloud container node-pools update default-pool \
  --cluster your-cluster-name \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Configure workload-pool for safe upgrade  
gcloud container node-pools update workload-pool \
  --cluster your-cluster-name \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**What this does:** Creates 1 new node before terminating old ones, ensuring no capacity loss

### 2.2 Verify surge settings applied
```bash
gcloud container node-pools list --cluster your-cluster-name --zone us-west1-b \
  --format="table(name,config.machineType,initialNodeCount,management.upgradeOptions.surgeSettings)"
```

## Phase 3: Control Plane Upgrade (15-20 minutes)

### 3.1 Start control plane upgrade
```bash
# Get the latest 1.32 patch version from step 1.2 output and use it here
gcloud container clusters upgrade your-cluster-name \
  --zone us-west1-b \
  --master \
  --cluster-version 1.32.LATEST_PATCH_NUMBER
```

**Confirmation prompt:** Type `Y` when prompted

**Expected:** Command will show "Upgrading your-cluster-name..." and complete in 10-15 minutes

### 3.2 Monitor control plane upgrade
```bash
# Check upgrade progress (run every few minutes)
gcloud container operations list --cluster your-cluster-name --zone us-west1-b --limit=1
```

Wait until the operation shows `DONE` status before proceeding.

### 3.3 Verify control plane upgraded
```bash
# Confirm control plane is at target version
gcloud container clusters describe your-cluster-name \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"
```

**Expected:** Shows the new 1.32.x version you specified

```bash
# Verify system pods are healthy
kubectl get pods -n kube-system
```

**Expected:** All pods should be Running or Completed

## Phase 4: Node Pool Upgrades (30-45 minutes total)

### 4.1 Upgrade default-pool
```bash
# Start upgrading the first node pool
gcloud container node-pools upgrade default-pool \
  --cluster your-cluster-name \
  --zone us-west1-b \
  --cluster-version 1.32.LATEST_PATCH_NUMBER
```

**Confirmation prompt:** Type `Y` when prompted

### 4.2 Monitor default-pool upgrade
```bash
# Watch node upgrade progress (run this in a separate terminal)
watch 'kubectl get nodes -o wide'
```

**What to expect:**
- Nodes will show `SchedulingDisabled` when being drained
- New nodes appear with the new version
- Old nodes disappear as upgrade completes
- Process takes 15-25 minutes depending on workloads

### 4.3 Verify default-pool completed
```bash
# Check all nodes in default-pool are at new version
gcloud container node-pools describe default-pool \
  --cluster your-cluster-name \
  --zone us-west1-b \
  --format="value(version)"
```

```bash
# Verify no pods are stuck
kubectl get pods -A | grep -E "Pending|Terminating"
```

**Expected:** Should return empty

### 4.4 Upgrade workload-pool
```bash
# Start upgrading the second node pool
gcloud container node-pools upgrade workload-pool \
  --cluster your-cluster-name \
  --zone us-west1-b \
  --cluster-version 1.32.LATEST_PATCH_NUMBER
```

### 4.5 Monitor workload-pool upgrade
```bash
# Continue watching node progress
watch 'kubectl get nodes -o wide'
```

Wait for all workload-pool nodes to complete upgrading.

## Phase 5: Post-Upgrade Validation (10 minutes)

### 5.1 Verify all versions match
```bash
# Final version check - everything should match
gcloud container clusters describe your-cluster-name \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"
```

**Expected:** Control plane and both node pools show identical 1.32.x version

### 5.2 Check cluster health
```bash
# All nodes Ready
kubectl get nodes
```

```bash
# All pods healthy
kubectl get pods -A | grep -v Running | grep -v Completed
```

```bash
# System pods healthy
kubectl get pods -n kube-system
```

### 5.3 Verify workload functionality
```bash
# Check your applications (adjust namespaces as needed)
kubectl get deployments -A
kubectl get services -A
```

**Test your applications:** Visit any web interfaces or run smoke tests to confirm everything works

## Troubleshooting

If any step fails, here's what to check:

**Upgrade stuck on node drain:**
```bash
# Check for restrictive PDBs
kubectl get pdb -A -o wide
# If ALLOWED DISRUPTIONS = 0, temporarily patch:
kubectl patch pdb PDB_NAME -n NAMESPACE -p '{"spec":{"maxUnavailable":"50%"}}'
```

**Pods stuck Pending:**
```bash
# Check for resource constraints
kubectl describe pods STUCK_POD_NAME -n NAMESPACE
# Look for "Insufficient cpu/memory" in events
```

**Operation appears hung (>30 minutes with no progress):**
```bash
# Get operation details
gcloud container operations list --cluster your-cluster-name --zone us-west1-b
# Contact support with the operation ID if truly stuck
```

## Success Checklist

- [ ] Control plane upgraded to 1.32.latest
- [ ] Both node pools upgraded to 1.32.latest  
- [ ] All nodes showing Ready status
- [ ] All pods running normally
- [ ] Applications responding correctly
- [ ] No error events in cluster

**Total expected time:** 60-90 minutes

> 💡 **Future upgrades:** Since you're on the Regular channel, GKE will automatically upgrade to new 1.32 patches and eventually to 1.33 when it becomes available. Set up maintenance windows to control when these happen: [Maintenance Windows Guide](https://cloud.google.com/kubernetes-engine/docs/how-to/updating-clusters#maintenance-windows)