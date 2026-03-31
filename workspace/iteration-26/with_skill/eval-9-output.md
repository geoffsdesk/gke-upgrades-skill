# GKE Upgrade Optimization Plan for Large Standard Cluster

## Current Situation Analysis
- **600 nodes across 4 pools** → ~150 nodes per pool average
- **24+ hour upgrade duration** vs 8-hour maintenance window
- **GPU pools with fixed reservations** → no surge capacity available
- **Mixed CPU/GPU workloads** → different optimization strategies needed

## Speed Optimization Strategy

### 1. GPU Pool Optimization (Primary Bottleneck)

GPU pools are likely your primary bottleneck due to fixed reservation constraints:

**Current constraint:** `maxSurge=1` (default) with fixed reservations means only 1 node upgrades at a time
**Solution:** Increase `maxUnavailable` for faster parallel upgrades

```bash
# GPU pools: Use maxUnavailable as the primary lever (no surge capacity available)
gcloud container node-pools update GPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4

gcloud container node-pools update GPU_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4
```

**Impact calculation:**
- Before: 1 node at a time → ~150 batches per GPU pool
- After: 4 nodes at a time → ~38 batches per GPU pool
- **4x speed improvement** on GPU pools

**Workload consideration:** Only increase `maxUnavailable` if your GPU workloads can tolerate temporary capacity reduction. For inference workloads, consider **autoscaled blue-green** instead (see alternative below).

### 2. CPU Pool Optimization

CPU pools can use surge upgrades with higher parallelism:

```bash
# CPU pools: Use percentage-based maxSurge for scalable parallelism
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

**Calculation:** For 150-node pools, `maxSurge=8` = ~5% of pool size → ~19 batches instead of 150

### 3. Parallel Node Pool Upgrades

Upgrade CPU and GPU pools in parallel instead of sequentially:

```bash
# Launch all node pool upgrades simultaneously
gcloud container node-pools upgrade CPU_POOL_1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade CPU_POOL_2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade GPU_POOL_1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade GPU_POOL_2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &

# Monitor all upgrades
watch 'gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES" --format="table(name,operationType,status,progress)"'
```

## Alternative: Autoscaled Blue-Green for GPU Inference

If GPU pools serve inference workloads that can't tolerate capacity reduction:

```bash
# GPU inference pools: Use autoscaled blue-green to avoid capacity dips
gcloud container node-pools update GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes MIN \
  --total-max-nodes MAX \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

This creates replacement capacity before draining, avoiding inference downtime.

## Expected Timeline Improvement

**Before optimization:**
- Control plane: 15 minutes
- Node pools sequential: ~6 hours per pool × 4 pools = 24 hours
- **Total: ~24+ hours**

**After optimization:**
- Control plane: 15 minutes  
- All node pools parallel with optimized settings: ~2-4 hours
- **Total: ~3-5 hours** (fits in 8-hour window)

## Pre-Upgrade Checklist

```
Speed Optimization Checklist
- [ ] GPU reservation headroom verified (no additional capacity needed for maxUnavailable=0 approach)
- [ ] CPU surge quota confirmed for maxSurge=8 per pool
- [ ] PDBs reviewed — ensure they allow 4+ disruptions simultaneously
- [ ] GPU workloads can tolerate 4-node capacity reduction during upgrade
- [ ] Monitoring configured to track 4 parallel upgrade operations
- [ ] Rollback plan documented for parallel upgrades
```

## Monitoring Commands

```bash
# Track upgrade progress across all pools
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "(gpu-pool|cpu-pool)"'

# Monitor PDB violations during parallel upgrades
kubectl get events -A --field-selector reason=EvictionBlocked --watch

# Check resource pressure with higher parallelism
kubectl top nodes | head -20
```

## Risk Mitigation

1. **Test in staging first** with the same node pool sizes and surge settings
2. **Start with lower parallelism** (maxUnavailable=2 for GPU) and increase if successful
3. **Monitor PDB violations** — if too many pods are blocked, reduce parallelism
4. **GPU workload validation** — confirm models still load correctly after driver updates

This approach should reduce your upgrade window from 24+ hours to 3-5 hours, fitting comfortably within your 8-hour maintenance window.