# Large-Scale GKE Upgrade Plan: 3,000-Node Multi-Pool Cluster

You're hitting GKE's **maximum upgrade parallelism limit** (~20 nodes simultaneously) combined with an 8-hour maintenance window that's insufficient for your cluster size. Here's how to solve this systematically:

## Scale Analysis

**Current constraints:**
- 3,000 nodes ÷ 20 concurrent = ~150 batches minimum
- At ~5-10 minutes per batch = 12.5-25 hours total upgrade time
- Your 8-hour window covers only ~30-60% of the upgrade

**GKE roadmap note:** Maximum parallelism is increasing to 100 nodes (target 2026), which would reduce your upgrade time to ~5-10 hours.

## Recommended Strategy

### 1. Extend maintenance window to 36 hours
```bash
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --maintenance-window-start "2025-01-11T02:00:00Z" \
    --maintenance-window-duration 36h \
    --maintenance-window-recurrence "FREQ=MONTHLY;BYSETPOS=1;BYDAY=SA"
```

Monthly Saturday 2am-2pm (next day) window ensures sufficient time. GKE doesn't pause mid-upgrade when windows expire — once started, upgrades continue to completion.

### 2. Stagger node pool upgrades by sensitivity

**Phase 1 - CPU pools first (lower risk):**
```bash
# Upgrade CPU pools during first part of window
gcloud container node-pools upgrade cpu-pool-1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION
# Let each complete before starting next
```

**Phase 2 - GPU pools during training gaps:**
```bash
# Schedule GPU pool upgrades when no active training jobs
gcloud container node-pools upgrade gpu-a100-pool --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION
```

### 3. GPU-specific upgrade strategy

For your GPU pools with likely fixed reservations:

```bash
# GPU pools: drain-first strategy (no surge capacity needed)
gcloud container node-pools update GPU_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 2-4

# Higher maxUnavailable (2-4) speeds up large pools
# Only if workloads tolerate temporary capacity loss
```

**GPU pool sequencing:** T4/L4 (inference) → A100/H100 (training) — upgrade inference pools first as they're more tolerant of interruption.

### 4. Protect long-running training workloads

```bash
# Add "no minor or node upgrades" exclusion to training pools
gcloud container node-pools update training-pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "training-campaign-2025" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support

# Upgrade training pools manually during scheduled gaps between runs
```

### 5. Enable nodepool upgrade concurrency (Preview, April 2026)

When available, this will allow multiple node pools to upgrade simultaneously instead of sequentially:

```bash
# Future: Enable concurrent nodepool upgrades
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --enable-nodepool-upgrade-concurrency
```

This could reduce your total upgrade time from 20+ hours to 8-12 hours.

## Immediate Action Plan

### Week 1: Infrastructure prep
- [ ] Extend maintenance window to 36 hours monthly
- [ ] Configure GPU pool surge settings (`maxUnavailable=2-4, maxSurge=0`)
- [ ] Set up training pool exclusions for active campaigns
- [ ] Test upgrade on 1 small CPU pool to validate timing

### Week 2: Phased upgrade execution
- [ ] **2am-6am:** Upgrade CPU pools sequentially (4 pools × 1 hour each)
- [ ] **6am-10am:** Break for health checks and issue resolution
- [ ] **10am-6pm:** Upgrade inference GPU pools (T4, L4)
- [ ] **6pm-2pm next day:** Upgrade training GPU pools (A100, H100) if no active jobs

### Week 3: Validation and optimization
- [ ] Monitor total upgrade time vs. predictions
- [ ] Adjust `maxUnavailable` settings based on actual drain performance
- [ ] Document lessons learned for future upgrades

## Alternative: Split cluster strategy

If monthly 36-hour windows are unacceptable:

**Split by workload type:**
- **Inference cluster:** T4/L4 pools + some CPU → 8-hour weekend windows
- **Training cluster:** A100/H100 pools + dedicated CPU → planned maintenance gaps

**Benefits:** Smaller blast radius, independent upgrade schedules, training-optimized configurations

## Monitoring during upgrades

```bash
# Track upgrade progress across all pools
watch 'gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE --format="table(name,version,status)"'

# Monitor pods not rescheduling
kubectl get pods -A | grep -E "Pending|Terminating" | wc -l

# Check for PDB violations blocking drain
kubectl get events -A --field-selector reason=EvictionBlocked --sort-by='.lastTimestamp'
```

## Cost optimization

- **Surge vs. drain-first trade-off:** Your GPU pools likely can't surge (fixed reservations), so `maxUnavailable` is your only speed lever
- **Spot instance pools:** If using spot VMs, increase `maxUnavailable` to 5-10% of pool size — spot workloads tolerate interruption
- **Off-peak timing:** 2am Saturday minimizes active workload interference

## Success metrics

- **Target:** Complete 3,000-node upgrade in <24 hours
- **Current baseline:** Measure actual upgrade time with new settings
- **Future state:** With 100-node concurrency (2026), target 8-12 hours total

This approach transforms your upgrade from a recurring operational crisis into a predictable monthly maintenance process. The key insight: at your scale, **time windows and sequencing** matter more than surge optimization.