# GKE Large Cluster Upgrade Optimization Plan

**Cluster:** 600 nodes (2 CPU pools, 2 GPU pools with A100 fixed reservations)  
**Current issue:** 24+ hour upgrades vs 8-hour maintenance window  
**Target:** Fit upgrades within 8-hour weekend window

## Root Cause Analysis

Your upgrade duration is driven by:
1. **GKE's maximum parallelism:** ~20 nodes simultaneously regardless of `maxSurge` setting
2. **Fixed GPU reservations:** No surge capacity available for A100 pools
3. **Sequential node pool processing:** Pools upgrade one after another by default

## Optimization Strategy

### 1. GPU Pool Configuration (Critical)

**Current assumption:** Your GPU pools likely use default `maxSurge=1, maxUnavailable=0`

**Recommended change:** Switch to drain-first mode since you have no surge GPU capacity:
```bash
# For each GPU node pool
gcloud container node-pools update GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2
```

**Impact calculation:**
- 100-node GPU pool at `maxUnavailable=2` with 20-node parallelism = ~5 cycles
- Each cycle ~15-20 minutes = ~2 hours per GPU pool vs current 5+ hours

### 2. CPU Pool Surge Optimization

**Calculate optimal maxSurge per pool:**
```bash
# For 250-node CPU pool: 5% = 12 nodes (capped at parallelism limit of 20)
gcloud container node-pools update CPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 12 \
  --max-unavailable-upgrade 0
```

### 3. Parallel Node Pool Upgrades (April 2026 Preview)

**New feature:** GKE is adding node pool upgrade concurrency for auto-upgrades. Multiple pools can upgrade simultaneously instead of sequentially.

**Immediate workaround:** Manually trigger parallel upgrades:
```bash
# Start all pools simultaneously (run in parallel terminals/scripts)
gcloud container node-pools upgrade CPU_POOL_1 --cluster CLUSTER --zone ZONE --cluster-version TARGET &
gcloud container node-pools upgrade CPU_POOL_2 --cluster CLUSTER --zone ZONE --cluster-version TARGET &
gcloud container node-pools upgrade GPU_POOL_1 --cluster CLUSTER --zone ZONE --cluster-version TARGET &
gcloud container node-pools upgrade GPU_POOL_2 --cluster CLUSTER --zone ZONE --cluster-version TARGET &
```

### 4. Resource Optimization

**Scale down non-critical workloads** before upgrade to free quota for surge:
```bash
# Scale down dev/test workloads temporarily
kubectl scale deployment NON_CRITICAL_APP --replicas=0
```

**Schedule upgrades during absolute off-peak** to maximize available quota.

## Projected Timeline Improvement

| Component | Current (hours) | Optimized (hours) |
|-----------|----------------|-------------------|
| CPU pools (sequential) | 10-12 | 3-4 (parallel + optimal surge) |
| GPU pools (sequential) | 12-14 | 4-5 (parallel + maxUnavailable=2) |
| **Total** | **24+** | **6-7** ✅ |

## Implementation Runbook

### Pre-upgrade (Friday evening)

```bash
# 1. Scale down non-critical workloads
kubectl get deployments -A | grep -E "(dev|test|canary)"
kubectl scale deployment NON_CRITICAL_APP --replicas=0

# 2. Configure optimal surge settings
# CPU pools
gcloud container node-pools update CPU_POOL_1 \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 12 --max-unavailable-upgrade 0

gcloud container node-pools update CPU_POOL_2 \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 12 --max-unavailable-upgrade 0

# GPU pools (drain-first since no surge capacity)
gcloud container node-pools update GPU_POOL_1 \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 0 --max-unavailable-upgrade 2

gcloud container node-pools update GPU_POOL_2 \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 0 --max-unavailable-upgrade 2

# 3. Verify PDBs aren't overly restrictive
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0
```

### Upgrade execution (Saturday morning)

```bash
# 1. Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# 2. Wait for CP upgrade completion (~10-15 min)
# Then start all node pools in parallel
gcloud container node-pools upgrade CPU_POOL_1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade CPU_POOL_2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade GPU_POOL_1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade GPU_POOL_2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &

# 3. Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "(Ready|NotReady|SchedulingDisabled)"'
```

### Monitoring commands

```bash
# Check upgrade operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES"

# Node status by pool
kubectl get nodes -L cloud.google.com/gke-nodepool -L cloud.google.com/gke-version

# Any stuck pods
kubectl get pods -A | grep -E "Terminating|Pending"
```

## Risk Mitigation

**GPU workload impact:** With `maxUnavailable=2`, you'll have temporary capacity reduction during drain. Ensure:
- Training jobs can checkpoint and resume
- Inference workloads have adequate replicas to handle 2-node loss
- Monitor for capacity-related pod scheduling failures

**Rollback plan:** If parallel upgrades cause issues, you can cancel in-progress operations:
```bash
# GKE will finish current nodes and stop
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE
# No need to specify operation ID - cancellation affects ongoing upgrades
```

## Alternative: Blue-Green for GPU Pools

If your A100 reservation has ANY headroom, consider blue-green for GPU pools:
```bash
# Check reservation capacity first
gcloud compute reservations describe RESERVATION_NAME --zone ZONE

# If capacity available, use autoscaled blue-green (cost-efficient)
gcloud container node-pools update GPU_POOL_NAME \
  --cluster CLUSTER_NAME --zone ZONE \
  --enable-autoscaling \
  --strategy=AUTOSCALED_BLUE_GREEN \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25
```

This would be faster than drain-first but requires 25-50% extra GPU capacity during upgrade.

## Next Steps

1. **Test surge settings** on a staging cluster with similar topology
2. **Implement parallel node pool upgrades** for your next maintenance window
3. **Consider Extended release channel** if you need more predictable upgrade timing
4. **Monitor GKE roadmap** for node pool upgrade concurrency GA (April 2026)

This optimization should get you from 24+ hours to 6-7 hours, comfortably within your 8-hour weekend window.