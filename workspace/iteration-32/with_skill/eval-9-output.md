# GKE Node Pool Upgrade Acceleration Plan

## Current Bottlenecks Analysis

Your 24+ hour upgrade time is likely caused by:
- **GKE's ~20 node concurrent upgrade limit** regardless of maxSurge settings
- **Conservative default surge settings** (maxSurge=1, maxUnavailable=0)
- **Sequential node pool upgrades** (one pool at a time by default)
- **GPU pools with no surge capacity** using inefficient maxSurge settings

## Acceleration Strategy

### 1. Optimize Surge Settings by Pool Type

**CPU Pools (assuming stateless workloads):**
```bash
# Calculate 5% of pool size as maxSurge (minimum 1)
# For 150-node pool: maxSurge=8
gcloud container node-pools update CPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 8 \
  --max-unavailable-upgrade 0

gcloud container node-pools update CPU_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 8 \
  --max-unavailable-upgrade 0
```

**GPU Pools (fixed reservations - no surge capacity):**
```bash
# Use maxUnavailable as the primary lever (surge=0)
# Start conservative, can increase if workloads tolerate capacity dips
gcloud container node-pools update GPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2

gcloud container node-pools update GPU_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2
```

### 2. Parallel Node Pool Upgrades

Trigger multiple pools simultaneously instead of waiting for sequential completion:

```bash
# Start control plane upgrade first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# Once CP upgrade completes, trigger all pools in parallel
# (Launch these commands simultaneously in separate terminals)
gcloud container node-pools upgrade CPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION &

gcloud container node-pools upgrade CPU_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION &

gcloud container node-pools upgrade GPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION &

gcloud container node-pools upgrade GPU_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION &
```

### 3. Pre-Upgrade Resource Optimization

**Scale down non-critical workloads during the upgrade window:**
```bash
# Temporarily scale down dev/test workloads to free quota for surge
kubectl scale deployment DEV_WORKLOAD --replicas=0 -n NAMESPACE
kubectl scale deployment STAGING_WORKLOAD --replicas=0 -n NAMESPACE
```

**Pause cluster autoscaler to prevent interference:**
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --no-enable-autoscaling
```
Re-enable after upgrades complete.

### 4. Advanced GPU Pool Strategy

For GPU pools, consider **autoscaled blue-green** if you have capacity for replacement nodes:

```bash
gcloud container node-pools update GPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 0 --total-max-nodes CURRENT_SIZE \
  --strategy AUTOSCALED_BLUE_GREEN \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

This cordons the old pool and auto-scales replacement nodes, avoiding inference downtime.

## Expected Time Reduction

**Before optimization:**
- 600 nodes ÷ 20 concurrent = 30 batches minimum
- Sequential pools = 4x multiplier
- **Total: 24+ hours**

**After optimization:**
- CPU pools: 300 nodes with maxSurge=8 each = ~19 batches per pool
- GPU pools: 300 nodes with maxUnavailable=2 each = ~75 batches per pool  
- **Parallel execution = ~6-8 hours total**

## Monitoring Progress

```bash
# Monitor all pools simultaneously
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "NODE|CPU_POOL|GPU_POOL"'

# Track operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES"
```

## Rollback Plan

If upgrades fail mid-process:
1. **CPU pools:** Cancel operation, pools will be in mixed-version state (functional)
2. **GPU pools:** May need to drain remaining old nodes manually if mixed-version causes issues
3. **Emergency:** Create new pools at old version and migrate critical workloads

## Maintenance Window Strategy

With these optimizations, you should complete within your 8-hour weekend window. For additional safety:

```bash
# Set maintenance window to prevent auto-upgrades during business hours
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "YYYY-MM-DDTHH:MM:SSZ" \
  --maintenance-window-duration 8h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Pre-Upgrade Checklist

```
Large Cluster Upgrade Checklist
- [ ] Control plane upgraded first (prerequisite for node pools)
- [ ] PDBs reviewed - not overly restrictive for 600-node cluster
- [ ] Non-critical workloads scaled down to free quota
- [ ] Cluster autoscaler paused
- [ ] GPU driver compatibility verified with target GKE version
- [ ] Surge settings optimized per pool type
- [ ] Parallel upgrade commands prepared
- [ ] Monitoring dashboards ready
- [ ] On-call team available for 8-hour window
```

This strategy should bring your upgrade time from 24+ hours down to 6-8 hours, fitting within your weekend maintenance window.