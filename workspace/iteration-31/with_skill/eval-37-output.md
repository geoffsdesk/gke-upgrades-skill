# GKE AI/ML Platform Upgrade Plan: 1.31 → 1.32

**Cluster:** AI/ML Platform (5,000 nodes total)  
**Current:** 1.31.x → **Target:** 1.32.x  
**Priority:** Training continuity > Inference availability > Dev/Services

## Executive Summary

This phased upgrade minimizes disruption to revenue-generating training and inference workloads by:
1. Starting with lowest-risk pools (CPU services, dev T4s)
2. Upgrading inference during low-traffic periods with gradual capacity transitions
3. Protecting training workloads with maintenance exclusions until scheduled gaps

**Total estimated duration:** 3-4 weeks with parallel execution

---

## Phase 1: Foundation & Low-Risk Pools (Week 1)

### 1.1 Control Plane Upgrade
**Timing:** Weekend maintenance window  
**Impact:** Brief API unavailability (~5 minutes), no workload disruption

```bash
# Pre-flight validation
gcloud container clusters describe AI-ML-CLUSTER \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].version)"

kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Control plane upgrade
gcloud container clusters upgrade AI-ML-CLUSTER \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.LATEST

# Validation
kubectl get pods -n kube-system
kubectl get nodes  # Verify API connectivity
```

### 1.2 CPU Services Pool (1,000 nodes)
**Strategy:** Surge with 5% maxSurge for faster completion  
**Risk:** Low - stateless services with load balancing

```bash
# Configure surge settings
gcloud container node-pools update services-cpu-pool \
  --cluster AI-ML-CLUSTER \
  --zone ZONE \
  --max-surge-upgrade 50 \
  --max-unavailable-upgrade 0

# Upgrade
gcloud container node-pools upgrade services-cpu-pool \
  --cluster AI-ML-CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.x-gke.LATEST
```

### 1.3 T4 Development Pool (500 nodes)
**Strategy:** maxUnavailable mode (GPU constraint assumption)  
**Risk:** Low - development workloads, interruptible

```bash
# GPU pools: maxUnavailable is primary lever (assume no surge capacity)
gcloud container node-pools update t4-dev-pool \
  --cluster AI-ML-CLUSTER \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2

gcloud container node-pools upgrade t4-dev-pool \
  --cluster AI-ML-CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.x-gke.LATEST
```

**Validation checkpoint:**
- All pools at 1.32.x
- No degraded services
- GPU driver compatibility confirmed for T4s

---

## Phase 2: A100 Inference Pools (Week 2-3)

### 2.1 Pre-inference Preparation

**Staging validation (CRITICAL):**
```bash
# Create staging A100 pool at target version
gcloud container node-pools create a100-inference-staging \
  --cluster AI-ML-CLUSTER \
  --zone ZONE \
  --machine-type a2-highgpu-1g \
  --num-nodes 3 \
  --cluster-version 1.32.x-gke.LATEST
```

**Test matrix:**
- [ ] Model loading (TensorRT, PyTorch, JAX)
- [ ] CUDA version compatibility (1.32 may change CUDA)
- [ ] Inference latency benchmarks
- [ ] GPU utilization metrics
- [ ] Driver compatibility with A100

### 2.2 A100 Inference Upgrade Strategy

**Recommended:** Autoscaled blue-green to minimize inference latency spikes  
**Alternative:** Drain-first surge if blue-green capacity unavailable

**Option A - Autoscaled Blue-Green (preferred for inference):**
```bash
# Enable autoscaling on A100 inference pool
gcloud container node-pools update a100-inference-pool \
  --cluster AI-ML-CLUSTER \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 1400 \
  --total-max-nodes 1600

# Configure autoscaled blue-green
gcloud container node-pools update a100-inference-pool \
  --cluster AI-ML-CLUSTER \
  --zone ZONE \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

**Option B - Drain-first Surge (if capacity constrained):**
```bash
gcloud container node-pools update a100-inference-pool \
  --cluster AI-ML-CLUSTER \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 3  # Higher for faster completion

gcloud container node-pools upgrade a100-inference-pool \
  --cluster AI-ML-CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.x-gke.LATEST
```

### 2.3 Inference Upgrade Execution

**Timing:** Execute during lowest inference traffic (typically 2-6 AM PST)

**Monitoring during upgrade:**
```bash
# Monitor node transition
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=a100-inference-pool -o wide'

# Track inference pod distribution
kubectl get pods -l workload-type=inference -o wide --sort-by='.spec.nodeName'

# Monitor service latency
# (Your monitoring stack - Prometheus, Cloud Monitoring)
```

**Estimated duration:** 24-48 hours for 1,500 nodes with parallelism limit (~20 nodes)

---

## Phase 3: H100 Training Pools (Week 4)

### 3.1 Training Window Coordination

**CRITICAL:** Coordinate with ML teams for training job scheduling gaps

**Pre-upgrade maintenance exclusion:**
```bash
# Block node upgrades during active training
gcloud container clusters update AI-ML-CLUSTER \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-start-time "2024-XX-XXTXX:XX:XXZ" \
  --add-maintenance-exclusion-end-time "2024-XX-XXTXX:XX:XXZ" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### 3.2 H100 Pool Upgrade Strategy

**Strategy:** Drain-first with extended grace periods  
**Assumption:** H100 reservations likely have no surge capacity

```bash
# Conservative settings for training pools
gcloud container node-pools update h100-training-pool \
  --cluster AI-ML-CLUSTER \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1  # One node at a time for safety
```

### 3.3 Training Job Protection Workflow

**Pre-upgrade steps:**
1. **Pause new training submissions** 2 hours before upgrade
2. **Verify checkpoint status** of all running jobs
3. **Coordinate with researchers** for natural stopping points

**Upgrade execution:**
```bash
# Remove maintenance exclusion when ready
gcloud container clusters update AI-ML-CLUSTER \
  --zone ZONE \
  --remove-maintenance-exclusion training-protection

# Upgrade H100 pool
gcloud container node-pools upgrade h100-training-pool \
  --cluster AI-ML-CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.x-gke.LATEST
```

**Post-upgrade validation:**
- [ ] All training pods rescheduled successfully
- [ ] GPUDirect/RDMA topology intact (if applicable)
- [ ] Checkpointing/resumption working
- [ ] Multi-node training communication functional

---

## Risk Mitigation & Rollback Plans

### GPU Driver Compatibility
**Risk:** CUDA version changes between 1.31 → 1.32 breaking models
**Mitigation:** Staging validation mandatory before each GPU pool upgrade
**Rollback:** Create new pools at 1.31, migrate workloads, delete upgraded pools

### Capacity Constraints  
**Risk:** Insufficient quota for surge nodes on GPU pools
**Solution:** Drain-first strategy (`maxSurge=0, maxUnavailable=N`)
**Monitoring:** Track reservation utilization before surge attempts

### Training Job Disruption
**Risk:** Multi-day training runs interrupted
**Mitigation:** 
- Maintenance exclusions during active campaigns
- Coordinate with ML teams for natural gaps
- Verify checkpointing works before upgrade

### Inference Latency Spikes
**Risk:** Customer-facing latency during A100 upgrades
**Mitigation:**
- Autoscaled blue-green keeps old pool serving during transition
- Execute during low-traffic periods
- Staged rollout if multiple inference pools

---

## Monitoring & Validation

### Key Metrics During Upgrade
```bash
# Node readiness
kubectl get nodes | grep -c Ready

# Pod distribution across versions
kubectl get pods -A -o wide | grep gpu | head -20

# GPU utilization
# (Your GPU monitoring - nvidia-smi, DCGM, etc.)

# Training job status
kubectl get pods -l workload-type=training -o jsonpath='{.items[*].status.phase}' | tr ' ' '\n' | sort | uniq -c
```

### Post-Phase Validation Checklist
- [ ] All nodes at target version
- [ ] No CrashLoopBackOff pods
- [ ] GPU drivers functional
- [ ] Model loading successful
- [ ] Inference latency within baseline
- [ ] Training jobs resuming correctly
- [ ] No PVC attachment issues

---

## Timeline Summary

| Phase | Duration | Pools | Risk | Parallel Execution |
|-------|----------|-------|------|-------------------|
| **Phase 1** | Week 1 | Control plane, CPU services (1K), T4 dev (500) | Low | Yes |
| **Phase 2** | Week 2-3 | A100 inference (1.5K) | Medium | No - single pool |
| **Phase 3** | Week 4 | H100 training (2K) | High | No - coordinate with ML teams |

**Critical Path:** H100 training pools due to coordination requirements and single-node-at-a-time upgrade speed.

---

## Emergency Procedures

### Stuck Upgrade Recovery
```bash
# Check operations status
gcloud container operations list --cluster AI-ML-CLUSTER --zone ZONE

# Common fixes
kubectl get pdb -A | grep -v "ALLOWED DISRUPTIONS.*[1-9]"  # Find restrictive PDBs
kubectl get pods -A | grep Terminating  # Find stuck terminating pods
```

### Rollback Decision Matrix
- **Phase 1 issues:** Low impact, retry after fixes
- **Phase 2 issues:** Customer impact, prioritize fast recovery
- **Phase 3 issues:** Coordinate with ML teams, may need to pause training

### Contact Escalation
- **Immediate:** Platform SRE team
- **Training issues:** ML Engineering leads
- **GKE issues:** Cloud Customer Care with cluster details

This upgrade plan balances the unique constraints of AI/ML workloads while maintaining service availability and training continuity. The phased approach allows for validation at each step and minimizes blast radius if issues arise.