You have a **critical version skew violation** that requires immediate action. Your node pool is 3 minor versions behind the control plane (1.28 vs 1.31), which exceeds GKE's maximum supported skew of 2 minor versions.

## What you're dealing with

- **Unsupported configuration**: Nodes can't be more than 2 minor versions behind the control plane
- **Auto-upgrade enforcement**: GKE will force-upgrade this node pool soon, regardless of maintenance settings
- **Potential stability issues**: Some API calls from 1.28 nodes may fail or behave unexpectedly
- **Security debt**: The 1.28 node pool is missing ~18+ months of security patches

## Immediate action required

You need to upgrade the node pool to at least 1.29 to get back within supported skew. Here's your upgrade path:

### Option 1: Skip-level upgrades (recommended)
Use GKE's skip-level capability to minimize upgrade cycles:

```bash
# Check available versions in your zone
gcloud container get-server-config --zone YOUR_ZONE --format="yaml(validNodeVersions)"

# Upgrade 1.28 → 1.30 (skip 1.29, still within N+2 limit)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone YOUR_ZONE \
  --node-version 1.30.X-gke.XXXX

# Then 1.30 → 1.31 to match control plane
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone YOUR_ZONE \
  --node-version 1.31.X-gke.XXXX
```

### Option 2: Create new node pool (if upgrade fails)
If the existing pool won't upgrade cleanly:

```bash
# Create new pool at 1.31
gcloud container node-pools create new-pool \
  --cluster CLUSTER_NAME \
  --zone YOUR_ZONE \
  --node-version 1.31.X-gke.XXXX \
  --num-nodes NUM_NODES \
  --machine-type MACHINE_TYPE

# Cordon old pool
kubectl cordon -l cloud.google.com/gke-nodepool=OLD_POOL_NAME

# Drain workloads (may take time)
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --grace-period=300

# Delete old pool after migration
gcloud container node-pools delete OLD_POOL_NAME --cluster CLUSTER_NAME --zone YOUR_ZONE
```

## Before you start - critical checks

```bash
# 1. Check for deprecated APIs (major upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# 2. Verify PDBs aren't too restrictive
kubectl get pdb -A -o wide

# 3. Check cluster capacity for surge
kubectl top nodes
```

## Prevent this in the future

This happened because your cluster likely has:
- Disabled auto-upgrades (`--enable-autoupgrade=false` - deprecated)
- OR very restrictive maintenance exclusions
- OR is on legacy "No channel"

**Recommended fix:**
```bash
# Move to a release channel with controlled auto-upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --release-channel stable

# Set maintenance window for predictable timing
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --maintenance-window-start "2024-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SUN"

# Optional: Use "no minor or node upgrades" exclusion for max control while allowing security patches
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Timeline pressure

The 1.28 version likely reached End of Support months ago. GKE will force-upgrade this pool soon - you can't indefinitely defer with maintenance exclusions when version skew is this severe.

**Start immediately** - the longer you wait, the more deprecated APIs accumulate and the riskier the eventual upgrade becomes.

Would you like me to help you create a specific upgrade plan with your cluster details, or do you need guidance on checking for deprecated APIs before starting?