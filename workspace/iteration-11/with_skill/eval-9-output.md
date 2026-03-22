# GKE Upgrade Optimization Plan for Large Standard Cluster

## Current Situation Analysis
- **Cluster:** 600 nodes, 4 node pools (2 CPU + 2 A100 GPU pools)
- **Problem:** 24+ hour upgrades don't fit in 8-hour weekend maintenance window
- **Constraint:** A100 pools have fixed reservations (likely no surge capacity)

## Speed Optimization Strategy

### 1. GPU Pool Upgrades (Primary Bottleneck)

GPU pools are your main constraint due to fixed reservations and no live migration support.

**Recommended approach for A100 pools:**
```bash
# Configure for fastest possible GPU upgrade
gcloud container node-pools update GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 3
```

**Why this works:**
- `maxSurge=0` — no extra GPUs needed (respects reservation limits)
- `maxUnavailable=3` — drains 3 nodes simultaneously instead of 1
- For 150-node GPU pool: ~50 batches instead of 150 sequential upgrades

**Alternative if training jobs allow:** Use GKE's **autoscaled blue-green upgrade** for GPU pools:
```bash
gcloud container node-pools update GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaled-blue-green-upgrade \
  --blue-green-upgrade-policy-node-pool-soak-duration=300s
```
This cordons the entire pool and auto-scales replacements based on workload demand — ideal for GPU workloads that can't use surge capacity.

### 2. CPU Pool Upgrades (Maximize Parallelism)

CPU pools typically have more quota flexibility. Dramatically increase surge settings:

```bash
# For stateless CPU pools
gcloud container node-pools update CPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 20 \
  --max-unavailable-upgrade 0
```

**Impact:** Instead of default 1-node-at-a-time, you upgrade 20 nodes simultaneously. For 225-node CPU pool: ~12 batches instead of 225.

**Note:** GKE's maximum upgrade parallelism is ~20 nodes regardless of `maxSurge` setting, so `maxSurge=20` is the practical ceiling.

### 3. Skip-Level Node Pool Upgrades

Use skip-level (N+2) upgrades to reduce total upgrade cycles:

```bash
# Instead of 1.28→1.29→1.30, go directly 1.28→1.30
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30.x-gke.xxxx
```

**Time savings:** 50% fewer upgrade cycles. Node pools support skip-level; control plane requires sequential minor versions.

### 4. Staggered Pool Upgrades

Don't upgrade all pools simultaneously. Sequence them strategically:

```bash
# Week 1: Upgrade control plane + CPU pools only
gcloud container clusters upgrade CLUSTER_NAME --master --cluster-version TARGET_VERSION
# After CP upgrade completes:
gcloud container node-pools upgrade CPU_POOL_1 --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade CPU_POOL_2 --cluster-version TARGET_VERSION &

# Week 2: Upgrade GPU pools during training gap
gcloud container node-pools upgrade GPU_POOL_1 --cluster-version TARGET_VERSION
gcloud container node-pools upgrade GPU_POOL_2 --cluster-version TARGET_VERSION
```

### 5. Pre-upgrade Workload Preparation

**For GPU pools with training workloads:**
```bash
# Cordon GPU nodes and wait for jobs to complete naturally
kubectl cordon -l cloud.google.com/gke-nodepool=GPU_POOL_NAME
# Monitor until no active training pods
kubectl get pods -A --field-selector spec.nodeName=GPU_NODE_NAME

# Then upgrade the empty pool
gcloud container node-pools upgrade GPU_POOL_NAME --cluster-version TARGET_VERSION
```

## Realistic Timeline Projection

**With optimizations:**
- **CPU pools:** ~2-3 hours each (with maxSurge=20)
- **GPU pools:** ~4-6 hours each (with maxUnavailable=3)
- **Total per weekend:** Can fit 1-2 pools in 8-hour window

**Recommended schedule:**
- **Weekend 1:** Control plane + CPU pool 1
- **Weekend 2:** CPU pool 2 + GPU pool 1  
- **Weekend 3:** GPU pool 2

## Alternative: Extended Maintenance Window

Consider requesting longer maintenance windows for upgrades:
- **12-hour window:** Could fit CPU pools + 1 GPU pool
- **Overnight Friday-Saturday:** More realistic for large cluster maintenance

## Pre-Flight Configuration Commands

```bash
# Check current surge settings
gcloud container node-pools describe POOL_NAME --cluster CLUSTER_NAME --zone ZONE \
  --format="value(upgradeSettings.maxSurge,upgradeSettings.maxUnavailable)"

# Verify quota for surge nodes (CPU pools only)
gcloud compute project-info describe --format="yaml(quotas)" | grep -A2 "metric: CPUS"

# Check A100 reservation utilization
gcloud compute reservations describe RESERVATION_NAME --zone ZONE
```

## Maintenance Exclusion Strategy

Use "no minor or node upgrades" exclusions to control timing precisely:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign" \
  --add-maintenance-exclusion-start-time 2024-02-01T00:00:00Z \
  --add-maintenance-exclusion-end-time 2024-02-15T00:00:00Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

This blocks auto-upgrades during training campaigns while still allowing control plane security patches.

## Expected Results

**Before optimization:** 24+ hours
**After optimization:** 6-8 hours per major pool group

This should allow you to fit upgrades within weekend maintenance windows using a staggered approach across multiple weekends.