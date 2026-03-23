You're dealing with a **version skew violation** — your node pool is 3 minor versions behind the control plane (1.28 vs 1.31), which exceeds GKE's supported 2-version skew limit. This creates several risks:

- **API compatibility issues** — nodes may not understand newer API objects
- **Security vulnerabilities** — 1.28 is missing 3+ years of patches
- **Support limitations** — this configuration is outside supported bounds
- **Potential cluster instability** — newer control plane features may break older nodes

## Immediate Assessment

First, let's understand what you're working with:

```bash
# Check exact versions and node pool status
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version, nodePools[].status)"

# Check for any blocking maintenance exclusions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy)"

# See if nodes are actually functional
kubectl get nodes -o wide
kubectl get pods -A | grep -v Running | grep -v Completed
```

## Upgrade Strategy

You **cannot** do a single skip-level upgrade from 1.28 → 1.31 (that's N+3, unsupported). You have two options:

### Option 1: Sequential Skip-Level Upgrades (Recommended)
Do two sequential skip-level upgrades within the 2-version limit:

1. **1.28 → 1.30** (N+2, supported)
2. **1.30 → 1.31** (N+1, supported)

### Option 2: Replace the Node Pool
Create a new pool at 1.31 and migrate workloads. Faster but more disruptive.

## Upgrade Plan: Sequential Skip-Level

### Pre-flight Checks
```bash
# Verify available versions in your release channel
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels)"

# Check for deprecated API usage (major concern with 3-version jump)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Ensure workload readiness
kubectl get pdb -A  # Check for overly restrictive PDBs
kubectl get pods -A -o json | jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'  # Find bare pods
```

### Step 1: Configure Upgrade Strategy
```bash
# Set conservative surge settings due to large version gap
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### Step 2: First Skip-Level (1.28 → 1.30)
```bash
# Upgrade to 1.30 (find exact patch version from get-server-config above)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30.X-gke.XXXX

# Monitor progress (this will take time)
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Validate step 1 completion
gcloud container node-pools describe NODE_POOL_NAME \
  --cluster CLUSTER_NAME --zone ZONE \
  --format="value(version)"
```

### Step 3: Second Skip-Level (1.30 → 1.31)
```bash
# Only proceed once step 1 is 100% complete
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.X-gke.XXXX

# Final validation
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed
```

## Alternative: Node Pool Replacement

If you need faster resolution or the sequential upgrade is problematic:

```bash
# Create new pool at target version
gcloud container node-pools create NODE_POOL_NAME-v131 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.X-gke.XXXX \
  --num-nodes NUM_NODES \
  --machine-type MACHINE_TYPE \
  --disk-size DISK_SIZE

# Cordon old pool to stop scheduling
kubectl cordon -l cloud.google.com/gke-nodepool=NODE_POOL_NAME

# Drain workloads (this may take time with PDBs)
kubectl drain -l cloud.google.com/gke-nodepool=NODE_POOL_NAME \
  --ignore-daemonsets --delete-emptydir-data --force

# Delete old pool once workloads migrated
gcloud container node-pools delete NODE_POOL_NAME \
  --cluster CLUSTER_NAME --zone ZONE
```

## Root Cause Prevention

This likely happened because:
- Node pool had auto-upgrades disabled (`--enable-autoupgrade=false`)
- Maintenance exclusions blocked upgrades for too long
- Cluster is on legacy "No channel" with poor upgrade controls

**Fix the root cause:**
```bash
# If on "No channel", migrate to a release channel
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular

# Use maintenance exclusions instead of disabled auto-upgrade
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "controlled-upgrades" \
  --add-maintenance-exclusion-start-time 2024-12-01T00:00:00Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Expected Timeline
- **Sequential upgrade:** 2-4 hours total (1-2 hours per step)
- **Pool replacement:** 1-2 hours (parallel provisioning + migration)

The sequential approach is safer for production workloads. The pool replacement is faster but requires sufficient quota and careful workload migration.

Which approach fits your situation better? And what's your current release channel configuration?