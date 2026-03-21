# GKE AI/ML Fleet Upgrade Plan: 1.31 → 1.32

**Cluster:** Mixed AI/ML Platform | **Mode:** Standard | **Current:** 1.31 | **Target:** 1.32
**Total nodes:** 5,000 (2,000 H100 + 1,500 A100 + 500 T4 + 1,000 CPU)

## Phase Sequencing Strategy

**Priority:** Training continuity (H100) > Inference availability (A100) > Dev/services (T4/CPU)

### Phase 1: CPU Services (1,000 nodes) - Low Risk
- **Duration:** 2-3 days
- **Strategy:** Surge upgrade with high parallelism
- **Rationale:** Stateless services with easy rollback, no GPU constraints

### Phase 2: T4 Development (500 nodes) - Medium Risk  
- **Duration:** 1-2 days
- **Strategy:** Surge upgrade during dev hours
- **Rationale:** Test GPU driver compatibility before production GPU pools

### Phase 3: A100 Inference (1,500 nodes) - High Risk
- **Duration:** 3-5 days  
- **Strategy:** Rolling surge with capacity preservation
- **Rationale:** Maintain inference SLA, validate before training pools

### Phase 4: H100 Training (2,000 nodes) - Critical
- **Duration:** 5-7 days
- **Strategy:** Maintenance exclusion → manual upgrade during training gaps
- **Rationale:** Protect multi-day training runs, longest upgrade window

## Detailed Phase Execution

### Phase 1: CPU Services Pool

```bash
# Configure aggressive surge for fast completion
gcloud container node-pools update cpu-services-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 20 \
  --max-unavailable-upgrade 0

# Upgrade control plane first (required order)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest

# Upgrade CPU pool
gcloud container node-pools upgrade cpu-services-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Validation:**
- All service endpoints responding
- No degraded performance metrics
- Gateway/ingress controllers healthy

### Phase 2: T4 Development Pool

```bash
# Conservative surge for GPU nodes (limited capacity assumed)
gcloud container node-pools update t4-dev-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 3

# Upgrade during dev hours (9-5 PT acceptable downtime)
gcloud container node-pools upgrade t4-dev-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Critical validation:**
- GPU driver version compatibility (GKE auto-installs drivers for 1.32)
- CUDA toolkit compatibility with ML frameworks
- Jupyter/notebook environments functional
- Dev workload scheduling successful

**⚠️ Stop here if GPU driver issues detected** - rollback T4 pool before proceeding to production GPU pools.

### Phase 3: A100 Inference Pool (Most Complex)

**Pre-upgrade preparation:**
```bash
# Apply "no minor or node upgrades" exclusion to protect from auto-upgrade
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "a100-inference-protection" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+90 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Configure rolling upgrade to preserve inference capacity
gcloud container node-pools update a100-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 5
```

**Execution strategy - staggered batches:**
```bash
# Week 1: Upgrade 1/3 of A100 nodes
# Monitor inference SLA impact, error rates, latency

# Week 2: Upgrade 2nd third if Week 1 successful
# Continue monitoring serving capacity

# Week 3: Complete remaining nodes
gcloud container node-pools upgrade a100-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Inference-specific validation:**
- Model serving endpoints responding (all frameworks)
- Inference latency within SLA (p95 < baseline + 10%)
- GPU utilization patterns normal
- Auto-scaling behavior intact
- Load balancer health checks passing

### Phase 4: H100 Training Pool (Highest Stakes)

**Pre-upgrade preparation:**
```bash
# Extend maintenance exclusion for training protection
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "h100-training-protection" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+120 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Configure for maximum control - no auto-upgrade during training
gcloud container node-pools update h100-training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

**Coordination with ML teams:**
1. **Training schedule alignment:** Identify 2-week gap between major training runs
2. **Checkpoint verification:** Ensure all active jobs have recent checkpoints
3. **Communication:** 48h advance notice to training teams

**Execution during training gap:**
```bash
# Option A: Rolling upgrade (safe but slow - 7-10 days for 2,000 nodes)
gcloud container node-pools upgrade h100-training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest

# Option B: Coordinated batch upgrade (faster - 3-4 days)
# Manually cordon batches of nodes, wait for job completion, then upgrade empty batches
```

**Training-specific validation:**
- Multi-node training job startup successful
- RDMA/GPUDirect interconnect functional
- NCCL communication performance maintained
- Compact placement policies preserved
- Storage (Filestore, GCS FUSE) mount performance intact

## Risk Mitigation

### GPU Driver Compatibility Testing
Before any production GPU upgrade, validate in T4 dev environment:
```bash
# Check new driver version
kubectl describe node t4-node-name | grep nvidia
nvidia-smi
nvcc --version

# Test framework compatibility
python -c "import torch; print(torch.cuda.is_available(), torch.version.cuda)"
python -c "import tensorflow as tf; print(tf.config.list_physical_devices('GPU'))"
```

### Rollback Strategy by Pool Type
- **CPU services:** Standard deployment rollback, fast recovery
- **T4 dev:** Acceptable to recreate pool if needed
- **A100 inference:** Gradual rollback batch-by-batch to maintain serving capacity  
- **H100 training:** Pool recreation during next training gap (coordinate with ML teams)

### Capacity Management
- **No surge capacity assumed** for GPU pools due to H100/A100 scarcity
- **maxUnavailable is the primary lever** for GPU pool upgrades
- **Reservation coordination:** Verify upgrade doesn't exceed reservation limits

## Timeline & Communication

| Week | Phase | Activities | Stakeholders |
|------|-------|------------|--------------|
| 1 | Phase 1 | CPU services upgrade | Platform team, SRE |
| 2 | Phase 2 | T4 dev upgrade + GPU validation | ML eng, dev teams |
| 3 | Phase 3a | A100 inference (batch 1) | Inference SRE, product |
| 4 | Phase 3b | A100 inference (batch 2) | Inference SRE, product |  
| 5 | Phase 3c | A100 inference (batch 3) | Inference SRE, product |
| 6-7 | Soak | Monitor inference metrics | All teams |
| 8-9 | Phase 4 | H100 training (during gap) | ML research, training leads |

## Monitoring & Success Criteria

### Platform Health
- No degraded nodes: `kubectl get nodes | grep -v Ready`
- All system pods healthy: `kubectl get pods -n kube-system`
- GPU nodes show correct driver: `kubectl get nodes -o wide -l accelerator=nvidia-tesla-h100`

### Workload Health  
- **Services:** HTTP 5xx < 0.1%, latency p95 within baseline
- **Inference:** Model serving SLA maintained, GPU utilization normal
- **Training:** Multi-node jobs start successfully, interconnect performance preserved

### Version Consistency
```bash
# Verify all nodes at target version
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE \
  --format="table(name,version,status,instanceGroupUrls.list():label=NODES)"
```

## Emergency Procedures

### Stuck Upgrade Recovery
```bash
# Check for common blockers
kubectl get pdb -A -o wide  # PDBs blocking drain
kubectl get pods -A | grep Terminating  # Long-terminating pods
kubectl get events -A --field-selector reason=FailedScheduling  # Resource constraints

# Force PDB relaxation if needed
kubectl patch pdb RESTRICTIVE_PDB -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"100%"}}'
```

### Training Job Protection
```bash
# Emergency exclusion during active training
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "emergency-training-protection" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades
```

This plan prioritizes your training continuity while maintaining inference availability. The 8-9 week timeline accounts for the scale and criticality of GPU workloads. Key success factors: thorough GPU driver validation in Phase 2 and close coordination with ML teams for Phase 4 timing.