# GKE AI/ML Fleet Upgrade Plan: 1.31 → 1.32
**Scale:** 5,000 nodes across mixed AI/ML workloads  
**Priority:** Training continuity (H100) + inference availability (A100)

## Executive Summary

This plan phases the upgrade across 4 weeks to minimize disruption to revenue-generating workloads:
- **Week 1:** Dev/services (low-risk validation)
- **Week 2:** Inference (A100) with autoscaled blue-green
- **Week 3:** Training gap window for H100 upgrade
- **Week 4:** Final validation and documentation

**Critical constraint:** H100 training pools will require a planned training gap due to GPU upgrade limitations.

---

## Phase 1: Development & Services (Week 1)
**Target:** 500 T4 dev nodes + 1,000 CPU service nodes  
**Risk:** Low — dev workloads are restart-tolerant

### Pre-Phase Setup
```bash
# Configure maintenance window for all clusters (off-peak hours)
gcloud container clusters update AI-PLATFORM-CLUSTER \
  --region us-central1 \
  --maintenance-window-start "2024-02-03T02:00:00Z" \
  --maintenance-window-duration 6h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Add "no minor or node upgrades" exclusion to protect training/inference during dev phase
gcloud container clusters update AI-PLATFORM-CLUSTER \
  --region us-central1 \
  --add-maintenance-exclusion-name "protect-prod-during-dev" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-start-time "2024-02-03T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-02-10T00:00:00Z"
```

### Day 1-2: Control Plane Upgrade
```bash
# Upgrade control plane first (required before node pools)
gcloud container clusters upgrade AI-PLATFORM-CLUSTER \
  --region us-central1 \
  --master \
  --cluster-version 1.32.X-gke.LATEST

# Validation (~30 min after completion)
kubectl get pods -n kube-system
kubectl get --raw /healthz
```

### Day 3-4: T4 Dev Pool (Surge Strategy)
**Strategy:** Surge upgrade with higher parallelism — dev workloads tolerate interruption
```bash
# Configure surge settings for speed
gcloud container node-pools update t4-dev-pool \
  --cluster AI-PLATFORM-CLUSTER \
  --region us-central1 \
  --max-surge-upgrade 25 \
  --max-unavailable-upgrade 0

# Upgrade
gcloud container node-pools upgrade t4-dev-pool \
  --cluster AI-PLATFORM-CLUSTER \
  --region us-central1 \
  --cluster-version 1.32.X-gke.LATEST

# Monitor progress
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=t4-dev-pool -o wide'
```

### Day 5-7: CPU Services Pool (Conservative Surge)
**Strategy:** Conservative surge to maintain service availability
```bash
# Configure conservative surge for services
gcloud container node-pools update cpu-services-pool \
  --cluster AI-PLATFORM-CLUSTER \
  --region us-central1 \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 0

# Upgrade
gcloud container node-pools upgrade cpu-services-pool \
  --cluster AI-PLATFORM-CLUSTER \
  --region us-central1 \
  --cluster-version 1.32.X-gke.LATEST
```

**Phase 1 Validation:**
- [ ] All dev workloads resuming normally
- [ ] Service endpoints responding
- [ ] GPU driver compatibility confirmed on T4s with 1.32
- [ ] No deprecated API issues in application logs

---

## Phase 2: A100 Inference (Week 2)
**Target:** 1,500 A100 GPU nodes  
**Strategy:** Autoscaled blue-green to minimize inference downtime

### Pre-Phase: GPU Driver Validation
```bash
# Create staging A100 node pool with 1.32 for driver testing
gcloud container node-pools create a100-staging-132 \
  --cluster AI-PLATFORM-CLUSTER \
  --region us-central1 \
  --machine-type a2-ultragpu-1g \
  --accelerator type=nvidia-a100-80gb,count=1 \
  --cluster-version 1.32.X-gke.LATEST \
  --num-nodes 2

# Deploy representative inference workload and validate
kubectl apply -f inference-validation-job.yaml
# Confirm CUDA version compatibility, model loading, throughput
```

### A100 Pool Upgrade (Autoscaled Blue-Green)
**Rationale:** Autoscaled blue-green keeps inference serving while new nodes warm up
```bash
# Enable autoscaling on A100 inference pool
gcloud container node-pools update a100-inference-pool \
  --cluster AI-PLATFORM-CLUSTER \
  --region us-central1 \
  --enable-autoscaling \
  --total-min-nodes 1400 \
  --total-max-nodes 1600

# Configure autoscaled blue-green upgrade
gcloud container node-pools update a100-inference-pool \
  --cluster AI-PLATFORM-CLUSTER \
  --region us-central1 \
  --strategy BLUE_GREEN \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.20,blue-green-full-batch-timeout=3600s

# Initiate upgrade
gcloud container node-pools upgrade a100-inference-pool \
  --cluster AI-PLATFORM-CLUSTER \
  --region us-central1 \
  --cluster-version 1.32.X-gke.LATEST
```

**Monitoring during A100 upgrade:**
```bash
# Track inference latency and throughput
kubectl top pods -l app=inference --containers
# Monitor for GPU memory allocation failures
kubectl get events -n inference-namespace --field-selector reason=FailedMount
```

**Phase 2 Validation:**
- [ ] Inference latency within 5% of baseline
- [ ] No model loading failures post-upgrade
- [ ] A100 GPU utilization restored to pre-upgrade levels
- [ ] Blue pool fully deleted after soak period

---

## Phase 3: H100 Training (Week 3)
**Target:** 2,000 H100 GPU nodes  
**Strategy:** Coordinated training gap + parallel host maintenance

### Critical Pre-Phase: Training Campaign Coordination
**⚠️ TRAINING TEAMS MUST CHECKPOINT AND PAUSE JOBS ⚠️**

```bash
# Remove exclusion to allow H100 upgrade
gcloud container clusters update AI-PLATFORM-CLUSTER \
  --region us-central1 \
  --remove-maintenance-exclusion-name "protect-prod-during-dev"

# Add new exclusion for inference protection during training upgrade
gcloud container clusters update AI-PLATFORM-CLUSTER \
  --region us-central1 \
  --add-maintenance-exclusion-name "protect-inference-during-training" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-start-time "2024-02-17T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-02-24T00:00:00Z"
```

### H100 Training Pool Strategy
**Important:** H100 nodes likely have fixed GPU reservations with NO surge capacity. Use maxUnavailable approach.

```bash
# Configure for drain-first upgrade (no surge capacity assumed)
gcloud container node-pools update h100-training-pool \
  --cluster AI-PLATFORM-CLUSTER \
  --region us-central1 \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 20

# Coordinate with AI Host Maintenance for firmware updates
# Apply maintenance label to trigger parallel host maintenance
kubectl label nodes -l cloud.google.com/gke-nodepool=h100-training-pool \
  cloud.google.com/perform-maintenance=true

# Initiate node pool upgrade
gcloud container node-pools upgrade h100-training-pool \
  --cluster AI-PLATFORM-CLUSTER \
  --region us-central1 \
  --cluster-version 1.32.X-gke.LATEST
```

**Parallel strategy rationale:** Training workloads can tolerate full restart. Parallel maintenance minimizes total wall-clock time (~4-6 hours) vs. sequential days/weeks.

### GPUDirect/RDMA Validation (Critical for H100)
```bash
# After upgrade, verify RDMA topology preserved
kubectl exec -it training-pod -- nvidia-smi topo -m
# Confirm GPUDirect-TCPX still functional
kubectl exec -it training-pod -- python -c "import jax; print(jax.devices())"
```

**Phase 3 Validation:**
- [ ] All 2,000 H100 nodes at version 1.32
- [ ] Multi-node training jobs resuming successfully
- [ ] GPUDirect/RDMA connectivity verified
- [ ] Compact placement preserved in same zones
- [ ] Training checkpoint restore working correctly

---

## Phase 4: Fleet Validation & Ops (Week 4)

### Final Cluster Health Check
```bash
# Comprehensive cluster status
gcloud container clusters describe AI-PLATFORM-CLUSTER \
  --region us-central1 \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version, nodePools[].instanceGroupUrls[0].segment(-1))"

# Verify all nodes healthy
kubectl get nodes --no-headers | wc -l  # Should equal 5,000
kubectl get nodes | grep -v Ready  # Should be empty

# Check workload health across all node pools
kubectl get pods -A | grep -v Running | grep -v Succeeded
```

### Performance Validation
- [ ] **Training throughput:** Compare H100 training steps/sec pre vs post-upgrade
- [ ] **Inference latency:** A100 p95 latency within 5% of baseline  
- [ ] **Development velocity:** T4 dev environments fully functional
- [ ] **Service availability:** CPU services maintaining SLA

### Documentation & Lessons Learned
```bash
# Capture final state for next upgrade cycle
gcloud container clusters get-upgrade-info AI-PLATFORM-CLUSTER \
  --region us-central1 \
  --format="yaml"
```

---

## Risk Mitigation & Rollback

### GPU Pool Rollback Strategy
**Critical limitation:** GPU pools cannot be rolled back in-place. Rollback requires new pool creation.

```bash
# Emergency rollback: Create new pool at 1.31
gcloud container node-pools create POOL-NAME-rollback-131 \
  --cluster AI-PLATFORM-CLUSTER \
  --region us-central1 \
  --machine-type MACHINE_TYPE \
  --accelerator type=GPU_TYPE,count=GPU_COUNT \
  --cluster-version 1.31.X-gke.PREVIOUS \
  --num-nodes TARGET_SIZE

# Migrate workloads, then delete failed pool
```

### Training Continuity Safeguards
- **Checkpoint frequency:** Increase to every 30 minutes during upgrade week
- **Job queuing:** Pause new job submissions 24h before H100 upgrade
- **Emergency contact:** 24/7 on-call during Phase 3 for training teams

### Monitoring & Alerting
```bash
# Critical metrics to monitor throughout
# - GPU utilization per pool
# - Training job completion rate
# - Inference request success rate
# - Node ready/not-ready count per pool
# - Pod restart frequency
```

---

## Timeline Summary

| Week | Phase | Target | Downtime | Risk Level |
|------|-------|--------|----------|------------|
| 1 | Dev/Services | 1,500 nodes | Minimal | Low |
| 2 | Inference (A100) | 1,500 nodes | ~30min per batch | Medium |
| 3 | Training (H100) | 2,000 nodes | 4-6 hours total | High |
| 4 | Validation | All pools | None | Low |

**Total estimated duration:** 4 weeks  
**Maximum concurrent disruption:** Single node pool at a time  
**Training gap required:** 1 day (Phase 3 only)

This plan prioritizes revenue-generating inference workloads and coordinates around training campaigns to minimize AI/ML platform disruption while ensuring the entire 5,000-node fleet reaches Kubernetes 1.32 safely.