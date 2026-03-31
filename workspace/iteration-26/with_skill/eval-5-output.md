You're in a **version skew violation** — your node pool is 3 minor versions behind the control plane (1.28 vs 1.31), which exceeds GKE's maximum supported skew of 2 minor versions. This is blocking auto-upgrades and likely causing compatibility issues.

## What you're dealing with

**Immediate risks:**
- **Auto-upgrades are blocked** — GKE won't upgrade other components until this is resolved
- **API compatibility issues** — 1.28 kubelet may have problems with 1.31 API server features
- **Forced upgrade risk** — if 1.28 reaches End of Support, GKE will force-upgrade the node pool regardless of timing
- **Support limitations** — GKE support is limited for clusters in version skew violation

**Why this happened:**
- Node pool auto-upgrades were likely disabled or blocked by maintenance exclusions
- Control plane upgraded (automatically or manually) while nodes stayed frozen
- This accumulated over multiple release cycles

## Fix Strategy: Skip-Level Upgrade

Since you need to jump 3 minor versions (1.28→1.31), you'll need to do this in stages to stay within supported skew:

### Step 1: Skip-level upgrade 1.28→1.30
```bash
# First, upgrade to an intermediate version within supported skew
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --node-version 1.30.X-gke.XXX

# Monitor progress
watch 'kubectl get nodes -L cloud.google.com/gke-nodepool'
```

### Step 2: Skip-level upgrade 1.30→1.31 (final)
```bash
# Once 1.30 upgrade completes, upgrade to match control plane
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --node-version 1.31.X-gke.XXX
```

## Pre-flight Checklist

Before starting, verify:

```bash
# Check exact versions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check available versions for your upgrade path
gcloud container get-server-config --zone ZONE \
  --format="yaml(validNodeVersions)"

# Verify no deprecated API usage that would block upgrades
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```

## Upgrade Settings for Severely Skewed Pools

Given the age of your 1.28 nodes, use conservative settings:

```bash
# Configure conservative surge settings
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Why conservative:** Older nodes may have accumulated config drift, incompatible taints, or resource allocation issues that cause problems during drain.

## Alternative: Replace the Node Pool

If the skip-level upgrades fail or you want to minimize risk:

```bash
# Create new pool at target version
gcloud container node-pools create new-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --node-version 1.31.X-gke.XXX \
  --num-nodes NUM_NODES \
  --machine-type MACHINE_TYPE

# Cordon old pool
kubectl cordon -l cloud.google.com/gke-nodepool=OLD_POOL_NAME

# Drain workloads (this may take time)
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --grace-period=300

# Delete old pool once migration is complete
gcloud container node-pools delete OLD_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE
```

## Prevention Going Forward

To avoid this situation recurring:

1. **Remove any persistent maintenance exclusions** that disabled auto-upgrades:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion EXCLUSION_NAME
```

2. **Use release channels** instead of manual version pinning:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular
```

3. **Set maintenance windows** for predictable timing:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-01T02:00:00Z" \
  --maintenance-window-end "2024-01-01T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Expected Timeline

- **1.28→1.30 upgrade:** 30-60 minutes depending on pool size
- **1.30→1.31 upgrade:** 30-60 minutes
- **Total downtime:** Rolling upgrade means no cluster-wide outage, just individual pod restarts

The cluster will be functional between the two upgrades — 1.30 nodes with 1.31 control plane is within supported skew.

Start with the first skip-level upgrade (1.28→1.30) and verify everything works before proceeding to the final upgrade. This gives you a checkpoint if anything goes wrong.