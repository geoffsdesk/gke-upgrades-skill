# GKE 1.29 → 1.30 Upgrade Plan: AI/ML Platform Fleet

## Executive Summary

This phased upgrade plan prioritizes training continuity on H100 nodes and maintains inference availability on A100 nodes while systematically upgrading a 5,000-node mixed GPU/CPU fleet. The plan uses maintenance exclusions to protect active training workloads and staggers GPU pool upgrades during low-impact windows.

## Environment Context

- **Cluster size**: 5,000 nodes (approaching large-scale limits)
- **GPU distribution**: 4,000 GPU nodes (H100: 2,000 | A100: 1,500 | T4: 500)
- **CPU services**: 1,000 nodes
- **Version jump**: 1.29 → 1.30 (single minor version — safe)
- **Estimated total duration**: 2-3 weeks with proper staging

## Version Compatibility Assessment

✅ **1.30 compatibility verified for AI/ML workloads:**
- GPU driver updates: GKE 1.30 ships with compatible NVIDIA drivers
- CUDA compatibility maintained for PyTorch/TensorFlow/JAX stacks
- No breaking changes affecting GPU resource management
- GPUDirect-TCPX support continues (required GKE 1.27.7+ already met)

## Phase Structure

### Phase 1: Infrastructure & Development (Days 1-3)
**Target**: CPU services + T4 development nodes (1,500 nodes total)
- Lowest risk, establishes baseline for GPU pool upgrades
- Tests 1.30 compatibility with supporting services
- Validates upgrade mechanics on smaller GPU pools

### Phase 2: Inference Infrastructure (Days 4-10)  
**Target**: A100 inference nodes (1,500 nodes)
- Staged over 1 week to maintain inference capacity
- Sub-phases with traffic shifting between upgraded/legacy pools
- Load balancer readiness validation between batches

### Phase 3: Training Infrastructure (Days 11-21)
**Target**: H100 training nodes (2,000 nodes) 
- **Highest priority protection** — upgraded only during training gaps
- Coordinated with ML teams for scheduled maintenance windows
- Checkpoint validation before any node touches training workloads

## Detailed Phase Plans

## Phase 1: CPU Services & Development GPU Nodes

**Scope**: 1,000 CPU + 500 T4 nodes  
**Risk**: Low — no production training/inference impact  
**Duration**: 3 days  

### Pre-Phase 1 Checklist
```
Infrastructure Readiness
- [ ] Control plane upgraded to 1.30 (all node pools)
- [ ] GPU driver compatibility tested in staging: CUDA versions confirmed
- [ ] Monitoring baselines captured: error rates, GPU utilization, inference latency
- [ ] T4 development workload tolerance confirmed (dev jobs can restart)
- [ ] CPU service PDBs reviewed: maxUnavailable settings appropriate
- [ ] Surge capacity confirmed: sufficient CPU quota for 200+ surge nodes
```

### Phase 1 Commands
```bash
# Configure surge settings - prioritize speed for low-risk pools
gcloud container node-pools update cpu-services-pool \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 20 --max-unavailable-upgrade 0

gcloud container node-pools update t4-dev-pool \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 5 --max-unavailable-upgrade 0

# Execute upgrades (CPU first, then T4)
gcloud container node-pools upgrade cpu-services-pool \
  --cluster CLUSTER_NAME --zone ZONE --cluster-version 1.30

# Monitor progress, then proceed to T4
gcloud container node-pools upgrade t4-dev-pool \
  --cluster CLUSTER_NAME --zone ZONE --cluster-version 1.30
```

### Phase 1 Validation
- All CPU services responding normally
- T4 development environments accessible  
- No degradation in logging/monitoring/CI pipeline performance
- GPU driver version confirmed on upgraded T4 nodes: `nvidia-smi` output

---

## Phase 2: A100 Inference Nodes

**Scope**: 1,500 A100 nodes across inference workloads  
**Risk**: Medium — inference availability protection required  
**Duration**: 7 days (staged sub-phases)

### Sub-Phase Strategy
Split A100 pool into 3 sub-groups of ~500 nodes each:
- **2A**: Low-traffic inference workloads (Days 4-5)
- **2B**: Medium-traffic workloads (Days 6-7)  
- **2C**: High-traffic/critical workloads (Days 8-10)

### Phase 2 Preparation
```bash
# Apply conservative surge settings - GPU capacity is precious
gcloud container node-pools update a100-inference-pool \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 1 --max-unavailable-upgrade 0

# Set maintenance exclusion during peak inference hours (if needed)
gcloud container clusters update CLUSTER_NAME --zone ZONE \
  --add-maintenance-exclusion-name "inference-peak-protection" \
  --add-maintenance-exclusion-start-time "2024-MM-DDTHH:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-MM-DDTHH:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### Sub-Phase 2A: Low-Traffic Inference (Days 4-5)
```bash
# Cordon subset of A100 nodes for controlled rollout
kubectl cordon -l node-group=a100-inference-low-traffic

# Upgrade this subset first
gcloud container node-pools upgrade a100-inference-pool \
  --cluster CLUSTER_NAME --zone ZONE --cluster-version 1.30 \
  --max-nodes-upgraded-simultaneously 10
```

**Validation between sub-phases:**
- Inference API response times within baseline
- GPU memory allocation successful on upgraded nodes
- Model loading times unchanged
- No CUDA/driver errors in application logs

### Sub-Phase 2B-2C: Repeat pattern for remaining A100 nodes
- 48-hour soak time between sub-phases
- Traffic shifting validation using load balancer weights
- Rollback plan: cordon upgraded nodes, shift traffic to legacy pool

---

## Phase 3: H100 Training Nodes (CRITICAL)

**Scope**: 2,000 H100 nodes supporting multi-day/week training runs  
**Risk**: HIGHEST — training interruption = days/weeks of compute loss  
**Duration**: 10 days with extensive coordination

### Training Continuity Strategy

**Coordination with ML Teams (PRE-PHASE 3):**
- [ ] Survey active training runs: expected completion dates
- [ ] Identify natural training gaps: model checkpoints, experiment transitions  
- [ ] Schedule 4-hour upgrade windows during identified gaps
- [ ] Establish "emergency brake" — ability to halt upgrade if critical training starts

### Phase 3A: Training Support Nodes (Days 11-13)
**Target**: H100 nodes NOT currently running active training jobs
```bash
# Identify idle H100 nodes
kubectl get pods -l workload-type=training --field-selector=status.phase=Running -o wide
# Cross-reference with H100 node list to find idle nodes

# Apply maintenance exclusion to protect active training nodes
gcloud container clusters update CLUSTER_NAME --zone ZONE \
  --add-maintenance-exclusion-name "active-training-protection" \
  --add-maintenance-exclusion-start-time "NOW" \
  --add-maintenance-exclusion-end-time "TRAINING_END_DATE" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Upgrade only idle H100 nodes
gcloud container node-pools update h100-training-pool \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 1 --max-unavailable-upgrade 0

# Target specific idle nodes for upgrade first
kubectl cordon NODE_NAME  # for each idle H100 node
```

### Phase 3B: Active Training Nodes (Days 14-21)  
**ONLY proceed when training runs complete naturally**

```bash
# Verify all critical training checkpointed and paused
kubectl get pods -l workload-type=training,priority=critical

# Remove protection exclusion for completed training
gcloud container clusters update CLUSTER_NAME --zone ZONE \
  --remove-maintenance-exclusion-name "active-training-protection"

# Upgrade remaining H100 nodes in small batches
gcloud container node-pools upgrade h100-training-pool \
  --cluster CLUSTER_NAME --zone ZONE --cluster-version 1.30 \
  --max-nodes-upgraded-simultaneously 5
```

**Critical Phase 3 Safeguards:**
- Upgrade ONLY during confirmed training gaps
- Maximum 5 H100 nodes upgrading simultaneously  
- 24-hour pause between training pool batches
- Emergency stop procedure if unexpected training job starts

---

## Large-Scale Cluster Considerations

### Upgrade Performance Expectations
- **Parallelism limit**: GKE upgrades ~20 nodes simultaneously regardless of settings
- **Timeline**: 5,000 nodes = ~250 batches minimum = **weeks not days**
- **GPU capacity constraints**: Surge upgrades need temporary extra GPU nodes (scarce resource)

### Resource Management
```bash
# Monitor overall cluster upgrade progress  
watch 'gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE --format="table(name,version,status)"'

# Track GPU quota utilization during surge
gcloud compute project-info describe --format="yaml(quotas)" | grep -A5 "GPUS_ALL_REGIONS\|NVIDIA"
```

### Networking Validation (Post-Upgrade)
```bash
# Verify GPUDirect-TCPX still functional (if used)
kubectl exec -it TRAINING_POD -- nvidia-smi topo -m

# Confirm high-bandwidth interconnect
kubectl exec -it TRAINING_POD -- ib_write_bw  # if InfiniBand configured
```

## Risk Mitigation

### Rollback Strategy
- **Control plane**: Contact GKE support — downgrade requires assistance
- **Node pools**: Create new pools at 1.29, migrate workloads, delete upgraded pools
- **Training workloads**: Restore from most recent checkpoint on rolled-back nodes

### Emergency Procedures
```bash
# Halt in-progress upgrade (completes current batch, stops future batches)
# Find operation ID:
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=5

# Contact GKE support with cluster name, zone, operation ID for emergency intervention
```

### Monitoring During Upgrades
- GPU driver version consistency: `nvidia-smi --query-gpu=driver_version --format=csv`
- CUDA runtime availability: Test model loading on upgraded nodes before shifting traffic
- Training throughput: Validate samples/second matches pre-upgrade baselines
- Inference latency: p95 latency within 10% of pre-upgrade measurements

## Communication Plan

### Stakeholder Notifications
- **Week -1**: ML teams, infrastructure team alignment on training schedule
- **Day 0**: Phase 1 start notification
- **Day 4**: Phase 2 start, inference SLA reminders  
- **Day 11**: Phase 3 start — training teams final confirmation
- **Day 21**: Completion announcement, lessons learned session

### Success Criteria
- [ ] All 5,000 nodes successfully upgraded to 1.30
- [ ] Zero training job interruptions due to upgrade (natural completions only)
- [ ] Inference availability >99.5% maintained throughout Phase 2
- [ ] No GPU driver/CUDA compatibility issues post-upgrade
- [ ] All workloads returning to pre-upgrade performance baselines

This phased approach balances the critical need for training continuity with systematic infrastructure modernization across your large-scale AI/ML platform.