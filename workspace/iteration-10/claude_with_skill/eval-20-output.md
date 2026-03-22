# GKE Upgrade Runbook: Standard Cluster to 1.32

**Cluster:** Your cluster name  
**Zone:** us-west1-b  
**Channel:** Regular  
**Current:** 1.32.x → **Target:** 1.32.latest  
**Mode:** Standard (2 node pools: default-pool, workload-pool)

This is a **patch upgrade** within the same minor version (1.32), so it's low-risk. We'll upgrade the control plane first, then both node pools.

---

## Phase 1: Pre-flight Checks (15 minutes)

### Step 1: Set your environment variables
```bash
# Replace YOUR_CLUSTER_NAME with your actual cluster name
export CLUSTER_NAME="YOUR_CLUSTER_NAME"
export ZONE="us-west1-b"
export PROJECT_ID="YOUR_PROJECT_ID"

# Verify you're in the right project
gcloud config get-value project
```

### Step 2: Check current cluster state
```bash
# Get current versions
gcloud container clusters describe $CLUSTER_NAME \
  --zone $ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"
```
Expected: Control plane and nodes should show 1.32.x versions

### Step 3: Check available target versions
```bash
# See what 1.32 versions are available in Regular channel
gcloud container get-server-config --zone $ZONE \
  --format="yaml(channels.REGULAR.validVersions)" | grep "1.32"
```
Note the latest 1.32.x version — this will be your target.

### Step 4: Verify cluster health
```bash
# All nodes should be Ready
kubectl get nodes

# No stuck pods (should only show Running/Completed)
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded
```

### Step 5: Check for any blocking PDBs
```bash
# Look for PodDisruptionBudgets that might block upgrades
kubectl get pdb -A -o wide
```
If any show "ALLOWED DISRUPTIONS" as 0, note them — we may need to temporarily relax them.

---

## Phase 2: Control Plane Upgrade (20-30 minutes)

### Step 6: Start control plane upgrade
```bash
# Find the exact target version from step 3, then run:
# Replace TARGET_VERSION with the latest 1.32.x from step 3
export TARGET_VERSION="1.32.X-gke.XXXXX"  # Use actual version from step 3

gcloud container clusters upgrade $CLUSTER_NAME \
  --zone $ZONE \
  --master \
  --cluster-version $TARGET_VERSION
```
When prompted, type `Y` to confirm.

### Step 7: Monitor control plane upgrade progress
```bash
# Check the operation status (wait for completion)
gcloud container operations list --cluster $CLUSTER_NAME --zone $ZONE --limit=1

# Once complete, verify control plane version
gcloud container clusters describe $CLUSTER_NAME \
  --zone $ZONE \
  --format="value(currentMasterVersion)"
```
This should show your target version. Wait until this matches before proceeding.

### Step 8: Verify control plane health
```bash
# System pods should all be Running
kubectl get pods -n kube-system

# API server should be responsive
kubectl get nodes
```

---

## Phase 3: Node Pool Upgrades (30-60 minutes total)

### Step 9: Configure surge upgrade settings (for faster, safer upgrades)
```bash
# Set surge settings for default-pool (stateless workloads)
gcloud container node-pools update default-pool \
  --cluster $CLUSTER_NAME \
  --zone $ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# Set surge settings for workload-pool (more conservative)
gcloud container node-pools update workload-pool \
  --cluster $CLUSTER_NAME \
  --zone $ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### Step 10: Upgrade first node pool (default-pool)
```bash
gcloud container node-pools upgrade default-pool \
  --cluster $CLUSTER_NAME \
  --zone $ZONE \
  --cluster-version $TARGET_VERSION
```
When prompted, type `Y` to confirm.

### Step 11: Monitor default-pool upgrade
```bash
# Watch nodes getting replaced (this will take 15-30 minutes)
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "NAME|default-pool"'
```
Press Ctrl+C to stop watching. You'll see nodes cycling through NotReady → Ready as they're replaced.

### Step 12: Verify default-pool completion
```bash
# Check all default-pool nodes are at target version
gcloud container node-pools describe default-pool \
  --cluster $CLUSTER_NAME \
  --zone $ZONE \
  --format="value(version)"

# Should show your target version
```

### Step 13: Upgrade second node pool (workload-pool)
```bash
gcloud container node-pools upgrade workload-pool \
  --cluster $CLUSTER_NAME \
  --zone $ZONE \
  --cluster-version $TARGET_VERSION
```
When prompted, type `Y` to confirm.

### Step 14: Monitor workload-pool upgrade
```bash
# Watch workload-pool nodes getting replaced
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "NAME|workload-pool"'
```

---

## Phase 4: Final Validation (10 minutes)

### Step 15: Verify all versions are correct
```bash
# Control plane and all node pools should show target version
gcloud container clusters describe $CLUSTER_NAME \
  --zone $ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"
```

### Step 16: Check cluster health
```bash
# All nodes Ready
kubectl get nodes

# No problematic pods
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded

# System components healthy
kubectl get pods -n kube-system | grep -v Running
```

### Step 17: Basic workload validation
```bash
# Check deployments are at desired replica count
kubectl get deployments -A

# Check for any CrashLoopBackOff or ImagePullBackOff pods
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
```

---

## Troubleshooting

### If a node pool upgrade gets stuck:

1. **Check for PDB issues:**
```bash
kubectl get pdb -A -o wide
# If any show ALLOWED DISRUPTIONS = 0:
kubectl describe pdb PDB_NAME -n NAMESPACE
```

2. **Temporarily relax blocking PDBs:**
```bash
# Backup first
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup.yaml

# Allow more disruptions temporarily
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

3. **Check for bare pods (not managed by controllers):**
```bash
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```
Delete any bare pods — they won't reschedule anyway.

### If you need to cancel an upgrade:
```bash
# List current operations
gcloud container operations list --cluster $CLUSTER_NAME --zone $ZONE

# Operations cannot be canceled, but will complete the current node and stop
```

---

## Expected Timeline
- **Pre-flight:** 15 minutes
- **Control plane:** 20-30 minutes  
- **Node pool 1:** 15-30 minutes
- **Node pool 2:** 15-30 minutes
- **Validation:** 10 minutes
- **Total:** 1.5-2 hours

## Success Criteria
✅ Control plane at target 1.32.x version  
✅ Both node pools at target 1.32.x version  
✅ All nodes show Ready  
✅ All system pods Running  
✅ Application pods healthy  

Your cluster will now receive automatic patch updates within 1.32. The next minor version (1.33) will arrive automatically when it reaches the Regular channel, respecting any maintenance windows you have configured.