# Large-Scale GKE Upgrade Strategy (3,000 nodes, 8 pools)

Your scale requires a fundamentally different approach than standard upgrade practices. With GKE's current ~20 node upgrade parallelism limit, a single 3,000-node pool would take **150+ batches minimum**, far exceeding an 8-hour window.

## Root cause analysis

**Why upgrades are timing out:**
- GKE upgrades node pools **sequentially** (one pool at a time by default)
- Within each pool: ~20 nodes maximum parallelism regardless of `maxSurge` setting
- 8 pools × sequential processing = potentially 40+ hours total upgrade time
- GPU pools are especially slow due to lack of surge capacity (fixed reservations)

## Strategy: Multi-window phased approach

Break the upgrade into **3 phases across 3 weekends** to fit your Saturday 2am-10am window:

### Phase 1: CPU pools (Weekend 1)
**Target:** 4 CPU pools during first maintenance window
```bash
# Prioritize CPU pools - they have surge capacity and upgrade faster
# Upgrade pools with highest maxSurge first (fastest completion)

# Example for CPU pools with good surge capacity:
gcloud container node-pools update cpu-pool-1 \
  --cluster CLUSTER_NAME \
  --max-surge-upgrade 10 \
  --max-unavailable-upgrade 0

# Trigger upgrades for all CPU pools simultaneously:
gcloud container node-pools upgrade cpu-pool-1 --cluster CLUSTER_NAME --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade cpu-pool-2 --cluster CLUSTER_NAME --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade cpu-pool-3 --cluster CLUSTER_NAME --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade cpu-pool-4 --cluster CLUSTER_NAME --cluster-version TARGET_VERSION &
```

### Phase 2: Smaller GPU pools (Weekend 2)
**Target:** T4 and L4 pools (typically smaller, less critical)
```bash
# GPU pools: maxUnavailable is the primary lever (assume no surge capacity)
gcloud container node-pools update t4-pool \
  --cluster CLUSTER_NAME \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2

gcloud container node-pools update l4-pool \
  --cluster CLUSTER_NAME \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2
```

### Phase 3: Premium GPU pools (Weekend 3)
**Target:** A100 and H100 pools (highest value, most risk)
```bash
# Conservative settings for premium GPUs
gcloud container node-pools update a100-pool \
  --cluster CLUSTER_NAME \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

gcloud container node-pools update h100-pool \
  --cluster CLUSTER_NAME \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

## Per-phase execution checklist

**Before each phase:**
- [ ] Apply "no upgrades" maintenance exclusion to non-target pools
- [ ] Verify adequate quota for CPU pool surge nodes (Phase 1 only)
- [ ] Checkpoint/pause long-running training jobs on GPU pools (Phases 2-3)
- [ ] Scale down non-critical workloads to free capacity

**During each window:**
- [ ] Start control plane upgrade first (15 minutes, do this in Phase 1)
- [ ] Launch node pool upgrades in parallel (using `&` backgrounding)
- [ ] Monitor progress: `watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'`
- [ ] If approaching window end: let current batches complete, then pause

**Exclusion management between phases:**
```bash
# After Phase 1, protect completed CPU pools from auto-upgrade:
gcloud container clusters update CLUSTER_NAME \
  --add-maintenance-exclusion-name "phase-1-complete" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+14 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades

# Remove exclusion before Phase 2 to allow GPU pool upgrades
```

## Scale-specific optimizations

### 1. Maximize parallelism within constraints
```bash
# CPU pools: Use percentage-based maxSurge (5% minimum)
# For 800-node CPU pool: maxSurge=40, but GKE caps at ~20 concurrent
# Still faster than maxSurge=1

# GPU pools: Increase maxUnavailable where workloads allow
# For 400-node A100 pool: maxUnavailable=2-4 if training can checkpoint
```

### 2. Leverage skip-level node upgrades
```bash
# If control plane goes 1.29→1.30→1.31, do node pools 1.29→1.31 directly
# Reduces total cycles: instead of 2 upgrades, do 1 skip-level upgrade
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --cluster-version 1.31.X  # Skip from 1.29 directly to 1.31
```

### 3. Training workload coordination
**GPU pool upgrade timing:**
- Schedule Phase 2/3 during natural training gaps (model checkpoints, experiment transitions)
- Use `--add-maintenance-exclusion-scope no_minor_or_node_upgrades` on GPU pools during active campaigns
- Coordinate with ML teams: "GPU upgrades happen first weekend of every month"

## Alternative: Extend to 4 phases

If even 3 phases feel rushed, split GPU pools further:

- **Phase 2a:** T4 pools (inference, lower priority)
- **Phase 2b:** L4 pools (inference, edge cases)  
- **Phase 3a:** A100 pools (training, high value)
- **Phase 3b:** H100 pools (frontier training, highest value)

## Long-term architecture recommendations

### 1. Right-size node pools
- **Current:** 8 pools averaging 375 nodes each
- **Target:** 12-16 smaller pools (150-200 nodes each)
- **Benefit:** More pools = more upgrade parallelism opportunities, easier to fit in maintenance windows

### 2. Separate training and inference clusters
- **Training cluster:** Fewer, larger nodes with "no minor or node upgrades" exclusions during campaigns
- **Inference cluster:** More frequent automated upgrades, optimized for availability
- **Benefit:** Decouple upgrade cadences based on workload sensitivity

### 3. Consider Autopilot for non-GPU workloads  
- **Current CPU pools** → Autopilot cluster
- **Benefit:** Google manages all node upgrades, removes 4 pools from your upgrade burden
- **Keep GPU pools on Standard** for training control

## Monitoring and safety

**Progress tracking during each phase:**
```bash
# Monitor upgrade operations
gcloud container operations list --cluster CLUSTER_NAME --filter="operationType=UPGRADE_NODES"

# Track node version distribution
kubectl get nodes -o json | jq -r '.items[] | "\(.metadata.labels["cloud.google.com/gke-nodepool"]) \(.status.nodeInfo.kubeletVersion)"' | sort | uniq -c

# GPU utilization during upgrade (ensure training jobs properly checkpointed)
kubectl top nodes -l accelerator=nvidia-tesla-a100
```

**Rollback planning:**
- Control plane: Two-step minor upgrade with soak period (1.33+) enables rollback during soak
- Node pools: Can't downgrade in-place; must create new pools at old version if critical issues found

This phased approach transforms an impossible 40+ hour upgrade into three manageable 6-8 hour windows, respecting your GPU workload sensitivity while making steady progress toward the target version.