# Accelerated Large-Scale GKE Upgrade Plan

## Current Bottleneck Analysis

Your 600-node upgrade is hitting GKE's **maximum upgrade parallelism of ~20 nodes simultaneously** (roadmap: increasing to 100 nodes). For a 600-node cluster, that's approximately 30 batches minimum, which explains the 24+ hour duration.

## Recommended Multi-Phase Strategy

### Phase 1: Optimize Upgrade Settings (Immediate Impact)

**CPU Pools** (surge capacity available):
```bash
# Increase maxSurge to percentage-based, capped at parallelism limit
# For 200-node CPU pools: 5% = 10 nodes per pool
gcloud container node-pools update CPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 10 \
  --max-unavailable-upgrade 0

gcloud container node-pools update CPU_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 10 \
  --max-unavailable-upgrade 0
```

**GPU Pools** (fixed reservations, no surge capacity):
```bash
# Use maxUnavailable as primary lever - increase from default 1 to 4
# This drains 4 GPU nodes simultaneously instead of 1
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

**Expected improvement:** Reduces from ~30 batches to ~15 batches for CPU pools, ~10 batches for GPU pools. Estimated total time: 12-16 hours.

### Phase 2: Parallel Pool Upgrades (Major Impact)

**Manual parallel execution** — upgrade multiple node pools simultaneously instead of waiting for sequential completion:

```bash
# Start all upgrades in parallel (requires separate terminals)
# Terminal 1:
gcloud container node-pools upgrade CPU_POOL_1 \
  --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &

# Terminal 2:
gcloud container node-pools upgrade CPU_POOL_2 \
  --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &

# Terminal 3:
gcloud container node-pools upgrade GPU_POOL_1 \
  --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &

# Terminal 4:
gcloud container node-pools upgrade GPU_POOL_2 \
  --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
```

**Monitor all pools:**
```bash
watch 'gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE --format="table(name,version,status)"'
```

**Expected improvement:** 4 pools upgrading simultaneously. Estimated total time: 6-8 hours (fits in your 8-hour window).

### Phase 3: GPU Pool Strategy Refinement

For GPU pools specifically, consider **autoscaled blue-green** if you have any reservation headroom:

```bash
# Check reservation utilization first
gcloud compute reservations describe RESERVATION_NAME --zone ZONE

# If headroom exists, use autoscaled blue-green for GPU pools
gcloud container node-pools update GPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --enable-autoscaling \
  --total-min-nodes MIN --total-max-nodes MAX \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25
```

This cordons the old pool and auto-scales replacement nodes, avoiding the capacity dip from `maxUnavailable` mode.

## Workload Considerations

**GPU workload protection:**
- **Training jobs:** Apply "no minor or node upgrades" exclusion during active training campaigns:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

- **Inference workloads:** Configure PDBs to ensure minimum serving capacity:
```bash
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: inference-pdb
spec:
  minAvailable: 75%  # Maintain serving capacity during upgrades
  selector:
    matchLabels:
      app: inference-server
EOF
```

## Upgrade Sequence Strategy

**Recommended order for parallel execution:**
1. **CPU pools first** (lower risk, surge capacity available)
2. **GPU pools during training gaps** (coordinate with ML team)

**Alternative staged approach:**
```bash
# Weekend 1: CPU pools only (lower risk)
gcloud container node-pools upgrade CPU_POOL_1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade CPU_POOL_2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &

# Weekend 2: GPU pools during scheduled training downtime
gcloud container node-pools upgrade GPU_POOL_1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade GPU_POOL_2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
```

## Monitoring During Upgrade

```bash
# Real-time progress tracking
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "(NAME|NotReady|SchedulingDisabled)"'

# GPU utilization during upgrade
kubectl top nodes -l cloud.google.com/gke-accelerator=nvidia-tesla-a100

# Check for stuck pods
kubectl get pods -A --field-selector=status.phase=Pending
```

## Expected Timeline

**Current state:** 24+ hours  
**With optimized settings:** 12-16 hours  
**With parallel execution:** 6-8 hours (fits your maintenance window)

## Future Improvements (Roadmap)

- **GKE's upgrade parallelism is increasing to 100 nodes** — when available, you'll see dramatic speedup without configuration changes
- **Nodepool upgrade concurrency (preview April 2026)** — GKE will automatically upgrade multiple node pools in parallel during auto-upgrades

## Risk Mitigation

**Rollback plan:** With 4 parallel upgrades, have multiple operators monitoring. If any pool fails:
```bash
# Cancel remaining upgrades
gcloud container operations cancel OPERATION_ID --zone ZONE

# Each pool can be independently rolled back or retried
```

**Resource monitoring:** Parallel upgrades increase API load and cluster churn. Monitor cluster control plane latency during execution.

This strategy should reduce your upgrade time from 24+ hours to under 8 hours, fitting within your weekend maintenance window while maintaining workload availability.