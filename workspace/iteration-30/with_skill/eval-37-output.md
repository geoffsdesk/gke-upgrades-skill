# GKE AI/ML Platform Upgrade Plan: 1.31 → 1.32

## Fleet Overview
- **Scale:** 5,000 nodes across 4 workload types
- **Current:** 1.31 → **Target:** 1.32 (single minor version jump)
- **Priority:** Training continuity > Inference availability > Dev environments > Support services

## Phase Structure

### Phase 1: Development & Staging Validation (Week 1)
**Target:** T4 dev nodes (500 nodes) + staging replicas

**Rationale:** Lowest risk, validates GPU driver compatibility and workload behavior on 1.32.

**Pre-phase requirements:**
- [ ] Verify 1.32 GPU driver compatibility with current CUDA versions
- [ ] Create staging node pools (10 H100, 10 A100, 10 T4, 20 CPU) at 1.32
- [ ] Deploy representative workloads to staging pools
- [ ] Validate model loading, inference latency, training job startup

**Upgrade strategy - T4 Development Pools:**
```bash
# T4 pools: Fixed reservation likely, use drain-first approach
gcloud container node-pools update t4-dev-pool \
  --cluster ai-platform-cluster \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4
  # 4 nodes at once = ~125 batches for 500 nodes

# Execute upgrade
gcloud container node-pools upgrade t4-dev-pool \
  --cluster ai-platform-cluster \
  --zone us-central1-a \
  --cluster-version 1.32.X-gke.XXXX
```

**Success criteria:**
- [ ] All dev workloads function normally on 1.32
- [ ] GPU driver version compatibility confirmed
- [ ] No CUDA version conflicts
- [ ] Model serving/training containers start successfully
- [ ] 48-hour soak period with no issues

### Phase 2: CPU Services (Week 2)
**Target:** CPU nodes (1,000 nodes)

**Rationale:** Support services can tolerate brief disruption, validates control plane at scale.

**Control plane upgrade first:**
```bash
# Upgrade control plane during maintenance window
gcloud container clusters upgrade ai-platform-cluster \
  --zone us-central1-a \
  --master \
  --cluster-version 1.32.X-gke.XXXX
```

**Node pool upgrade strategy - CPU Services:**
```bash
# CPU pools: Use percentage-based surge for faster rollout
gcloud container node-pools update cpu-services-pool \
  --cluster ai-platform-cluster \
  --zone us-central1-a \
  --max-surge-upgrade 50 \
  --max-unavailable-upgrade 0
  # 5% of 1000 = 50 nodes concurrent, ~20 batches

# Apply PDB protection for critical services
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: api-gateway-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: api-gateway
EOF
```

**Success criteria:**
- [ ] API services maintain availability
- [ ] Monitoring/logging pipeline uninterrupted
- [ ] Job scheduler (Argo/Airflow) functions normally
- [ ] 24-hour soak period

### Phase 3: A100 Inference (Week 3)
**Target:** A100 inference nodes (1,500 nodes)

**Rationale:** Inference can tolerate brief latency spikes, validates production GPU workloads.

**Pre-phase preparation:**
```bash
# Apply maintenance exclusion to H100 training pools
gcloud container clusters update ai-platform-cluster \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "protect-training-h100" \
  --add-maintenance-exclusion-start-time $(date -u -d '+1 day' '+%Y-%m-%dT%H:%M:%SZ') \
  --add-maintenance-exclusion-end-time $(date -u -d '+14 days' '+%Y-%m-%dT%H:%M:%SZ') \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**Upgrade strategy - A100 Inference:**
```bash
# Option A: If A100 reservation has surge capacity
gcloud container node-pools update a100-inference-pool \
  --cluster ai-platform-cluster \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Option B: If fixed A100 reservation (more likely)
gcloud container node-pools update a100-inference-pool \
  --cluster ai-platform-cluster \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 8
  # 8 nodes = ~188 batches, expect 2-3 days total
```

**Alternative - Autoscaled Blue-Green (Preview, if available):**
```bash
# Better for inference - avoids latency spikes from pod restarts
gcloud container node-pools update a100-inference-pool \
  --cluster ai-platform-cluster \
  --zone us-central1-a \
  --enable-autoscaling \
  --total-min-nodes 1400 --total-max-nodes 1600 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.1,blue-green-full-batch-timeout=3600s
```

**Inference-specific monitoring:**
```bash
# Monitor inference latency during upgrade
kubectl get pods -l workload-type=inference -o wide --sort-by='.status.startTime'

# Check for model loading issues
kubectl logs -l app=model-server --tail=100 | grep -i error
```

**Success criteria:**
- [ ] P95 inference latency within 10% of baseline
- [ ] No model loading failures
- [ ] GPU utilization returns to pre-upgrade levels
- [ ] 72-hour soak period with stable metrics

### Phase 4: H100 Training (Week 4-5)
**Target:** H100 training nodes (2,000 nodes) - **HIGHEST RISK**

**Rationale:** Training jobs are most disruption-sensitive, require careful orchestration.

**Pre-phase coordination:**
```bash
# Remove maintenance exclusion from H100 pools
gcloud container clusters update ai-platform-cluster \
  --zone us-central1-a \
  --remove-maintenance-exclusion-name "protect-training-h100"

# Coordinate with ML teams - checkpoint active jobs
# Wait for natural job completion where possible
```

**Upgrade strategy - H100 Training:**
```bash
# Conservative approach for training pools
gcloud container node-pools update h100-training-pool \
  --cluster ai-platform-cluster \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4
  # 4 nodes = ~500 batches, expect 5-7 days total
```

**Training-specific protection:**
```bash
# Apply strict PDBs for multi-node training jobs
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-job-pdb
spec:
  minAvailable: 7  # For 8-node jobs
  selector:
    matchLabels:
      job-type: distributed-training
EOF
```

**Advanced: Parallel Host Maintenance Strategy (if needed):**
```bash
# For very large training jobs, coordinate with GKE support for:
# 1. Checkpoint all active jobs
# 2. Scale training workloads to zero
# 3. Apply maintenance label to all H100 nodes simultaneously
# kubectl label nodes -l node-pool=h100-training cloud.google.com/perform-maintenance=true
# 4. Wait for host maintenance completion (~4h)
# 5. Restart training jobs from checkpoints
```

**Success criteria:**
- [ ] Training jobs resume from checkpoints successfully
- [ ] Multi-node job communication (NCCL/RDMA) functions
- [ ] GPU interconnect performance matches baseline
- [ ] No data loss from interrupted jobs
- [ ] 96-hour soak period

## Cross-Phase Controls

### Maintenance Windows
```bash
# Configure weekend maintenance windows for all pools
gcloud container clusters update ai-platform-cluster \
  --zone us-central1-a \
  --maintenance-window-start "2024-01-13T02:00:00Z" \
  --maintenance-window-duration 8h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### Monitoring Throughout Upgrade
```bash
# GPU utilization tracking
kubectl top nodes --selector=accelerator=nvidia-tesla-h100

# Training job health
kubectl get pods -l job-type=training --field-selector=status.phase!=Succeeded

# Inference endpoint monitoring
curl -o /dev/null -s -w "%{http_code} %{time_total}\n" https://inference-endpoint/health
```

### Emergency Rollback Procedures

**Control plane rollback (requires GKE support):**
```bash
# Contact GKE support with cluster details for CP downgrade
# Not customer-initiated for minor versions
```

**Node pool rollback:**
```bash
# Create new pool at 1.31, migrate workloads, delete 1.32 pool
gcloud container node-pools create h100-training-pool-rollback \
  --cluster ai-platform-cluster \
  --zone us-central1-a \
  --cluster-version 1.31.X-gke.XXXX \
  --num-nodes 2000 \
  --machine-type a3-highgpu-8g
```

## Risk Mitigation

### GPU-Specific Considerations
- **Driver compatibility:** 1.31→1.32 may change CUDA driver version - validated in Phase 1
- **Fixed reservations:** H100/A100 pools likely have no surge capacity - use `maxUnavailable` only
- **GPUDirect/RDMA:** Test multi-node communication after each phase
- **Compact placement:** Verify replacement nodes maintain physical co-location

### Large-Scale Considerations
- **Upgrade parallelism:** GKE maximum ~20 nodes simultaneously regardless of settings
- **Duration estimates:** 
  - T4 dev (500 nodes): 1-2 days
  - CPU services (1,000 nodes): 2-3 days  
  - A100 inference (1,500 nodes): 3-4 days
  - H100 training (2,000 nodes): 5-7 days
- **Progressive rollout:** Upgrades roll out across regions over 4-5 business days

### Training Continuity
- **Checkpoint before upgrade:** Ensure all active jobs save state
- **PDB timeout:** GKE respects PDBs for 1 hour, then force-evicts
- **Multi-day jobs:** Coordinate upgrades with natural job boundaries
- **Cordon and wait:** For critical jobs, cordon nodes and wait for natural completion

## Success Metrics

### Technical KPIs
- [ ] Zero training job data loss
- [ ] <5% inference latency degradation during transition
- [ ] GPU utilization returns to >90% post-upgrade
- [ ] Multi-node job success rate maintains >98%
- [ ] Zero deprecated API usage warnings

### Operational KPIs  
- [ ] Upgrade completed within 4-week window
- [ ] <2 hours total inference downtime across all phases
- [ ] <8 hours training pipeline interruption per phase
- [ ] Zero emergency rollbacks required
- [ ] Post-upgrade monitoring shows stable metrics for 7 days

## Timeline Summary
- **Week 1:** T4 dev validation + staging
- **Week 2:** CPU services + control plane  
- **Week 3:** A100 inference pools
- **Week 4-5:** H100 training pools (highest priority)
- **Week 6:** Cleanup, documentation, lessons learned

This phased approach prioritizes your training workloads while validating the upgrade path through lower-risk environments first. The extended timeline accounts for the scale and criticality of your AI/ML platform.