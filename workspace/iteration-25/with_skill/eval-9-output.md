# GKE Node Pool Upgrade Acceleration Plan

## Current State Analysis
- **600-node cluster with 4 node pools** (2 CPU, 2 GPU A100)
- **24+ hour upgrade duration** vs 8-hour maintenance window
- **GPU pools have fixed reservations** (no surge capacity available)

## Root Cause: GKE Upgrade Parallelism Limits
GKE upgrades ~20 nodes simultaneously regardless of `maxSurge` setting. For 600 nodes, this means ~30 batches minimum, explaining your 24+ hour duration.

## Acceleration Strategies

### 1. GPU Pool Strategy (Primary Bottleneck)
GPU pools with fixed reservations cannot use surge upgrades. **`maxUnavailable` is your only lever.**

```bash
# Current (likely): maxSurge=1, maxUnavailable=0 (sequential, very slow)
# Optimized for speed:
gcloud container node-pools update GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4
```

**Impact:** Instead of 1 GPU node at a time, drain 4 simultaneously. This reduces GPU pool upgrade time from ~8 hours to ~2 hours (assuming 100-node GPU pool).

**Trade-off:** Temporary 4-node capacity loss during each batch. Ensure your GPU workloads can tolerate this reduction.

### 2. CPU Pool Strategy
CPU pools likely have surge capacity available:

```bash
# Aggressive surge settings for CPU pools
gcloud container node-pools update CPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 10 \
  --max-unavailable-upgrade 0
```

**Impact:** Creates 10 surge nodes at a time instead of 1. For 200-node CPU pools, this reduces upgrade time from ~10 hours to ~2 hours.

### 3. Staggered Pool Upgrades
Upgrade pools in optimal sequence during your 8-hour window:

```bash
# Hour 0-2: Start with CPU pools (parallel)
gcloud container node-pools upgrade CPU_POOL_1 --cluster CLUSTER --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade CPU_POOL_2 --cluster CLUSTER --zone ZONE --cluster-version TARGET_VERSION &

# Hour 2-6: Start GPU pools after CPU completes
gcloud container node-pools upgrade GPU_POOL_1 --cluster CLUSTER --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade GPU_POOL_2 --cluster CLUSTER --zone ZONE --cluster-version TARGET_VERSION &
```

### 4. Pre-Upgrade Optimization

**Scale down non-critical workloads:**
```bash
# Free up nodes for faster drain
kubectl scale deployment NON_CRITICAL_APP --replicas=0
```

**Verify PDBs aren't overly restrictive:**
```bash
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0
```

**Check for bare pods:**
```bash
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

## Projected Timeline with Optimizations

| Pool Type | Current Duration | Optimized Duration | Strategy |
|-----------|------------------|-------------------|----------|
| CPU Pool 1 (200 nodes) | ~10 hours | ~2 hours | maxSurge=10 |
| CPU Pool 2 (200 nodes) | ~10 hours | ~2 hours | maxSurge=10 |
| GPU Pool 1 (100 nodes) | ~8 hours | ~2.5 hours | maxUnavailable=4 |
| GPU Pool 2 (100 nodes) | ~8 hours | ~2.5 hours | maxUnavailable=4 |
| **Total (sequential)** | **36 hours** | **9 hours** | |
| **Total (parallel)** | **24+ hours** | **~4-5 hours** | CPU parallel, then GPU parallel |

## Alternative: Blue-Green for GPU Pools (if budget allows)

If you can temporarily double GPU costs:

```bash
gcloud container node-pools update GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --strategy=BLUE_GREEN \
  --node-pool-soak-duration=3600s
```

**Benefit:** Faster than drain-first, zero capacity loss during upgrade
**Cost:** Doubles GPU costs during upgrade (2x A100 reservation)

## Monitoring Commands

```bash
# Track upgrade progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Monitor operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES"

# Check for stuck pods
kubectl get pods -A | grep -E "Terminating|Pending"
```

## Recommended Implementation

1. **Week 1:** Test the aggressive settings on a staging cluster first
2. **Week 2:** Apply to production during maintenance window:
   - Start CPU pools with maxSurge=10 (parallel)
   - Once CPU completes (~2 hours), start GPU pools with maxUnavailable=4 (parallel)
   - Total window: ~5-6 hours (fits in 8-hour window with buffer)

This should reduce your upgrade time from 24+ hours to under 6 hours, fitting within your weekend maintenance window.