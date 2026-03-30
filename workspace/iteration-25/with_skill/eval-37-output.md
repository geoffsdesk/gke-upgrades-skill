# GKE AI/ML Platform Upgrade Plan: 1.31 → 1.32

**Cluster Details:** 5,000-node mixed AI/ML platform  
**Target:** GKE 1.31 → 1.32 minor version upgrade  
**Priority:** Training continuity (H100) > Inference availability (A100) > Dev/Services uptime

## Executive Summary

This is a **high-risk, high-impact upgrade** requiring 2-3 weeks execution time. The H100 training pools pose the greatest challenge due to limited surge capacity and multi-day job sensitivity. We'll use a phased approach with extensive validation gates.

**Key Constraints:**
- GPU VMs don't support live migration — every upgrade requires pod restart
- H100 surge capacity likely unavailable (assume fixed reservation)
- Training jobs can't tolerate mid-job eviction (1+ week runtimes)
- A100 inference pools need minimal downtime for serving continuity

## Phase 1: Pre-flight & Staging (Days 1-3)

### 1.1 Compatibility Validation

```bash
# Check target version availability
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels)" | grep -A 10 "1\.32"

# Critical: Verify no deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Check GKE deprecation insights
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=LOCATION \
  --project=PROJECT_ID \
  --filter="category.category:RELIABILITY"
```

### 1.2 GPU Driver Compatibility Testing

**Critical prerequisite:** Test GPU driver changes in staging before production.

1. Create staging node pools with 1.32 for each GPU type:
   ```bash
   # H100 staging pool
   gcloud container node-pools create h100-staging-132 \
     --cluster STAGING_CLUSTER \
     --machine-type a3-highgpu-8g \
     --accelerator type=nvidia-h100-80gb,count=8 \
     --cluster-version 1.32.x-gke.xxx \
     --num-nodes 2

   # A100 staging pool  
   gcloud container node-pools create a100-staging-132 \
     --cluster STAGING_CLUSTER \
     --machine-type a2-highgpu-1g \
     --accelerator type=nvidia-tesla-a100,count=1 \
     --cluster-version 1.32.x-gke.xxx \
     --num-nodes 2
   ```

2. Deploy representative workloads and validate:
   - CUDA version compatibility
   - Model loading performance
   - GPUDirect-TCPX functionality (if used)
   - Training throughput benchmarks
   - Inference latency benchmarks

**Go/No-Go Gate:** All GPU driver tests must pass before proceeding.

## Phase 2: Control Plane Upgrades (Days 4-5)

Upgrade all cluster control planes first. For large clusters, schedule during off-peak hours.

**Assumption:** Using regional clusters (recommended for production) — control plane remains highly available during upgrade.

```bash
# Control plane upgrade (per cluster)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.xxx

# Validate control plane health
kubectl get pods -n kube-system
kubectl get nodes  # Should show CP at 1.32, nodes at 1.31
```

**Timeline:** ~30 minutes per cluster control plane.

## Phase 3: Non-Critical Pools (Days 6-8)

Start with lowest-risk pools to validate upgrade procedures.

### 3.1 CPU Service Nodes (1,000 nodes)

**Strategy:** Surge upgrade with percentage-based maxSurge
**Risk:** Low — stateless services, fast recovery

```bash
gcloud container node-pools update cpu-services \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5% \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade cpu-services \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxx
```

**Expected Duration:** 6-8 hours (1,000 nodes ÷ ~20 concurrent = 50 batches)

### 3.2 T4 Development Nodes (500 nodes)

**Strategy:** GPU-optimized surge (maxUnavailable mode)
**Risk:** Low — dev workloads, can tolerate disruption

```bash
gcloud container node-pools update t4-dev \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2

gcloud container node-pools upgrade t4-dev \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxx
```

**Expected Duration:** 4-6 hours (500 nodes ÷ ~20 concurrent = 25 batches)

**Validation Gate:** Verify GPU drivers, CUDA compatibility on dev workloads before proceeding.

## Phase 4: A100 Inference Pools (Days 9-12)

**Strategy:** Autoscaled blue-green upgrade for minimal inference disruption
**Risk:** Medium — customer-facing inference, revenue impact

### 4.1 Pre-upgrade: Inference Health Check

```bash
# Baseline inference metrics
kubectl top pods -l workload=inference --containers
# Document current throughput, latency p95/p99
```

### 4.2 A100 Upgrade Execution

**Key insight:** Autoscaled blue-green keeps old pool serving while new pool scales up — minimizes inference downtime.

```bash
# Configure autoscaled blue-green
gcloud container node-pools update a100-inference \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 100 \
  --total-max-nodes 1500 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Execute upgrade
gcloud container node-pools upgrade a100-inference \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxx
```

**Expected Duration:** 8-12 hours (1,500 nodes, autoscaled transition)

**Monitoring:** Track inference latency during upgrade. If latency degrades >20%, consider pausing.

### 4.3 Post-upgrade Validation

- [ ] All inference pods rescheduled successfully
- [ ] Inference latency within 5% of baseline
- [ ] Model loading times unchanged
- [ ] GPU memory utilization normal
- [ ] No CUDA errors in application logs

## Phase 5: H100 Training Pools (Days 13-20)

**Strategy:** Maintenance exclusion + coordinated training campaign pause
**Risk:** Highest — multi-day training jobs, limited rollback options

### 5.1 Training Campaign Coordination

**Critical:** Coordinate with ML teams 1 week before this phase.

1. **Pre-upgrade (Day 13):**
   - Pause new training job submissions
   - Allow in-flight jobs to complete or reach checkpoint
   - Apply maintenance exclusion to prevent auto-upgrades during jobs

   ```bash
   gcloud container clusters update CLUSTER_NAME \
     --zone ZONE \
     --add-maintenance-exclusion-name "training-campaign-pause" \
     --add-maintenance-exclusion-start-time 2024-XX-XXTXX:XX:XXZ \
     --add-maintenance-exclusion-end-time 2024-XX-XXTXX:XX:XXZ \
     --add-maintenance-exclusion-scope no_upgrades
   ```

2. **Job completion verification:**
   ```bash
   # Monitor active training jobs
   kubectl get pods -l workload=training --field-selector=status.phase=Running
   # Wait for count = 0 or all jobs at safe checkpoint
   ```

### 5.2 H100 Pool Upgrade Strategy

**Two sub-phases for risk mitigation:**

#### Phase 5.2a: H100 Pool 1 (1,000 nodes) - Days 15-17

```bash
# Configure for fixed GPU reservation (no surge capacity)
gcloud container node-pools update h100-pool-1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4

# Execute upgrade
gcloud container node-pools upgrade h100-pool-1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxx
```

**Expected Duration:** 12-16 hours (1,000 nodes ÷ 4 unavailable = 250 batches)

#### Phase 5.2b: H100 Pool 2 (1,000 nodes) - Days 18-20

Only proceed after validating Pool 1 upgrade success:

- [ ] All H100 Pool 1 nodes at 1.32
- [ ] No CUDA/driver issues
- [ ] Test training job successfully runs on upgraded nodes
- [ ] GPUDirect-TCPX topology preserved (if applicable)

```bash
# Same strategy for Pool 2
gcloud container node-pools upgrade h100-pool-2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxx
```

### 5.3 Post-H100 Validation

**Critical validation before resuming training:**

```bash
# Verify all H100 nodes ready
kubectl get nodes -l cloud.google.com/gke-nodepool=h100-pool-1,h100-pool-2 

# Test job deployment
kubectl run test-training-job \
  --image=nvcr.io/nvidia/pytorch:24.01-py3 \
  --limits=nvidia.com/gpu=8 \
  --overrides='{"spec":{"nodeSelector":{"cloud.google.com/gke-nodepool":"h100-pool-1"}}}' \
  -- python -c "import torch; print(f'GPUs available: {torch.cuda.device_count()}')"
```

**Go/No-Go Gate:** Test training job must successfully allocate 8 H100s and report correct CUDA version.

## Phase 6: Fleet-wide Validation & Cleanup (Days 21-22)

### 6.1 Complete Fleet Health Check

```bash
# Verify all nodes at target version
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion | grep -v 1.32

# System health across all pools
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded

# Resource utilization normal
kubectl top nodes | head -20
```

### 6.2 Performance Regression Testing

- [ ] Training throughput: Run representative 1-hour training job on H100
- [ ] Inference latency: A100 p95 latency within 5% of baseline  
- [ ] Service response times: CPU service pools performing normally
- [ ] GPU memory: No memory leaks or utilization anomalies

### 6.3 Resume Normal Operations

```bash
# Remove maintenance exclusions
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "training-campaign-pause"

# Resume training job submissions
# Notify ML teams: cluster ready for full training campaigns
```

## Risk Mitigation & Rollback Planning

### Rollback Strategy (Per Phase)

**CPU/T4 Pools:** Create new pools at 1.31, migrate workloads, delete upgraded pools
**A100 Inference:** Blue-green provides automatic rollback during soak period
**H100 Training:** **No easy rollback** — plan for forward fixes only

### Circuit Breakers

**Stop upgrade if:**
- >5% of nodes fail to upgrade successfully in any pool
- GPU driver compatibility issues discovered in production
- Inference latency degrades >20% sustained
- Any H100 node shows CUDA errors post-upgrade

### Monitoring During Upgrade

```bash
# Continuous monitoring commands
watch 'kubectl get nodes -o wide | grep -E "NotReady|SchedulingDisabled"'
watch 'kubectl get pods -A | grep -E "Pending|CrashLoopBackOff"'

# GPU-specific health checks
kubectl describe nodes | grep -A 5 "nvidia.com/gpu"
```

## Timeline Summary

| Phase | Duration | Pools | Risk | Rollback Difficulty |
|-------|----------|-------|------|-------------------|
| Pre-flight | 3 days | Staging | Low | Easy |
| Control Plane | 2 days | All CPs | Low | Moderate |
| CPU Services | 3 days | 1,000 nodes | Low | Easy |
| T4 Dev | 3 days | 500 nodes | Low | Easy |
| A100 Inference | 4 days | 1,500 nodes | Medium | Easy |
| H100 Training | 8 days | 2,000 nodes | High | **Very Hard** |
| Validation | 2 days | Full fleet | Low | N/A |

**Total Duration:** 25 days (5 weeks)

## Success Criteria

- [ ] All 5,000 nodes successfully upgraded to GKE 1.32
- [ ] Zero data loss across all workload types
- [ ] Training throughput within 5% of pre-upgrade baseline
- [ ] Inference latency within 5% of pre-upgrade baseline  
- [ ] No prolonged service disruptions (>30 min)
- [ ] All GPU drivers compatible and performing normally
- [ ] Training teams can resume full multi-day campaigns

---

**Next Steps:**
1. Socialize this plan with ML/AI teams for training campaign coordination
2. Verify GPU surge capacity availability with Cloud Customer Care
3. Set up monitoring dashboards for upgrade progress tracking
4. Schedule staging environment validation (Phase 1)

**Key Decision Point:** After Phase 1 staging validation, re-assess risk and confirm go/no-go for production phases.