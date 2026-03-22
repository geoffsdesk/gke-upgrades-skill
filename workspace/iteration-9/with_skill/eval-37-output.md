# GKE AI/ML Fleet Upgrade Plan: 1.31 → 1.32

**Cluster:** AI/ML Platform  
**Scale:** 5,000 nodes total  
**Current:** 1.31.x  
**Target:** 1.32.x  
**Priority:** Training continuity + inference availability

## Executive Summary

This plan uses a **4-phase approach** over 3-4 weeks, upgrading lowest-risk pools first and protecting active training workloads. GPU pools use `maxUnavailable` strategy (no surge capacity assumed). Training pools upgrade during scheduled gaps only.

## Phase Overview

| Phase | Duration | Node Pools | Strategy | Risk Level |
|-------|----------|------------|----------|------------|
| **1** | Week 1 | CPU services (1,000 nodes) | Surge upgrade | Low |
| **2** | Week 1-2 | T4 dev (500 nodes) | maxUnavailable=2 | Low |
| **3** | Week 2-3 | A100 inference (1,500 nodes) | Rolling batch, maintain capacity | Medium |
| **4** | Week 3-4 | H100 training (2,000 nodes) | Coordinate with training schedule | High |

---

## Pre-Upgrade Preparation

### Version Compatibility
- [ ] Confirm 1.32 available in release channel: `gcloud container get-server-config --zone ZONE --format="yaml(channels)"`
- [ ] Verify GPU driver compatibility (GKE auto-installs drivers matching 1.32 — test CUDA version compatibility)
- [ ] Check training framework compatibility (PyTorch, JAX, TensorFlow) with 1.32 node image
- [ ] Review GKE 1.31→1.32 release notes for AI/ML-specific changes

### Infrastructure Readiness
- [ ] Backup all training checkpoints and model artifacts
- [ ] Configure maintenance windows: **Weekends 00:00-08:00 UTC** for GPU pools
- [ ] Set up "no minor or node upgrades" exclusions for active training pools
- [ ] Verify compact placement policies will preserve RDMA topology post-upgrade
- [ ] Confirm no live GPU/TPU reservations will be disrupted

### Monitoring Setup
- [ ] Baseline metrics: GPU utilization, training throughput, inference latency
- [ ] Alert on stuck upgrades (>4h with no node progress)
- [ ] Monitor training job health during exclusion windows

---

## Phase 1: CPU Services Pool (1,000 nodes)
**Timeline:** Week 1 (Mon-Wed)  
**Risk:** Low - stateless services, standard surge capacity

### Configuration
```bash
# Control plane upgrade first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest

# CPU pool: aggressive surge for speed
gcloud container node-pools update cpu-services \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 10 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade cpu-services \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

### Validation
- [ ] All 1,000 CPU nodes at 1.32
- [ ] API gateway, monitoring, logging services healthy
- [ ] No impact to GPU workloads (services only)
- [ ] **Soak time:** 24h before proceeding to Phase 2

---

## Phase 2: T4 Development Pool (500 nodes)
**Timeline:** Week 1-2 (Thu-Mon)  
**Risk:** Low - development workloads, can tolerate restarts

### Strategy
T4 nodes typically have limited surge capacity. Use `maxUnavailable` as primary lever.

```bash
# T4 dev pool: faster batch upgrades
gcloud container node-pools update t4-dev \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 3

gcloud container node-pools upgrade t4-dev \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

### Validation
- [ ] All 500 T4 nodes upgraded
- [ ] Development notebooks and experiments functional
- [ ] GPU driver version compatible with dev frameworks
- [ ] **Soak time:** 48h before Phase 3

---

## Phase 3: A100 Inference Pool (1,500 nodes) 
**Timeline:** Week 2-3  
**Risk:** Medium - must maintain serving capacity

### Strategy
**Rolling batch upgrade** maintaining 80% capacity throughout. A100 inference typically serves live traffic.

```bash
# Conservative settings to maintain serving capacity
gcloud container node-pools update a100-inference \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2

# Coordinate upgrade timing with traffic patterns
gcloud container node-pools upgrade a100-inference \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

### Monitoring During Phase 3
- [ ] Inference latency (p95) stays within 20% of baseline
- [ ] No customer-facing errors from capacity reduction
- [ ] Load balancer properly routing around upgrading nodes
- [ ] Model serving pods reschedule successfully

### Validation
- [ ] All 1,500 A100 nodes upgraded  
- [ ] Inference throughput restored to pre-upgrade levels
- [ ] GPU memory utilization normal
- [ ] **Soak time:** 72h before final phase

---

## Phase 4: H100 Training Pool (2,000 nodes)
**Timeline:** Week 3-4  
**Risk:** High - large-scale training jobs, expensive restarts

### Pre-Phase 4 Coordination
**Critical:** Coordinate with ML teams 1 week before Phase 4.

- [ ] **Training schedule review:** Identify training job gaps (typically weekends)
- [ ] **Checkpoint verification:** Ensure all active jobs have recent checkpoints
- [ ] **Job pause coordination:** Plan controlled pause for long-running jobs
- [ ] **Capacity verification:** Confirm no surge GPU quota available (standard for H100)

### Strategy
**Maintenance exclusion + controlled upgrade windows**

```bash
# Apply "no minor or node upgrades" exclusion during active training
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time "2024-12-15T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# During scheduled gap: remove exclusion and upgrade in batches
# Conservative batch size for H100
gcloud container node-pools update h100-training \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

# Execute during weekend training gap
gcloud container node-pools upgrade h100-training \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

### H100-Specific Considerations
- **Upgrade duration:** 2,000 nodes at ~20 parallel = 100+ batches. Plan 12-24h total.
- **RDMA topology:** Verify replacement nodes maintain compact placement for multi-node training
- **Training restart protocol:** Jobs resume from checkpoints, not from scratch
- **GPU driver testing:** H100 CUDA compatibility most critical — verify in dev first

### Validation
- [ ] All 2,000 H100 nodes at 1.32
- [ ] Multi-node training jobs successfully restart from checkpoints
- [ ] RDMA/GPUDirect interconnect functioning (if applicable)  
- [ ] Training throughput matches pre-upgrade baseline
- [ ] No GPU memory or driver issues

---

## Risk Mitigation

### Training Job Protection
- **Active exclusions:** Keep "no minor or node upgrades" on training pools until scheduled gaps
- **Checkpoint frequency:** Increase checkpoint frequency during upgrade window
- **Job monitoring:** Real-time alerts on training job failures during Phase 4

### Inference SLA Protection  
- **Capacity monitoring:** Maintain 80%+ inference capacity during Phase 3
- **Circuit breakers:** Configure load balancers to handle temporary capacity reduction
- **Rollback plan:** Keep previous node pool available for emergency rollback

### Fleet-Level Safeguards
- **Batch limits:** Never upgrade >500 nodes simultaneously across all pools
- **Progress gates:** 24-48h soak time between phases, with health validation
- **Emergency stops:** Process to pause upgrades if critical issues detected

---

## Rollback Procedures

### Control Plane Rollback
Control plane minor version rollback requires GKE support. Patch rollback is customer-initiated:
```bash
# Emergency: contact Google Cloud Support with cluster details
```

### Node Pool Rollback
**GPU pools:** Create new pool at 1.31, migrate workloads, delete upgraded pool.
```bash
# Example for critical rollback
gcloud container node-pools create h100-training-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.latest \
  --num-nodes 2000 \
  --machine-type a3-highgpu-8g

# Cordon upgraded pool, migrate training jobs
kubectl cordon -l cloud.google.com/gke-nodepool=h100-training
```

---

## Timeline Summary

```
Week 1:  [CPU Services] → [T4 Dev starts]
Week 2:  [T4 Dev completes] → [A100 Inference]  
Week 3:  [A100 completes] → [H100 prep & coordination]
Week 4:  [H100 Training] → [Final validation]
```

**Total Duration:** 3-4 weeks  
**Business Impact:** Minimal - training jobs protected, inference capacity maintained  
**Rollback Window:** Available through Week 2, limited after H100 upgrade

This plan balances upgrade velocity with AI/ML workload protection, ensuring your training investments are preserved while maintaining inference SLAs throughout the process.