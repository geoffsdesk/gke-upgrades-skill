You have a critical **version skew violation**. Your node pool is 3 minor versions behind the control plane (1.28 vs 1.31), but GKE only supports a 2-minor-version maximum skew. This configuration is unsupported and can cause API compatibility issues, scheduling problems, and unpredictable behavior.

## What you're dealing with

- **Immediate risk**: API incompatibilities between 1.28 nodes and 1.31 control plane
- **Blocking issue**: You cannot upgrade the control plane further until node pools catch up
- **Support limitation**: This configuration is outside GKE's support matrix

## Fix Strategy

You'll need to upgrade the node pool through the intermediate versions. Here's your upgrade path:

**Node Pool Upgrade Sequence**: 1.28 → 1.29 → 1.30 → 1.31

---

# Node Pool Recovery Runbook

## Pre-flight checks

```bash
# Confirm current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check which versions are available
gcloud container get-server-config --zone ZONE \
  --format="yaml(validNodeVersions)" | head -20

# Verify cluster health
kubectl get nodes
kubectl get pods -A | grep -E "Pending|CrashLoop|Error"
```

## Step 1: Prepare for upgrade

```bash
# Configure conservative surge settings (adjust based on your capacity)
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Check PDBs that might block drain
kubectl get pdb -A -o wide
```

## Step 2: Sequential node pool upgrades

**Upgrade 1.28 → 1.29:**
```bash
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.29.9-gke.1273000

# Monitor progress (~15-30 min depending on pool size)
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

**Wait for completion, then 1.29 → 1.30:**
```bash
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30.6-gke.1125000

# Monitor again
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

**Finally 1.30 → 1.31:**
```bash
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.2-gke.1372000

# Final monitoring
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

## Step 3: Validation

```bash
# Confirm version alignment
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed

# Verify no version skew warnings
gcloud container clusters describe CLUSTER_NAME --zone ZONE | grep -i warning
```

## Alternative: Blue-green approach (if you have capacity)

If you need faster resolution and have sufficient quota:

```bash
# Create new node pool at 1.31
gcloud container node-pools create NODE_POOL_NAME-131 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.2-gke.1372000 \
  --num-nodes NUM_NODES \
  --machine-type MACHINE_TYPE

# Cordon old pool
kubectl cordon -l cloud.google.com/gke-nodepool=NODE_POOL_NAME

# Wait for workloads to migrate, then delete old pool
gcloud container node-pools delete NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE
```

## Important notes

- **Use specific patch versions** from the available list rather than just minor versions
- **Each upgrade takes time** - budget 20-45 minutes per step depending on pool size
- **Monitor for stuck pods** during each upgrade - PDBs or resource constraints can block progress
- **Don't skip versions** - go through each minor version sequentially for node pools

## Prevention

To avoid this situation in the future:
- Enable auto-upgrades on node pools OR
- Set up maintenance exclusions to control timing while keeping auto-upgrades enabled
- Monitor version skew warnings in the GKE console
- Consider migrating to a release channel for automated lifecycle management

The sequential upgrade will take 1-3 hours total depending on your node pool size, but this will get you back to a supported configuration.