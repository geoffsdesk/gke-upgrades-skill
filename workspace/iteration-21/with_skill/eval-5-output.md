# GKE Version Skew Recovery Plan

## What You're Dealing With

You have a **critical version skew violation**. Your node pool at 1.28 is **3 minor versions** behind your 1.31 control plane, which exceeds GKE's maximum supported skew of 2 minor versions. This creates several risks:

- **EoS enforcement imminent**: 1.28 reached End of Support and will be force-upgraded by GKE
- **API compatibility issues**: Some 1.31 control plane APIs may not work with 1.28 nodes
- **Security vulnerabilities**: 1.28 nodes are missing ~3 years of security patches
- **Support limitations**: This configuration is outside GKE's support matrix

## Immediate Assessment

First, let's understand your current state:

```bash
# Check all versions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check release channel and auto-upgrade status
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel)"

# Check for any maintenance exclusions blocking upgrades
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy)"

# Verify node pool is healthy (before we touch it)
kubectl get nodes -l cloud.google.com/gke-nodepool=NODE_POOL_NAME
```

## Recovery Options

### Option A: Skip-Level Upgrade (Recommended)

Since you're within the 3-version limit, you can use GKE's skip-level upgrade to jump directly from 1.28 → 1.30 or 1.28 → 1.31:

```bash
# Upgrade node pool directly to 1.31 (2-version skip)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.PATCH_VERSION

# Or safer: upgrade to 1.30 first, then 1.31
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30.PATCH_VERSION
```

**Skip-level constraints:**
- Must stay within 2 minor versions of control plane (1.28→1.30 ✓, 1.28→1.31 ✓)
- Cannot skip to unsupported versions
- Some workloads may need compatibility validation across the gap

### Option B: Create New Node Pool + Migration

If the skip-level upgrade seems too risky or you have workloads sensitive to the version jump:

```bash
# Create new node pool at current control plane version
gcloud container node-pools create NODE_POOL_NAME-new \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.PATCH_VERSION \
  --num-nodes NUM_NODES \
  --machine-type MACHINE_TYPE \
  --disk-size DISK_SIZE

# Cordon old node pool
kubectl cordon -l cloud.google.com/gke-nodepool=NODE_POOL_NAME

# Drain workloads (this will reschedule to new pool)
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --grace-period=300

# After all workloads migrate, delete old pool
gcloud container node-pools delete NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE
```

## Pre-Upgrade Checklist

Before proceeding with either option:

- [ ] **Remove any maintenance exclusions** that might be blocking auto-upgrades
- [ ] **Check for deprecated API usage**: `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated`
- [ ] **Verify PDBs won't block drain**: `kubectl get pdb -A -o wide` (look for ALLOWED DISRUPTIONS = 0)
- [ ] **No bare pods**: `kubectl get pods -A -o json | jq -r '.items[] | select(.metadata.ownerReferences | length == 0)'`
- [ ] **Backup stateful workloads** if any exist on the 1.28 node pool
- [ ] **Configure appropriate surge settings** for the upgrade:
  ```bash
  # Conservative settings for version-skewed pools
  gcloud container node-pools update NODE_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 1 \
    --max-unavailable-upgrade 0
  ```

## Recovery Runbook

### Step 1: Enable auto-upgrades and remove blocks

```bash
# Check if you're on "No channel" (common cause of this situation)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel)"

# If "No channel", migrate to Regular channel first
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular

# Remove any maintenance exclusions blocking upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --clear-maintenance-exclusions
```

### Step 2: Execute the upgrade

**If using skip-level (Option A):**
```bash
# Skip-level upgrade 1.28 → 1.30
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30.LATEST_PATCH

# Monitor progress
watch 'kubectl get nodes -o wide -l cloud.google.com/gke-nodepool=NODE_POOL_NAME'
```

**If creating new pool (Option B):**
Follow the commands in Option B above.

### Step 3: Validate

```bash
# Confirm all nodes at supported versions
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# Check workload health
kubectl get pods -A | grep -v Running | grep -v Completed

# Verify no version skew warnings
kubectl get events -A --field-selector reason=NodeSkew
```

## Prevention

To avoid this situation in the future:

1. **Stay on release channels** (not "No channel") with auto-upgrades enabled
2. **Use maintenance windows** to control timing, not maintenance exclusions to freeze versions
3. **Set up monitoring** for version skew:
   ```bash
   # Enable cluster notifications for EoS warnings
   gcloud container clusters update CLUSTER_NAME \
     --zone ZONE \
     --enable-network-policy \
     --notification-config=topic=projects/PROJECT_ID/topics/gke-cluster-upgrades
   ```
4. **Regular upgrade cadence**: Don't let node pools fall more than 1 minor version behind

## Troubleshooting

If the skip-level upgrade fails:
- **Check resource constraints**: `kubectl top nodes`
- **Look for stuck PDBs**: `kubectl get pdb -A -o wide`
- **Monitor upgrade progress**: `gcloud container operations list --cluster CLUSTER_NAME --zone ZONE`

The 1.28 → 1.30/1.31 jump crosses significant Kubernetes changes, so test critical workloads carefully after the upgrade completes.

**Critical warning**: Don't delay this fix. GKE will force-upgrade 1.28 nodes to the next supported version automatically once EoS enforcement kicks in, and that forced upgrade may be more disruptive than a planned one.