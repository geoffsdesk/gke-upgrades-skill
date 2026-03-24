# GKE 1.31→1.32 Upgrade Plan: AI/ML Platform (5,000 nodes)

## Executive Summary

**Cluster:** AI/ML Platform | **Mode:** Standard | **Scale:** 5,000 nodes
**Current:** 1.31.x | **Target:** 1.32.x | **Priority:** Training continuity > Inference availability

This plan phases the upgrade across 4 weeks to minimize training disruption and maintain inference capacity. GPU pools use `maxUnavailable` strategies due to fixed reservations.

## Fleet Overview & Constraints

| Pool Type | Node Count | Primary Constraint | Upgrade Strategy |
|-----------|------------|-------------------|------------------|
| H100 Training | 2,000 | Multi-day jobs, no checkpointing interruption | Maintenance exclusion during campaigns |
| A100 Inference | 1,500 | Serving availability, reservation-bound | Rolling maxUnavailable=2-4 |
| T4 Development | 500 | Lower priority, flexible | Standard surge |
| CPU Services | 1,000 | Stateless, auto-scaling | Standard surge |

**Critical assumptions:**
- H100/A100 pools have fixed GPU reservations (no surge capacity)
- Training jobs run 3-7 days continuously
- Inference serves production traffic (99.9% SLA)
- Development workloads are restart-tolerant

## Phase 1: Foundation (Week 1)

### 1.1 Control Plane Upgrades

**All clusters simultaneously** (regional clusters remain available):

```bash
# Two-step upgrade for production safety (rollback window available)
gcloud beta container clusters upgrade CLUSTER_NAME \
  --master \
  --cluster-version 1.32.x-gke.latest \
  --control-plane-soak-duration 24h

# After 24h soak + validation, complete the upgrade
gcloud beta container clusters upgrade CLUSTER_NAME \
  --complete-upgrade
```

**Validation checklist:**
- [ ] API server responds: `kubectl get nodes`
- [ ] System pods healthy: `kubectl get pods -n kube-system`
- [ ] No deprecated API usage: `kubectl get --raw /metrics | grep deprecated`
- [ ] Training jobs unaffected (control plane upgrade doesn't impact running pods)

### 1.2 CPU Services Pool (1,000 nodes) - Low Risk

Stateless services can handle rolling restarts.

```bash
gcloud container node-pools update services-cpu \
  --cluster CLUSTER_NAME \
  --max-surge-upgrade 5% \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade services-cpu \
  --cluster CLUSTER_NAME \
  --cluster-version 1.32.x-gke.latest
```

**Expected duration:** 2-3 days (50 nodes per batch, ~20 batches)

## Phase 2: Development (Week 2)

### 2.1 T4 Development Pool (500 nodes)

Dev workloads are restart-tolerant and lower priority.

```bash
gcloud container node-pools update dev-t4 \
  --cluster CLUSTER_NAME \
  --max-surge-upgrade 10% \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade dev-t4 \
  --cluster CLUSTER_NAME \
  --cluster-version 1.32.x-gke.latest
```

**Expected duration:** 1-2 days (50 nodes per batch, ~10 batches)

**Validation:**
- [ ] Dev jobs reschedule successfully
- [ ] Jupyter notebooks reconnect
- [ ] GPU drivers compatible (T4 typically has good compatibility)

## Phase 3: Inference (Week 3)

### 3.1 A100 Inference Pool (1,500 nodes) - **CRITICAL**

**Strategy:** Rolling `maxUnavailable` to maintain 90%+ serving capacity.

**Pre-upgrade:**
```bash
# Verify no A100 surge capacity available
gcloud compute reservations describe A100_RESERVATION --zone ZONE

# Check inference service health baselines
kubectl top nodes -l node-pool=inference-a100
```

**Configuration:**
```bash
gcloud container node-pools update inference-a100 \
  --cluster CLUSTER_NAME \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4
```

**Execute in maintenance window (3 AM - 6 AM PST):**
```bash
gcloud container node-pools upgrade inference-a100 \
  --cluster CLUSTER_NAME \
  --cluster-version 1.32.x-gke.latest
```

**Expected duration:** 4-5 days (75 batches of 4 nodes, ~20 batch limit)

**Monitoring during upgrade:**
- [ ] Inference QPS maintained >90% of baseline
- [ ] P99 latency <2x baseline
- [ ] No model loading failures on new nodes
- [ ] GPU utilization remains consistent

**PDB protection for inference:**
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: inference-pdb
spec:
  minAvailable: 85%  # Allow 15% disruption
  selector:
    matchLabels:
      app: inference-service
```

## Phase 4: Training (Week 4) - **HIGHEST RISK**

### 4.1 H100 Training Pool (2,000 nodes) - Coordinate with ML Teams

**Pre-upgrade coordination:**
1. **3 days before:** Survey active training jobs, identify checkpoint schedules
2. **1 day before:** Confirm all jobs have recent checkpoints
3. **Upgrade day:** Coordinate with ML teams for job pause/resume

**Strategy:** Rolling `maxUnavailable` with training job coordination.

```bash
# Set maintenance exclusion during active campaigns
gcloud container clusters update CLUSTER_NAME \
  --add-maintenance-exclusion-name "training-campaign-q1" \
  --add-maintenance-exclusion-start-time 2024-01-15T00:00:00Z \
  --add-maintenance-exclusion-end-time 2024-01-21T23:59:59Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**When training jobs complete naturally:**
```bash
gcloud container node-pools update training-h100 \
  --cluster CLUSTER_NAME \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2  # Conservative for $$ hardware
```

**Execute with ML team coordination:**
```bash
# Upgrade in batches during job transitions
gcloud container node-pools upgrade training-h100 \
  --cluster CLUSTER_NAME \
  --cluster-version 1.32.x-gke.latest
```

**Expected duration:** 7-10 days (100 batches of 2 nodes)

**Training-specific validation:**
- [ ] NCCL/RDMA connectivity preserved
- [ ] GPUDirect-TCPX functioning (GKE 1.32 supports this)
- [ ] Compact placement preserved
- [ ] Training throughput within 95% of baseline

## Long-running Training Job Protection

For jobs that cannot be interrupted:

```bash
# Apply to dedicated training node pool
gcloud container clusters update CLUSTER_NAME \
  --add-maintenance-exclusion-name "llm-pretraining-run-47" \
  --add-maintenance-exclusion-start-time 2024-01-10T00:00:00Z \
  --add-maintenance-exclusion-until-end-of-support \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**Alternative approach for extremely long jobs:** Cordon training nodes, wait for natural completion, upgrade empty pool.

## Rollback Strategy

**Control Plane:** Two-step upgrade allows rollback during 24h soak period.

**Node Pools:** Create replacement pools at 1.31 and migrate workloads.

```bash
# Emergency rollback for training
gcloud container node-pools create training-h100-rollback \
  --cluster CLUSTER_NAME \
  --cluster-version 1.31.x-gke.previous \
  --num-nodes 2000 \
  --machine-type a3-highgpu-8g

# Cordon upgraded pool, migrate jobs
kubectl cordon -l cloud.google.com/gke-nodepool=training-h100
```

## Monitoring & Validation

### During Each Phase

**Cluster health:**
```bash
# Node status
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool

# System health
kubectl get pods -n kube-system | grep -v Running

# GPU node registration
kubectl describe nodes -l node-pool=training-h100 | grep nvidia.com/gpu
```

**Workload health:**
```bash
# Training jobs status
kubectl get pods -n training --field-selector=status.phase=Running

# Inference traffic
kubectl top pods -n inference -l app=inference-service
```

### Success Criteria

- [ ] All node pools at 1.32.x
- [ ] Zero training job failures due to upgrade
- [ ] Inference availability >99.5% throughout
- [ ] GPU utilization returns to baseline
- [ ] No performance regressions

## Timeline Summary

| Week | Phase | Pools | Risk | Validation Window |
|------|-------|-------|------|------------------|
| 1 | Control Plane + CPU Services | 1,000 CPU nodes | Low | 3 days |
| 2 | Development | 500 T4 nodes | Low | 2 days |
| 3 | Inference | 1,500 A100 nodes | High | 5 days |
| 4 | Training | 2,000 H100 nodes | Critical | 10 days |

**Total timeline:** 4 weeks with 1-week buffer for training coordination.

## Risk Mitigation

1. **GPU Driver Compatibility:** Test 1.32 in staging with representative workloads
2. **RDMA/Interconnect:** Validate GPUDirect-TCPX on upgraded nodes
3. **Reservation Management:** Monitor quota usage during upgrade
4. **Training Checkpoints:** Enforce checkpoint policy before H100 upgrade
5. **Inference Redundancy:** Ensure load balancer health checks handle node transitions

## Communication Plan

- **T-2 weeks:** Platform team notification, staging validation
- **T-1 week:** ML team coordination, checkpoint verification  
- **T-0:** Daily standup during training phase
- **T+1 week:** Retrospective and lessons learned

This plan balances the critical nature of training workloads with the availability requirements of inference, using GKE's native upgrade strategies optimized for GPU constraints.