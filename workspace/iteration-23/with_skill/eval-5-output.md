You're dealing with a **version skew violation** - your node pool is 3 minor versions behind the control plane (1.28 vs 1.31), which exceeds GKE's 2-minor-version limit. This is likely blocking auto-upgrades and could cause compatibility issues.

## What you're dealing with

- **Hard constraint violation**: Nodes can't be more than 2 minor versions behind the control plane
- **Auto-upgrade pause**: GKE automatically pauses upgrades when version skew limits are exceeded
- **Potential instability**: API compatibility issues between 1.28 nodes and 1.31 control plane
- **EoS risk**: 1.28 reached End of Support, so you're missing security patches

## Recovery Plan

### Option 1: Sequential skip-level upgrades (Recommended)

Since you can't jump directly from 1.28 → 1.31 (3 versions), do multiple skip-level upgrades within the 2-version limit:

```bash
# Step 1: Upgrade 1.28 → 1.30 (2-version skip, within limit)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30.X-gke.XXXX

# Verify nodes reach 1.30
kubectl get nodes -o wide

# Step 2: Upgrade 1.30 → 1.31 (1-version jump)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.X-gke.XXXX
```

Use conservative surge settings given the large version gap:
```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### Option 2: Replace the node pool (Faster for large gaps)

Create a new pool at 1.31 and migrate workloads:

```bash
# Create new pool at current CP version
gcloud container node-pools create NODE_POOL_NAME-v131 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.X-gke.XXXX \
  --machine-type MACHINE_TYPE \
  --num-nodes NUM_NODES

# Cordon old pool
kubectl cordon -l cloud.google.com/gke-nodepool=NODE_POOL_NAME

# Drain old pool
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data

# Delete old pool once workloads migrate
gcloud container node-pools delete NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE
```

## Pre-flight safety checks

Before starting either approach:

```bash
# Check for deprecated APIs (major concern across 3 versions)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Check GKE deprecation insights
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=ZONE \
  --project=PROJECT_ID

# Verify no bare pods
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Set up PDBs if missing (crossing 3 versions is risky)
kubectl get pdb -A
```

## High-risk items when jumping 1.28 → 1.31

- **API removals**: Several APIs deprecated in 1.28 may be removed by 1.31
- **Container runtime changes**: CRI/containerd behavior changes
- **Network policy changes**: CNI and NetworkPolicy API evolution
- **Admission webhook compatibility**: Many webhooks break across major gaps

**Strongly recommend**: Test the target version (1.31) in a staging cluster with your workloads before upgrading production.

## Prevention for the future

```bash
# Set up maintenance exclusions to control timing without creating version drift
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Configure maintenance windows for predictable timing
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

The key lesson: **Use maintenance exclusions and windows to control WHEN upgrades happen, not to freeze versions indefinitely**. Version skew compounds upgrade difficulty exponentially.

Would you like me to create a detailed runbook for your specific node pool once you choose Option 1 or 2?