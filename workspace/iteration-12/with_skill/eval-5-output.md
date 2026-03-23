You're in an **unsupported version skew** situation. GKE requires nodes to be within 2 minor versions of the control plane, and your 1.28 nodes are 3 versions behind your 1.31 control plane (1.28 → 1.29 → 1.30 → 1.31).

## What you're dealing with

- **Unsupported configuration**: 3-version skew violates GKE's compatibility matrix
- **Potential stability issues**: API mismatches, scheduler problems, networking issues
- **Security exposure**: 1.28 nodes missing 1+ years of security patches
- **Auto-upgrade blocked**: GKE won't auto-upgrade nodes that are >2 versions behind
- **Limited support**: Google support may be limited for this configuration

## Fix options (in order of preference)

### Option 1: Skip-level upgrade within supported skew (RECOMMENDED)

Upgrade the 1.28 pool directly to 1.30 (2-version jump, which GKE supports):

```bash
# Check what 1.30 versions are available
gcloud container get-server-config --zone YOUR_ZONE --format="yaml(channels)"

# Upgrade 1.28 → 1.30 directly (skip 1.29)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone YOUR_ZONE \
  --cluster-version 1.30.X-gke.XXXX

# Then upgrade 1.30 → 1.31 to match control plane
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone YOUR_ZONE \
  --cluster-version 1.31.X-gke.XXXX
```

### Option 2: Blue-green replacement (if Option 1 fails)

Create a new pool at 1.31 and migrate workloads:

```bash
# Create new node pool at 1.31
gcloud container node-pools create POOL_NAME-v131 \
  --cluster CLUSTER_NAME \
  --zone YOUR_ZONE \
  --cluster-version 1.31.X-gke.XXXX \
  --num-nodes NUM_NODES \
  --machine-type MACHINE_TYPE

# Cordon old pool to prevent new pods
kubectl cordon -l cloud.google.com/gke-nodepool=OLD_POOL_NAME

# Drain workloads (may take time)
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data

# Delete old pool once workloads migrated
gcloud container node-pools delete OLD_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone YOUR_ZONE
```

## Pre-upgrade checklist for your situation

Given the severe version skew, be extra careful:

```
- [ ] Backup critical workloads and data
- [ ] Test in staging first if possible
- [ ] Check for deprecated APIs (1.28→1.31 span includes major API changes)
- [ ] Review PDBs - may need to relax during upgrade
- [ ] Ensure adequate quota for surge/replacement nodes
- [ ] Plan for extended maintenance window (this will take longer than normal)
- [ ] Have rollback plan ready (blue-green approach gives you the safest rollback)
```

## Deprecated API check (CRITICAL)

The 1.28→1.31 jump spans significant API deprecations. Check immediately:

```bash
# Check for deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Check GKE insights for deprecation warnings
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=YOUR_LOCATION \
    --project=YOUR_PROJECT_ID
```

## Why this happened

Common causes:
- Node pool auto-upgrade was disabled
- Maintenance exclusions blocked upgrades for too long
- Manual version pinning without a upgrade plan
- Cluster on legacy "No channel" with per-nodepool settings

## Prevention for the future

1. **Use release channels** with maintenance windows instead of manual version management
2. **Set up maintenance exclusions properly** - use "no minor or node upgrades" scope rather than disabling auto-upgrade entirely  
3. **Monitor version skew** - set up alerts for nodes >1 version behind control plane
4. **Regular upgrade cadence** - don't let nodes fall more than 1 minor version behind

**Immediate action**: I'd recommend Option 1 (skip-level upgrade 1.28→1.30→1.31) as it's faster and uses GKE's supported upgrade path. Only fall back to Option 2 if the direct upgrade fails due to deprecated APIs or other compatibility issues.

Would you like me to produce a detailed runbook for either approach, or do you need help with the deprecated API analysis first?