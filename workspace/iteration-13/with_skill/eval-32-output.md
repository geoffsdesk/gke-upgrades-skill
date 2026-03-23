# Large-Scale GKE Cluster Upgrade Strategy

Your 3,000-node cluster with mixed GPU/CPU pools faces several scale-specific challenges. An 8-hour maintenance window won't be sufficient given GKE's upgrade concurrency limits and GPU constraints.

## Current Scale Constraints

**GKE Upgrade Parallelism:** ~20 nodes simultaneously regardless of `maxSurge` settings
- Your cluster: 3,000 nodes ÷ 20 = **minimum 150 batches**
- Per-batch time: ~10-15 minutes including drain + provision + ready
- **Total time estimate: 25-40 hours** (150 batches × 10-15 min each)

**8-hour window reality:** Only ~500-700 nodes can upgrade per window, leaving 2,300+ nodes for subsequent weekends.

## Recommended Strategy

### 1. Extend Your Maintenance Window

```bash
# Expand to Friday 10pm - Sunday 6am (32-hour window)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-12-06T22:00:00Z" \
  --maintenance-window-end "2024-12-08T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=FR"
```

### 2. Stagger Node Pool Upgrades (Don't upgrade all 8 pools simultaneously)

**Priority order:**
1. **CPU pools first** (faster, no GPU constraints)
2. **Inference GPU pools** (L4, T4) — shorter jobs, more tolerant
3. **Training GPU pools** (A100, H100) — during scheduled training gaps

### 3. GPU Pool Upgrade Strategy

**For GPU pools with fixed reservations:**
```bash
# A100/H100 pools: Conservative, no surge capacity needed
gcloud container node-pools update gpu-a100-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2

# L4/T4 pools: Slightly more aggressive if you have headroom
gcloud container node-pools update gpu-l4-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 3
```

**For training pools:** Use maintenance exclusions to protect active training campaigns:
```bash
# Block node upgrades on training pools during campaigns
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-q4" \
  --add-maintenance-exclusion-start-time "2024-12-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-nodepool gpu-a100-training
```

### 4. CPU Pool Optimization

**Scale up surge aggressively for CPU pools:**
```bash
# CPU pools: Use percentage-based maxSurge (5% of pool size)
# For 500-node CPU pool: maxSurge=25, maxUnavailable=0

gcloud container node-pools update cpu-general-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 25 \
  --max-unavailable-upgrade 0
```

## Multi-Weekend Upgrade Plan

Given the scale, plan a **3-weekend rollout:**

### Weekend 1: CPU Pools (4 pools, ~1,500 nodes)
- Upgrade all 4 CPU pools with aggressive surge settings
- Expected completion: 15-20 hours

### Weekend 2: Inference GPU Pools (L4, T4)
- Coordinate with ML teams to minimize inference traffic
- Use `maxUnavailable=2-3` per pool

### Weekend 3: Training GPU Pools (A100, H100)
- Only during scheduled training gaps
- Use parallel maintenance strategy if all nodes can be updated simultaneously

## Alternative: Blue-Green at Node Pool Level

For mission-critical pools, consider **manual blue-green**:

1. **Create new pool** at target version
2. **Gradually migrate workloads** (cordon old, schedule on new)
3. **Delete old pool** once migration complete

This gives you full control over timing but requires 2x capacity temporarily.

## Monitoring & Automation

```bash
# Monitor upgrade progress across all pools
watch 'gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE --format="table(name,version,status)"'

# Check which nodes are upgrading
kubectl get nodes -l cloud.google.com/gke-nodepool -o custom-columns=POOL:.metadata.labels.cloud\.google\.com/gke-nodepool,NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion --sort-by=.metadata.labels.cloud\.google\.com/gke-nodepool
```

## Key Recommendations

1. **Accept multi-weekend reality** — 8 hours isn't sufficient for 3,000 nodes
2. **Prioritize CPU pools** — they upgrade faster and have fewer constraints
3. **Coordinate with ML teams** — understand training schedules before touching GPU pools
4. **Use maintenance exclusions** — protect active training workloads
5. **Consider cluster splitting** — 3,000 nodes may warrant multiple clusters by workload type

This approach respects GKE's concurrency limits while minimizing disruption to your GPU workloads. The total upgrade will span 2-3 weekends, but each pool completes within its optimal maintenance strategy.