# Large-Scale GKE Upgrade Plan (3,000 nodes)

Your upgrade timeout issue is expected at this scale. With GKE's maximum parallelism of ~20 nodes simultaneously, a 3,000-node cluster requires **150+ batches minimum**, taking **days to weeks** to complete. An 8-hour weekend window cannot accommodate this scale.

## Root Cause Analysis

**Scale vs. Window Mismatch:**
- 3,000 nodes ÷ 20 nodes/batch = 150+ batches minimum
- At ~15-20 minutes per batch (provision surge + drain + verify), you need **40-50+ hours** of upgrade time
- Your 8-hour Saturday window covers only ~15-20% of the required time

**GKE continues upgrades past maintenance windows** — the window controls when upgrades START, not when they must complete. However, very long-running upgrades can hit other constraints (quotas, regional capacity, operational complexity).

## Recommended Solutions

### 1. Extend Maintenance Window (Primary Recommendation)

```bash
# Expand to a longer weekend window
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-12-07T02:00:00Z" \
  --maintenance-window-end "2024-12-08T10:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Multi-day window strategy:**
- Saturday 2am → Sunday 10am (32-hour window)
- Or Friday 10pm → Sunday 6am (32-hour window with more buffer)
- Allows upgrades to complete naturally within the window

### 2. Staged Node Pool Upgrades (Immediate Mitigation)

Upgrade pools sequentially during separate maintenance windows instead of all at once:

**Week 1: CPU pools only (lower risk)**
```bash
# Upgrade CPU pools first - they're typically more tolerant
for pool in cpu-pool-1 cpu-pool-2 cpu-pool-3 cpu-pool-4; do
  gcloud container node-pools upgrade $pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version TARGET_VERSION
done
```

**Week 2-5: GPU pools one at a time**
```bash
# Week 2: T4 pool (lowest-end GPUs)
gcloud container node-pools upgrade t4-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION

# Week 3: L4 pool
# Week 4: A100 pool  
# Week 5: H100 pool (highest value - upgrade last)
```

### 3. GPU Pool Optimization (Critical for Your Fleet)

Your GPU pools likely have the most constraints. Configure them for efficient upgrades:

**For fixed GPU reservations (most common):**
```bash
# T4/L4 pools: Higher maxUnavailable (these are more replaceable)
gcloud container node-pools update t4-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 3

# A100/H100 pools: Conservative (these are precious)  
gcloud container node-pools update h100-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

**Key insight:** For GPU pools with fixed reservations, `maxUnavailable` is your PRIMARY lever. Increasing it from 1→3 triples upgrade speed but creates temporary capacity dips.

### 4. Workload-Specific Maintenance Exclusions

Use maintenance exclusions to protect active training campaigns while allowing inference pools to upgrade:

```bash
# Block upgrades during active training (up to EoS)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-q4" \
  --add-maintenance-exclusion-start-time "2024-12-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

This allows security patches on the control plane while blocking disruptive node upgrades.

### 5. Capacity and Quota Pre-Check

Before any large upgrade, verify you have the resources:

```bash
# Check current utilization vs quota
gcloud compute project-info describe --format="yaml(quotas)"

# Verify GPU reservation headroom  
gcloud compute reservations describe GPU_RESERVATION_NAME --zone ZONE

# If using surge (maxSurge > 0), ensure 5-10% extra quota
# If using drain-first (maxSurge=0), no extra quota needed
```

## Implementation Timeline

**Immediate (this week):**
1. Extend maintenance window to 32 hours (Friday night → Sunday morning)
2. Configure GPU pools with appropriate maxUnavailable settings
3. Apply maintenance exclusion if you have active training jobs

**Next upgrade cycle:**
1. Upgrade CPU pools first (Week 1)  
2. Upgrade GPU pools sequentially (Weeks 2-5)
3. Validate each pool before proceeding to next

**Long-term optimization:**
1. Consider cluster partitioning (separate training vs inference clusters)
2. Implement rollout sequencing for multi-cluster environments
3. Move to Extended release channel for 24-month support periods

## Cluster Architecture Recommendation

For a 3,000-node fleet, consider splitting into specialized clusters:

**Training cluster (1,000-1,500 nodes):**
- H100/A100 pools only
- Extended release channel + "no minor or node upgrades" exclusion
- Manual upgrades between training campaigns
- Dedicated network with GPUDirect-TCPX

**Inference cluster (1,500-2,000 nodes):**
- L4/T4 pools + CPU pools  
- Regular release channel + extended maintenance windows
- Autoscaled blue-green upgrades for inference workloads
- Auto-upgrade enabled with staged rollout

This isolates your highest-value training workloads from routine maintenance while allowing inference to stay current.

## Success Metrics

Track these to validate the new approach:
- Upgrade completion rate within maintenance window
- Training job interruption (should approach zero)
- Time to complete full fleet upgrade (target: <1 week)
- GPU utilization during maintenance windows

Your scale puts you in the top 1% of GKE clusters. The standard 8-hour maintenance approach doesn't apply — you need enterprise-grade upgrade orchestration with multi-day windows and staged rollouts.