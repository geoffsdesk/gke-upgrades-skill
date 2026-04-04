# Large-Scale GKE Cluster Upgrade Plan (3,000 nodes)

## Problem Analysis

Your 3,000-node cluster is hitting GKE's **maximum upgrade parallelism limit of ~20 nodes simultaneously** (increasing to 100 in roadmap). This means your upgrade requires ~150 batches minimum, taking days to weeks — far exceeding your 8-hour Saturday window.

**Key insight:** GKE upgrades one node pool at a time by default. With 8 pools averaging 375 nodes each, a single pool takes 18+ batches × 20-30 minutes per batch = 6-9 hours just for one pool.

## Recommended Strategy

### 1. **Extend maintenance windows to multi-day approach**
```bash
# Configure maintenance window to span multiple days
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-duration 8h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA,SU"
```

This gives you 16 hours across weekend (Saturday + Sunday 2am-10am).

### 2. **Stagger node pool upgrades by priority**

**Week 1 — CPU pools (lower risk):**
```bash
# Upgrade CPU pools first (stateless workloads, easier to reschedule)
gcloud container node-pools upgrade cpu-pool-1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION

# Monitor progress, trigger next pool when first completes
gcloud container node-pools upgrade cpu-pool-2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION
# Repeat for cpu-pool-3, cpu-pool-4
```

**Week 2 — GPU pools (during training gaps):**
```bash
# GPU pools during scheduled training downtime
# Use maxUnavailable mode for fixed GPU reservations
gcloud container node-pools update a100-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2

gcloud container node-pools upgrade a100-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

### 3. **Optimize surge settings per pool type**

**CPU pools (assume elastic capacity):**
```bash
# Higher maxSurge for CPU pools (5% of pool size)
# 375-node pool → maxSurge=19 (rounded from 18.75)
gcloud container node-pools update cpu-pool-1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 19 \
  --max-unavailable-upgrade 0
```

**GPU pools (assume fixed reservations):**
```bash
# maxUnavailable mode for GPU pools (no surge capacity)
# Higher maxUnavailable for faster upgrade (if workloads tolerate capacity loss)
gcloud container node-pools update a100-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4
```

### 4. **Parallel node pool upgrades (manual trigger)**

While GKE auto-upgrades one pool at a time, you can manually trigger multiple pools in parallel:

```bash
# Start multiple pools simultaneously (different terminal sessions)
gcloud container node-pools upgrade cpu-pool-1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade cpu-pool-2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade cpu-pool-3 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &

# Monitor all upgrades
watch 'gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES" --limit=10'
```

**Caution:** Only parallelize pools with different workload types. Don't upgrade both A100 and H100 pools simultaneously if they run the same training jobs.

### 5. **Consider cluster splitting for extreme scale**

For future growth beyond 5,000 nodes, consider splitting into multiple clusters:
- **Training cluster:** GPU pools only (A100, H100)
- **Inference cluster:** Mixed GPU/CPU (L4, T4, CPU)
- **Batch cluster:** CPU pools for batch workloads

This reduces per-cluster upgrade complexity and blast radius.

## GPU Pool Specific Guidance

### A100/H100 pools (training workloads):
```bash
# Coordinate with training schedule
# Apply maintenance exclusion during active training campaigns
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Remove exclusion during planned training gaps, then upgrade
# Use maxUnavailable=1 for conservative upgrade
gcloud container node-pools update a100-pool \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

### L4/T4 pools (inference workloads):
```bash
# Use autoscaled blue-green to avoid inference latency spikes
gcloud container node-pools update l4-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 10 --total-max-nodes 100 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

## Timeline Estimation

**Realistic timeline for 3,000-node cluster:**
- **Control plane:** 10-15 minutes
- **Each CPU pool (375 nodes):** 6-9 hours with maxSurge=19
- **Each GPU pool (375 nodes):** 12-18 hours with maxUnavailable=2
- **Total sequential:** 2-3 weeks
- **With parallelization:** 1-2 weeks
- **With multi-day windows:** Fits in 2 weekends

## Monitoring and Validation

```bash
# Monitor upgrade progress across all pools
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,POOL:.metadata.labels.cloud\.google\.com/gke-nodepool | sort -k3,3

# Check for stuck operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES AND status=RUNNING"

# Validate workload health during upgrade
kubectl get pods -A | grep -v Running | grep -v Completed | wc -l
```

## Key Recommendations

1. **Accept multi-weekend upgrade cycles** — 3,000 nodes cannot upgrade in 8 hours
2. **Prioritize CPU pools first** — lower risk, validates upgrade strategy
3. **Coordinate GPU upgrades with training schedules** — use maintenance exclusions
4. **Use parallel manual upgrades** for pools with different workload types
5. **Consider cluster splitting** if you grow beyond 5,000 nodes

The fundamental constraint is GKE's 20-node parallelism limit. Until that increases to 100 (roadmap item), large clusters require extended maintenance windows and careful orchestration.