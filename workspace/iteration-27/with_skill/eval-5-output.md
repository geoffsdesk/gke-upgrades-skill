You're dealing with a **3 minor version skew** (1.31 control plane, 1.28 nodes), which **violates GKE's supported version skew policy**. GKE only supports nodes up to **2 minor versions** behind the control plane.

## What you're dealing with:

- **Unsupported configuration**: 1.31 CP → 1.28 nodes = 3 version gap (exceeds the 2-version limit)
- **Automatic enforcement**: GKE will force-upgrade the 1.28 node pool soon to restore supported skew
- **Potential issues**: API compatibility problems, security vulnerabilities, unpredictable behavior
- **No manual control**: You can't manually upgrade a node pool that's 3+ versions behind — GKE will do it automatically

## Immediate action required:

The 1.28 node pool will be **automatically upgraded by GKE** to restore supported version skew. This is systematic enforcement — you cannot avoid it. The upgrade will likely target 1.29 first (bringing it within the 2-version limit), then potentially continue to newer versions.

# Recovery Plan

## Phase 1: Prepare for forced upgrade (urgent)

```bash
# Check current state
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Configure upgrade strategy BEFORE GKE forces the upgrade
gcloud container node-pools update PROBLEMATIC_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

## Phase 2: Workload protection

```bash
# Check for workloads that might be disrupted
kubectl get pods -o wide | grep PROBLEMATIC_NODE_POOL

# Verify PDBs exist for critical workloads
kubectl get pdb -A

# If missing, create emergency PDBs:
kubectl create pdb WORKLOAD-pdb --selector=app=WORKLOAD --min-available=1
```

## Phase 3: Monitor the forced upgrade

```bash
# Watch for GKE upgrade operations
watch 'gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=3'

# Monitor node versions during upgrade
watch 'kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,POOL:.metadata.labels.cloud\.google\.com/gke-nodepool'
```

## Alternative approach: Replace the node pool

If you need more control over timing, **create a new node pool** and migrate workloads:

```bash
# Create replacement pool at supported version (1.29 minimum)
gcloud container node-pools create POOL_NAME-replacement \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.29 \
  --num-nodes NUM_NODES \
  --machine-type MACHINE_TYPE

# Cordon old pool
kubectl cordon -l cloud.google.com/gke-nodepool=OLD_POOL_NAME

# Drain workloads gradually
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --grace-period=300

# Delete old pool once empty
gcloud container node-pools delete OLD_POOL_NAME --cluster CLUSTER_NAME --zone ZONE
```

## How did this happen?

This typically occurs when:
- Control plane was upgraded (automatically or manually) multiple minor versions
- Node pool had auto-upgrade disabled or maintenance exclusions blocking upgrades
- The gap accumulated over months as the CP moved from 1.28 → 1.29 → 1.30 → 1.31

## Prevention for the future:

```bash
# Ensure auto-upgrades are enabled and use maintenance exclusions only when needed
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --enable-autoupgrade \
  --release-channel regular

# Set maintenance windows for predictable timing
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-01T02:00:00Z" \
  --maintenance-window-end "2024-01-01T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Key insight**: The 3-version skew is a **hard constraint violation**. GKE will enforce compliance automatically, so your best bet is to prepare for that upgrade or proactively replace the node pool with a compliant version. Don't try to fight the enforcement — work with it.