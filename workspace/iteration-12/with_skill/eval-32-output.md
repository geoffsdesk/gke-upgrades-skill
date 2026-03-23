# Large-Scale GKE Upgrade Strategy (3,000+ Nodes)

Your 8-hour maintenance window is insufficient for a 3,000-node cluster. With GKE's ~20 node maximum upgrade parallelism, you're looking at **150+ batches minimum** — potentially days of upgrade time, not hours.

## Immediate Solutions

### 1. Extend Maintenance Window to Multi-Day
```bash
# Example: Friday 10pm - Monday 6am (80-hour window)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "YYYY-MM-DDTFRI22:00:00Z" \
  --maintenance-window-end "YYYY-MM-DDTMON06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=FR"
```

### 2. Stagger Node Pool Upgrades (Don't Upgrade All Pools Simultaneously)

**Phase 1: CPU pools first (less disruptive)**
```bash
# Upgrade CPU pools with higher surge settings
gcloud container node-pools update CPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5% \  # 5% of pool size
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade CPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

**Phase 2: GPU pools during training gaps**
```bash
# GPU pools: maxUnavailable is primary lever (assume no surge capacity)
gcloud container node-pools update GPU_POOL_A100 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2  # Increase for faster completion

gcloud container node-pools upgrade GPU_POOL_A100 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

### 3. Use "No Minor or Node Upgrades" Exclusion for Control
```bash
# Block auto-upgrades, do manual upgrades during planned windows
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "manual-upgrade-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## GPU Pool-Specific Strategy

### A100/H100 Pools (Training Workloads)
- **Maintenance exclusions are critical** — use per-nodepool exclusions during active training campaigns
- **Coordinate with training schedule** — upgrade only during gaps between training runs
- **Cordon and wait pattern:**
```bash
# Cordon training nodes, wait for natural completion
kubectl cordon -l cloud.google.com/gke-nodepool=GPU_POOL_A100
# Wait for training jobs to complete naturally, then upgrade empty pool
```

### L4/T4 Pools (Inference Workloads)
- **Use autoscaled blue-green upgrades** for inference pools that need continuous availability:
```bash
gcloud container node-pools update L4_INFERENCE_POOL \
  --cluster CLUSTER_NAME \
  --enable-autoscaling \
  --total-min-nodes MIN --total-max-nodes MAX \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

## Architecture Recommendations

### 1. Split Into Multiple Smaller Clusters
Consider restructuring as 2-4 clusters of 750-1,500 nodes each:
- **Training cluster** (A100/H100) — can tolerate full restarts
- **Inference cluster** (L4/T4) — needs rolling upgrades
- **Batch processing cluster** (CPU) — flexible timing
- **Services cluster** (CPU) — needs availability

This reduces per-cluster upgrade time and enables different maintenance strategies.

### 2. Dedicated Training Node Pools with Tight Control
```bash
# Training pools: block auto-upgrades entirely
gcloud container node-pools update TRAINING_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```
Upgrade these pools manually only during scheduled training gaps.

## Recommended Multi-Phase Upgrade Plan

### Phase 1: Control Plane (15 minutes)
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION
```

### Phase 2: CPU Pools (2-3 days)
- Surge settings: 5% of pool size, maxUnavailable=0
- Run overnight during business downtime

### Phase 3: Inference GPU Pools (1-2 days)
- Use autoscaled blue-green for L4/T4 pools
- Coordinate with inference traffic patterns

### Phase 4: Training GPU Pools (coordinate with training schedule)
- Wait for natural training gap
- Use `maxUnavailable=2-5` for faster completion
- Parallel strategy if full restart is acceptable

## Monitoring Large Upgrades

```bash
# Track progress across all pools
watch 'gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE --format="table(name,version,status)"'

# Monitor node readiness
watch 'kubectl get nodes -o custom-columns="POOL:.metadata.labels.cloud\.google\.com/gke-nodepool,VERSION:.status.nodeInfo.kubeletVersion,STATUS:.status.conditions[?(@.type==\"Ready\")].status" --no-headers | sort | uniq -c'

# Check for stuck operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES AND status=RUNNING"
```

## Timeline Expectations

With your scale:
- **CPU pools (2,000 nodes):** ~3-4 days at 5% surge
- **GPU pools (1,000 nodes):** ~2-3 days with maxUnavailable=2
- **Total upgrade window:** Plan for 5-7 days end-to-end

## Key Takeaways

1. **Your 8-hour window is the core problem** — extend to multi-day or split the cluster
2. **Don't upgrade all pools simultaneously** — phase CPU first, then GPU during training gaps  
3. **GPU pools need special handling** — coordinate with training schedules, use maintenance exclusions
4. **Consider cluster splitting** — multiple smaller clusters upgrade faster and enable different strategies per workload type
5. **Manual upgrade control is necessary at your scale** — use maintenance exclusions to control timing rather than fighting auto-upgrades

Would you like me to create a detailed runbook for any specific phase, or help you evaluate cluster splitting options?