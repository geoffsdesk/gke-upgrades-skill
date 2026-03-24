# GKE Large Cluster Upgrade Optimization Plan

## Current Bottleneck Analysis

Your 24+ hour upgrade time with 600 nodes is likely caused by:
- **GKE's maximum upgrade parallelism**: ~20 nodes simultaneously regardless of `maxSurge` setting
- **Conservative default settings**: Low `maxSurge`/`maxUnavailable` values
- **Sequential node pool upgrades**: GKE upgrades pools one at a time by default
- **GPU pool constraints**: Fixed A100 reservations likely have no surge capacity

**Time calculation**: 600 nodes ÷ 20 parallel = 30 batches minimum. At ~15-20 minutes per batch, this explains your 24+ hour timeline.

## Optimization Strategy

### 1. GPU Pools - Increase maxUnavailable (Primary Lever)

For your A100 pools with fixed reservations, `maxUnavailable` is the **only effective parameter**:

```bash
# Configure GPU pools for faster drain-first upgrades
gcloud container node-pools update GPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4

gcloud container node-pools update GPU_POOL_2 \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4
```

**Rationale**: 
- `maxSurge=0` because A100 reservations typically have no surge capacity
- `maxUnavailable=4` allows 4 nodes to drain simultaneously instead of 1
- **Risk**: Temporary capacity reduction during upgrade batches
- **Benefit**: 4x faster GPU pool upgrades

### 2. CPU Pools - Optimize Surge Settings

For CPU pools, use percentage-based surge with higher parallelism:

```bash
# Configure CPU pools for surge upgrades
gcloud container node-pools update CPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 10 \
  --max-unavailable-upgrade 0

gcloud container node-pools update CPU_POOL_2 \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 10 \
  --max-unavailable-upgrade 0
```

**Calculation**: If each CPU pool has ~150 nodes, `maxSurge=10` = ~7% of pool size. This is aggressive but stays within the ~20 node batch limit.

### 3. Enable Node Pool Upgrade Concurrency (Preview)

**Critical optimization**: Enable concurrent node pool upgrades instead of sequential:

```bash
# Enable concurrent node pool upgrades (available April 2026)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --enable-concurrent-node-pool-upgrades
```

This allows multiple node pools to upgrade simultaneously, potentially cutting your total time by 75% (4 pools → 1 pool worth of time).

### 4. Workload-Specific Optimizations

**Long-running GPU workloads** (training jobs):
- Apply maintenance exclusion to GPU pools during active training
- Schedule upgrades between training campaigns
- Use checkpointing to allow job resumption after upgrade

```bash
# Block GPU pool upgrades during training campaigns
gcloud container node-pools update GPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "training-campaign" \
  --add-maintenance-exclusion-start-time "2024-XX-XXTXX:XX:XXZ" \
  --add-maintenance-exclusion-end-time "2024-XX-XXTXX:XX:XXZ" \
  --add-maintenance-exclusion-scope "no_minor_or_node_upgrades"
```

**PDB Review** for CPU workloads:
```bash
# Check for overly restrictive PDBs
kubectl get pdb -A -o custom-columns="NAMESPACE:.metadata.namespace,NAME:.metadata.name,MIN_AVAILABLE:.spec.minAvailable,MAX_UNAVAILABLE:.spec.maxUnavailable"
```

Temporarily relax PDBs during upgrade window if they're blocking drain.

### 5. Upgrade Sequencing Strategy

**Recommended order**:
1. **CPU pools first** (lower risk, faster validation)
2. **GPU pools during training gaps** (higher impact, needs coordination)

**Manual trigger for controlled timing**:
```bash
# Trigger all pools simultaneously (if concurrent upgrades enabled)
gcloud container node-pools upgrade CPU_POOL_1 --cluster CLUSTER_NAME --region REGION --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade CPU_POOL_2 --cluster CLUSTER_NAME --region REGION --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade GPU_POOL_1 --cluster CLUSTER_NAME --region REGION --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade GPU_POOL_2 --cluster CLUSTER_NAME --region REGION --cluster-version TARGET_VERSION &
```

## Expected Time Improvement

**Before optimization**: 24+ hours
**After optimization**: 6-8 hours

**Breakdown**:
- Concurrent node pool upgrades: 4x faster (24h → 6h)
- Higher maxUnavailable on GPU pools: Additional 2x improvement on GPU portions
- Optimized surge settings on CPU pools: Marginal improvement within batch limits

## Alternative: Staggered Maintenance Windows

If the preview features aren't available, consider splitting across multiple weekends:

**Weekend 1**: CPU pools only (lower risk)
**Weekend 2**: GPU pools only (coordinate with ML team)

```bash
# CPU-only upgrade weekend
gcloud container node-pools upgrade CPU_POOL_1 --cluster CLUSTER_NAME --region REGION --cluster-version TARGET_VERSION
gcloud container node-pools upgrade CPU_POOL_2 --cluster CLUSTER_NAME --region REGION --cluster-version TARGET_VERSION
```

## Monitoring During Upgrade

Track progress with:
```bash
# Monitor node versions across pools
watch 'kubectl get nodes -L cloud.google.com/gke-nodepool -o custom-columns="NAME:.metadata.name,POOL:.metadata.labels.cloud\.google\.com/gke-nodepool,VERSION:.status.nodeInfo.kubeletVersion,STATUS:.status.conditions[3].type"'

# Check GPU workload impact
kubectl get pods -A -l accelerator=nvidia-tesla-a100 -o wide
```

## Risk Mitigation

- **Test in staging first** with the same node pool configuration
- **Coordinate with ML teams** on GPU pool upgrade timing
- **Monitor A100 reservation utilization** before starting GPU upgrades
- **Have rollback plan ready** (manual blue-green with new pools if needed)

This optimization should bring your upgrade time within your 8-hour weekend window while minimizing workload disruption.