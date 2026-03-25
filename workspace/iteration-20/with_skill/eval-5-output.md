You're dealing with **unsupported version skew** — your nodes are 3 minor versions behind the control plane (1.28 vs 1.31), which exceeds GKE's 2-minor-version skew limit. This is a serious issue that needs immediate attention.

## What you're dealing with

**Version skew violation:** GKE supports nodes up to 2 minor versions behind the control plane. Your setup:
- Control plane: 1.31 ✅
- Node pool: 1.28 ❌ (3 versions behind — unsupported)

**Risks:**
- **Workload instability** — API compatibility issues between 1.28 nodes and 1.31 control plane
- **Security vulnerabilities** — 1.28 is likely at or past End of Support
- **Support limitations** — GKE may not provide full support for unsupported skew
- **Forced upgrades** — GKE will eventually force-upgrade EoS node pools

## Immediate remediation plan

### Step 1: Assess current state
```bash
# Check exact versions and EoS status
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check if 1.28 is past End of Support
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

### Step 2: Plan the node pool upgrade path

You **cannot** do a single jump from 1.28→1.31 (exceeds N+2 skip-level limit). You need **two sequential skip-level upgrades**:

**Path A: Skip-level upgrades (recommended)**
1. 1.28 → 1.30 (N+2 skip-level)
2. 1.30 → 1.31 (N+1, brings nodes to CP version)

**Path B: Create new node pool (alternative)**
- Create new pool at 1.31
- Migrate workloads
- Delete old 1.28 pool

### Step 3: Pre-upgrade preparation

```bash
# Apply maintenance exclusion to prevent auto-upgrades during remediation
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "version-skew-fix" \
  --add-maintenance-exclusion-start $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end $(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades

# Check for deprecated APIs (common cause of upgrade failures)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Configure conservative surge settings for the upgrade
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### Step 4: Execute skip-level upgrades

```bash
# First upgrade: 1.28 → 1.30
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30.X-gke.XXXX

# Wait for completion, then verify
kubectl get nodes -o wide

# Second upgrade: 1.30 → 1.31
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.X-gke.XXXX
```

### Step 5: Alternative - New node pool approach

If skip-level upgrades fail or you prefer a blue-green approach:

```bash
# Create new node pool at 1.31
gcloud container node-pools create NODE_POOL_NAME-v131 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.X-gke.XXXX \
  --machine-type MACHINE_TYPE \
  --num-nodes NUM_NODES \
  --disk-size DISK_SIZE

# Cordon old pool
kubectl cordon -l cloud.google.com/gke-nodepool=NODE_POOL_NAME

# Drain workloads (respects PDBs)
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data

# Delete old pool after migration
gcloud container node-pools delete NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE
```

## Root cause analysis

How did this happen? Common causes:
- **Disabled auto-upgrades** on node pools while CP continued upgrading
- **Maintenance exclusions** applied too long
- **Manual version freezing** without considering CP progression
- **Legacy "No channel" cluster** with inconsistent upgrade policies

## Prevention going forward

```bash
# Remove maintenance exclusion after fixing
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "version-skew-fix"

# Ensure cluster is on a release channel for consistent upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular

# Set up monitoring for version skew
# Check GKE deprecation insights dashboard for warnings
```

## Expected timeline

- **Skip-level approach:** 2-4 hours per upgrade (depending on pool size)
- **New pool approach:** 1-2 hours for migration

## Immediate next steps

1. Run the assessment commands above to confirm versions and EoS status
2. Choose skip-level vs new pool approach based on your workload tolerance
3. Apply the maintenance exclusion to prevent further drift
4. Execute the chosen remediation path

This is a high-priority fix — version skew violations can cause unpredictable behavior and GKE may force-upgrade the node pool at any time if it's past EoS.