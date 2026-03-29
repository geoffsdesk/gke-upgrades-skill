# GKE AI/ML Platform Upgrade Plan: 1.31 → 1.32

**Cluster Details:**
- Total nodes: 5,000 (very large cluster)
- Mix: 2,000 H100 (training) + 1,500 A100 (inference) + 500 T4 (dev) + 1,000 CPU
- Current: 1.31 → Target: 1.32

## Executive Summary

This upgrade plan prioritizes training continuity and inference availability through **phased rollout with training-first sequencing**. GPU pools require special handling due to fixed reservations (no surge capacity) and extended upgrade duration (~3-7 days for large pools).

**Key Strategy:**
1. **Dev environment first** (T4 + CPU subset) for validation
2. **CPU services pools** during off-peak (minimal training impact)
3. **A100 inference pools** with autoscaled blue-green (maintains serving capacity)
4. **H100 training pools** during scheduled training gaps only

## Phase 1: Development Environment Validation (Week 1)

**Objective:** Validate GKE 1.32 + GPU driver compatibility with zero production impact

**Scope:** T4 dev pools (500 nodes) + staging CPU subset (100 nodes)

### Pre-flight Validation
```bash
# Create staging H100/A100 pools with 1.32 for validation
gcloud container node-pools create h100-staging \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest \
  --num-nodes 2 \
  --machine-type a3-highgpu-8g \
  --node-taints=staging=true:NoSchedule

# Deploy representative workloads on staging pools
kubectl apply -f training-validation-job.yaml
kubectl apply -f inference-validation-deployment.yaml
```

**Validation Checklist:**
- [ ] CUDA compatibility with new GPU driver version
- [ ] Training job convergence on H100 staging nodes
- [ ] Inference latency/throughput baseline on A100 staging nodes
- [ ] GPUDirect-TCPX/RDMA topology survives upgrade
- [ ] Custom operators (PyTorch, JAX, MLX) load successfully
- [ ] Model checkpointing/resumption works

**T4 Dev Pool Upgrade (Safe to proceed immediately):**
```bash
# T4 pools: Use higher maxUnavailable due to dev tolerance
gcloud container node-pools update t4-dev-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4

gcloud container node-pools upgrade t4-dev-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Timeline:** 3-4 days (staging validation + T4 upgrade)

## Phase 2: CPU Services Infrastructure (Week 2)

**Objective:** Upgrade non-GPU infrastructure with minimal training/inference impact

**Scope:** CPU node pools (1,000 nodes) - API servers, monitoring, data pipelines

**Timing:** Off-peak hours (nights/weekends) to minimize API server load during training

```bash
# CPU pools: Standard surge upgrade with moderate parallelism
gcloud container node-pools update cpu-services-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 50 \
  --max-unavailable-upgrade 0

# Maintenance window for off-peak execution
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-duration 6h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

gcloud container node-pools upgrade cpu-services-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**PDB Configuration for Critical Services:**
```bash
# Ensure API gateways, monitoring maintain availability
kubectl patch pdb api-gateway-pdb -n production \
  -p '{"spec":{"minAvailable":"75%"}}'
```

**Timeline:** 2-3 days (1,000 nodes at ~20 node parallelism = ~50 batches)

## Phase 3: A100 Inference Pools (Week 3)

**Objective:** Upgrade inference nodes with zero serving downtime

**Scope:** A100 inference pools (1,500 nodes)

**Strategy:** **Autoscaled blue-green** - maintains serving capacity throughout upgrade

**Critical Preparation:**
```bash
# Verify inference pool has autoscaling enabled
gcloud container node-pools describe a100-inference-pool \
  --cluster CLUSTER_NAME --zone ZONE \
  --format="value(autoscaling.enabled,autoscaling.minNodeCount,autoscaling.maxNodeCount)"

# Configure autoscaled blue-green upgrade
gcloud container node-pools update a100-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 1000 --total-max-nodes 3000 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.20,blue-green-full-batch-timeout=3600s
```

**Why Autoscaled Blue-Green for Inference:**
- Avoids inference latency spikes from surge drain-restart cycles
- Maintains serving capacity while new nodes warm up
- Scales down old pool as workloads migrate (cost-efficient)
- Critical for SLA-bound inference workloads

```bash
# Trigger autoscaled blue-green upgrade
gcloud container node-pools upgrade a100-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Monitoring During Upgrade:**
```bash
# Track inference latency and error rates
kubectl top pods -n inference --containers
# Monitor pool scaling: old pool scales down, new pool scales up
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=a100-inference-pool -o wide'
```

**Timeline:** 5-7 days (1,500 nodes + blue-green soak time)

## Phase 4: H100 Training Pools (Week 4)

**Objective:** Upgrade training infrastructure during scheduled training gaps

**Scope:** H100 training pools (2,000 nodes) - largest, highest-risk component

**Critical Prerequisite:** **Coordinate with ML teams for training campaign gaps**

### Pre-Upgrade Training Protection
```bash
# Apply maintenance exclusion to block auto-upgrades during active training
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-freeze" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-01-21T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### Training Job Preparation
```bash
# Verify all training jobs have checkpointing enabled
kubectl get jobs -n training -o jsonpath='{range .items[*]}{.metadata.name}: {.spec.template.spec.volumes[?(@.name=="checkpoint")]}{"\n"}{end}'

# Pause new training job submissions
kubectl scale deployment training-scheduler --replicas=0 -n training

# Wait for active jobs to reach checkpoint
# Monitor: kubectl get pods -n training -l job-type=training
```

### H100 Pool Upgrade Strategy

**Option A: Parallel Host Maintenance (Recommended for Training)**
All H100 nodes updated simultaneously during planned downtime:

```bash
# Scale training workloads to zero
kubectl scale statefulset large-model-training --replicas=0 -n training

# Apply AI host maintenance label to all H100 nodes
kubectl label nodes -l cloud.google.com/gke-nodepool=h100-training-pool \
  cloud.google.com/perform-maintenance=true

# Monitor host maintenance progress (~4 hours)
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=h100-training-pool -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,READY:.status.conditions[?(@.type=="Ready")].status'
```

**Option B: Conservative Drain-First (Slower but Safer)**
```bash
# H100 pools: No surge capacity available, drain-first approach
gcloud container node-pools update h100-training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 10

gcloud container node-pools upgrade h100-training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

### Post-Upgrade Validation
```bash
# Verify RDMA/GPUDirect topology
kubectl apply -f gpu-topology-test.yaml

# Resume training scheduler
kubectl scale deployment training-scheduler --replicas=1 -n training

# Test training job on upgraded nodes
kubectl apply -f validation-training-job.yaml
```

**Timeline:** 3-5 days (depending on strategy choice)

## Complete Upgrade Runbook

### Control Plane Upgrade (Before any node pools)
```bash
# Upgrade control plane first - required order
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest

# Verify control plane health (~15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"

kubectl get pods -n kube-system | grep -v Running
```

### Version Compatibility Check
```bash
# Verify 1.32 available in release channel
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels)" | grep -A 10 "REGULAR\|STABLE"

# Check deprecated API usage (common failure cause)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=LOCATION --project=PROJECT_ID
```

### GPU Driver Compatibility Verification
```bash
# Check current and target GPU driver versions
gcloud container node-pools describe h100-training-pool \
  --cluster CLUSTER_NAME --zone ZONE \
  --format="value(config.accelerators[0].acceleratorType,version)"

# Validate CUDA compatibility in staging
kubectl exec -it gpu-test-pod -- nvidia-smi
kubectl exec -it gpu-test-pod -- nvcc --version
```

## Risk Mitigation & Rollback

### High-Risk Components (Order of Impact)
1. **H100 training pools** - Multi-day jobs, no live migration
2. **A100 inference pools** - SLA impact, customer-facing
3. **CPU services** - Infrastructure dependencies
4. **T4 dev pools** - Low risk, rapid recovery

### Emergency Rollback Procedures

**Control Plane Rollback:**
Not supported for minor versions. Requires GKE support engagement.

**Node Pool Rollback:**
```bash
# Create emergency rollback pool at 1.31
gcloud container node-pools create POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.previous \
  --machine-type MACHINE_TYPE \
  --num-nodes NUM_NODES

# Migrate workloads to rollback pool
kubectl cordon -l cloud.google.com/gke-nodepool=ORIGINAL_POOL
# Drain and delete original pool after migration
```

### GPU Pool-Specific Rollback
```bash
# For GPU pools with fixed reservations - replace pool entirely
gcloud container node-pools create h100-training-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.previous \
  --machine-type a3-highgpu-8g \
  --accelerator type=nvidia-h100-80gb,count=8 \
  --reservation-affinity=specific \
  --reservation=h100-reservation

# Validate GPU driver compatibility before migrating training jobs
```

## Monitoring & Validation

### Success Criteria Per Phase

**Phase 1 (Dev):**
- [ ] All T4 nodes at 1.32
- [ ] Development workloads healthy
- [ ] GPU driver compatibility confirmed
- [ ] No training/inference impact

**Phase 2 (CPU):**
- [ ] All CPU nodes at 1.32
- [ ] API server latency <100ms p99
- [ ] Monitoring/logging pipelines healthy
- [ ] No training/inference disruption

**Phase 3 (A100 Inference):**
- [ ] All A100 inference nodes at 1.32
- [ ] Inference SLA maintained (0 downtime)
- [ ] Latency within 10% of baseline
- [ ] Error rate <0.1%

**Phase 4 (H100 Training):**
- [ ] All H100 training nodes at 1.32
- [ ] Training jobs resume from checkpoint
- [ ] GPUDirect/RDMA topology intact
- [ ] Multi-node training communication working

### Critical Monitoring Commands
```bash
# Overall cluster health
kubectl get nodes | grep -c Ready
kubectl get pods -A | grep -E "Crash|Error|Pending" | wc -l

# GPU-specific health
kubectl get nodes -l accelerator=nvidia-h100-80gb -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,GPU:.status.allocatable."nvidia\.com/gpu"

# Training job health
kubectl get pods -n training -l job-type=training -o wide
kubectl top pods -n training --containers | grep gpu
```

## Timeline Summary

| Phase | Duration | Scope | Risk Level |
|-------|----------|--------|-----------|
| **Phase 1: Dev Validation** | Week 1 (3-4 days) | 600 nodes (T4 + staging) | **Low** |
| **Phase 2: CPU Services** | Week 2 (2-3 days) | 1,000 CPU nodes | **Medium** |  
| **Phase 3: A100 Inference** | Week 3 (5-7 days) | 1,500 A100 nodes | **High** |
| **Phase 4: H100 Training** | Week 4 (3-5 days) | 2,000 H100 nodes | **Critical** |
| **Total** | **~3-4 weeks** | **5,000 nodes** | **Managed progression** |

**Key Success Factors:**
- Coordinate H100 upgrades with ML team training schedules
- Use autoscaled blue-green for inference to maintain SLA
- Validate GPU driver compatibility in dev before production
- Maintain 48-hour soak periods between high-risk phases
- Keep emergency rollback pools ready for GPU components

This plan balances upgrade velocity with AI/ML workload protection, ensuring training continuity and inference availability throughout the 1.31→1.32 migration.