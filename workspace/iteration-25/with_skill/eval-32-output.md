# Large-Scale GKE Upgrade Plan: 3,000 Node Multi-GPU Cluster

## Problem Analysis

Your 8-hour maintenance window is insufficient for 3,000 nodes. At GKE's ~20 node maximum concurrent upgrade rate, you need **150+ batches minimum** just for the math, not including:
- Pod drain time (especially GPU workloads with longer termination periods)
- Surge node provisioning delays (GPU capacity constraints)
- Sequential node pool processing (GKE upgrades one pool at a time by default)

## Recommended Solution: Phased Upgrade Strategy

### Phase 1: CPU Pools (Lower Risk, Faster)
**Timing:** First Saturday window (2am-10am)
- Upgrade all 4 CPU pools first
- CPU nodes upgrade faster (no GPU driver dependencies)
- Higher `maxUnavailable` tolerance for stateless workloads
- If something goes wrong, GPU workloads still run

### Phase 2: GPU Pools (Higher Risk, Slower)  
**Timing:** Following Saturday window(s)
- Upgrade GPU pools during training job gaps
- One pool type per window for risk isolation
- Account for driver compatibility testing time

## Detailed Configuration

### GPU Pool Settings (Critical)
For pools with fixed GPU reservations (most A100/H100 customers):
```bash
# Primary strategy: maxUnavailable only (no surge capacity available)
gcloud container node-pools update GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4
```

**Pool-specific recommendations:**
- **H100/A100 pools:** `maxUnavailable=2` (conservative, these are expensive)
- **L4/T4 pools:** `maxUnavailable=4` (higher tolerance for inference workloads)
- **Never use maxSurge for GPU pools with fixed reservations** — surge nodes will fail to provision

### CPU Pool Settings  
```bash
# CPU pools: can use surge if quota available
gcloud container node-pools update CPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 5% \
  --max-unavailable-upgrade 0
```

### Extended Maintenance Windows

**Option A — Multi-weekend approach (Recommended):**
```bash
# Weekend 1: CPU pools only
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-window-start "2025-01-04T02:00:00Z" \
  --maintenance-window-duration 8h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Weekend 2+: GPU pools (one type per weekend)
# Apply "no minor or node upgrades" exclusion between weekends
```

**Option B — Extended weekend window:**
```bash
# Friday 10pm - Sunday 6am (32-hour window)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-window-start "2025-01-03T22:00:00Z" \
  --maintenance-window-duration 32h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=FR"
```

### AI Workload Protection

For long-running training jobs:
```bash
# Block upgrades during training campaigns
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "training-campaign" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Training workflow:**
1. Apply exclusion before starting multi-day/week training
2. Remove exclusion during scheduled gaps between training runs
3. Upgrade during gaps, not mid-training

## Pre-Upgrade Checklist (Large Scale)

```
Large Cluster Pre-Upgrade Checklist
- [ ] Cluster: ___ | 3,000 nodes across 8 pools | Current: ___ → Target: ___

GPU-Specific Readiness
- [ ] Target GKE version GPU driver compatibility confirmed in staging
- [ ] A100/H100 pools: CUDA version change tested with workloads
- [ ] GPU reservations verified — no surge capacity assumed
- [ ] L4/T4 inference: latency impact tested with autoscaled blue-green in staging
- [ ] Training jobs: checkpoint/resume capability verified
- [ ] GPUDirect-TCPX/RDMA compatibility confirmed (if applicable)

Scale-Specific Planning  
- [ ] Upgrade phases defined: CPU pools → GPU pools (one type per window)
- [ ] Node pool upgrade parallelism: manual trigger for concurrent pools
- [ ] Maintenance window extended: 8h → 32h OR multi-weekend plan
- [ ] Between-phase exclusions configured to prevent auto-continuation
- [ ] Cluster autoscaler behavior during upgrades: pause or accept mixed-version state
- [ ] Monitoring dashboards ready for 48+ hour upgrade duration

Risk Mitigation
- [ ] Staging cluster (representative node pool sizes) upgrade tested end-to-end
- [ ] Rollback plan: new node pools + workload migration (not in-place downgrade)
- [ ] On-call team available for full weekend(s)
- [ ] Customer communication: "GPU training may be unavailable Sat-Sun"
- [ ] Quota verified: no additional CPU quota needed (using maxUnavailable mode for GPU)
```

## Runbook: Multi-Phase Large Cluster Upgrade

### Phase 1: Control Plane (Friday night)
```bash
# Start control plane upgrade off-peak to avoid Saturday morning issues
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version TARGET_VERSION
# Takes ~10-15 minutes, done before maintenance window
```

### Phase 2: CPU Pools (Saturday 2am-10am)
```bash
# Trigger all CPU pools concurrently (override default sequential)
for pool in cpu-pool-1 cpu-pool-2 cpu-pool-3 cpu-pool-4; do
  gcloud container node-pools upgrade $pool \
    --cluster CLUSTER_NAME \
    --region REGION \
    --cluster-version TARGET_VERSION &
done

# Monitor progress every 30 minutes
watch 'kubectl get nodes -o wide | grep -c TARGET_VERSION'
```

### Phase 3: GPU Pools (Following weekends)
```bash
# Weekend 2: A100/H100 pools (highest value, most conservative)
gcloud container node-pools upgrade h100-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version TARGET_VERSION

# Weekend 3: L4/T4 pools (inference workloads)
gcloud container node-pools upgrade l4-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version TARGET_VERSION
```

## Alternative: Autoscaled Blue-Green for GPU Inference

If GPU inference pools are large and latency-sensitive:
```bash
gcloud container node-pools update GPU_INFERENCE_POOL \
  --cluster CLUSTER_NAME \
  --region REGION \
  --enable-autoscaling \
  --total-max-nodes CURRENT_SIZE_X2 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25
```

This keeps the old pool serving while new nodes warm up, minimizing inference downtime.

## Troubleshooting Large Scale Upgrades

**Most likely issues:**
1. **GPU surge quota exhaustion** → Use `maxUnavailable` mode instead of surge
2. **Mixed-version cluster autoscaler confusion** → Pause autoscaler during upgrade or accept mixed state
3. **Training job eviction during 1-hour PDB timeout** → Use "no minor or node upgrades" exclusions during training campaigns
4. **Upgrade stalls after 20 nodes** → This is expected; GKE's concurrency limit. Monitor batch completion, don't force-restart operations.

**Key insight:** Your scale requires treating upgrades as **multi-day operations**, not single maintenance windows. Plan accordingly with phased rollouts and workload-aware scheduling.

This approach transforms your 8-hour timeout problem into a controlled, predictable multi-weekend process that respects both GKE's technical limits and your workload requirements.