# GKE AI/ML Platform Upgrade Plan: 1.31 → 1.32
**Fleet Size:** 5,000 nodes | **Target:** Maintain training continuity & inference availability

## Executive Summary

This phased upgrade plan prioritizes **training continuity** (H100 pools) and **inference availability** (A100 pools) while systematically upgrading your 5,000-node AI/ML platform. The approach uses dedicated maintenance exclusions for training pools, autoscaled blue-green for inference pools, and progressive rollout across development → services → production.

**Key Strategy:**
- Phase 1-2: Non-critical pools (T4 dev, CPU services) to validate upgrade
- Phase 3: A100 inference with zero-downtime autoscaled blue-green
- Phase 4: H100 training during scheduled campaign gaps only

---

## Pre-Flight Assessment

### Version Compatibility
```bash
# Verify 1.32 availability in your release channel
gcloud container get-server-config --zone ZONE --format="yaml(channels)"

# Check for deprecated API usage (critical for AI/ML operators)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Validate GPU driver compatibility with 1.32
# GKE 1.32 includes NVIDIA driver 535.x - verify model compatibility in staging
```

### AI/ML Workload Assessment
- [ ] **Training campaigns:** Current H100 utilization and scheduled training gaps
- [ ] **Inference SLAs:** A100 availability requirements and traffic patterns  
- [ ] **GPU reservations:** Confirm no surge capacity available (typical for H100/A100)
- [ ] **Operator compatibility:** Verify Kubeflow, Ray, PyTorch operators support K8s 1.32
- [ ] **CUDA version impact:** Test inference models with driver 535.x in staging cluster

---

## Phase 1: Development Infrastructure (T4 Nodes)
**Duration:** 3-4 days | **Nodes:** 500 T4 GPU nodes | **Risk:** Low

### Objective
Validate GPU upgrade behavior and driver compatibility with non-critical workloads.

### Strategy
- **Upgrade approach:** Surge with `maxSurge=0, maxUnavailable=2` (no surge capacity)
- **Timing:** Business hours for active monitoring
- **Validation:** GPU driver installation, model loading, development workflows

### Commands
```bash
# Phase 1a: Control plane upgrade
gcloud container clusters upgrade ML_DEV_CLUSTER \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.y

# Phase 1b: T4 node pool upgrade  
gcloud container node-pools update t4-dev-pool \
  --cluster ML_DEV_CLUSTER \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2

gcloud container node-pools upgrade t4-dev-pool \
  --cluster ML_DEV_CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.x-gke.y
```

### Success Criteria
- [ ] All T4 nodes at 1.32, driver 535.x installed
- [ ] Development notebooks and training jobs launch successfully
- [ ] GPU memory allocation and CUDA calls functional
- [ ] No regressions in PyTorch/TensorFlow model loading

---

## Phase 2: Service Infrastructure (CPU Nodes)  
**Duration:** 2-3 days | **Nodes:** 1,000 CPU nodes | **Risk:** Low

### Objective
Upgrade platform services (monitoring, logging, CI/CD, control plane components) to ensure operational readiness.

### Strategy
- **Upgrade approach:** Surge with `maxSurge=5%, maxUnavailable=0`
- **Timing:** Maintenance window (Saturday 2-6 AM)
- **Focus:** Zero downtime for monitoring/alerting during AI workload upgrades

### Commands
```bash
# Control plane first
gcloud container clusters upgrade PLATFORM_SERVICES_CLUSTER \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.y

# CPU service pools with rolling surge
gcloud container node-pools update cpu-services-pool \
  --cluster PLATFORM_SERVICES_CLUSTER \
  --zone ZONE \
  --max-surge-upgrade 50 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade cpu-services-pool \
  --cluster PLATFORM_SERVICES_CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.x-gke.y
```

### Success Criteria
- [ ] Monitoring (Prometheus/Grafana) operational
- [ ] Logging pipeline (Fluentd/Cloud Logging) functional  
- [ ] CI/CD and artifact registries available
- [ ] Platform APIs responding within SLA

---

## Phase 3: Inference Infrastructure (A100 Nodes)
**Duration:** 5-7 days | **Nodes:** 1,500 A100 GPU nodes | **Risk:** Medium

### Objective
Zero-downtime upgrade of inference infrastructure maintaining SLA compliance.

### Strategy
- **Upgrade approach:** Autoscaled blue-green (preserves inference availability)
- **Pool sequencing:** One pool per day with validation soak
- **SLA protection:** Blue pool serves traffic while green pool warms up

### Why Autoscaled Blue-Green for Inference
- GPU VMs don't support live migration - every surge upgrade causes pod restart
- Inference workloads are latency-sensitive - avoid serving interruption
- Cost-efficient vs standard blue-green (scales down blue as green scales up)
- No surge GPU capacity needed (uses existing reservation efficiently)

### Commands
```bash
# Control plane upgrade
gcloud container clusters upgrade INFERENCE_PROD_CLUSTER \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.y

# Configure autoscaled blue-green per A100 pool
gcloud container node-pools update a100-inference-pool-1 \
  --cluster INFERENCE_PROD_CLUSTER \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 100 \
  --total-max-nodes 300 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Trigger autoscaled blue-green upgrade
gcloud container node-pools upgrade a100-inference-pool-1 \
  --cluster INFERENCE_PROD_CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.x-gke.y

# Monitor green pool scaling and traffic shift
kubectl get nodes -l cloud.google.com/gke-nodepool=a100-inference-pool-1 -o wide
kubectl get pods -l app=inference-service -o wide
```

### Validation Per Pool
```bash
# Model loading test
kubectl run inference-test --image=gcr.io/PROJECT/inference:latest \
  --rm -it --restart=Never \
  --overrides='{"spec":{"nodeSelector":{"cloud.google.com/gke-nodepool":"a100-inference-pool-1"}}}'

# SLA verification  
curl -X POST https://INFERENCE_ENDPOINT/predict -d @sample_request.json
# Verify <100ms p95 latency maintained
```

### Success Criteria (Per Pool)
- [ ] Model loading successful on 1.32 + driver 535.x
- [ ] Inference latency within pre-upgrade baseline (p95 <100ms)
- [ ] No request drops during blue-green transition
- [ ] Autoscaling behavior normal on upgraded nodes
- [ ] 48-hour soak period with zero incidents

---

## Phase 4: Training Infrastructure (H100 Nodes)
**Duration:** Coordinated with training schedule | **Nodes:** 2,000 H100 GPU nodes | **Risk:** High

### Objective  
Upgrade training infrastructure during natural campaign gaps to minimize disruption to multi-day/week training runs.

### Strategy
- **Timing:** Coordinate with ML teams for training campaign gaps
- **Maintenance exclusion:** Block auto-upgrades during active training
- **Upgrade approach:** Drain-first (`maxUnavailable=1`) - no surge capacity
- **Checkpoint requirement:** All training jobs must support checkpointing

### Pre-Training Campaign Protection
```bash
# Block auto-upgrades during active training campaigns
gcloud container clusters update TRAINING_PROD_CLUSTER \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-q1" \
  --add-maintenance-exclusion-start-time 2024-03-01T00:00:00Z \
  --add-maintenance-exclusion-end-time 2024-03-15T00:00:00Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### Upgrade During Campaign Gap
```bash
# Control plane upgrade (minimal disruption)
gcloud container clusters upgrade TRAINING_PROD_CLUSTER \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.y

# Wait for training jobs to checkpoint and stop
kubectl get pods -l app=training-job --field-selector=status.phase=Running

# Configure drain-first strategy (no surge capacity available)
gcloud container node-pools update h100-training-pool-1 \
  --cluster TRAINING_PROD_CLUSTER \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

# Trigger node pool upgrade
gcloud container node-pools upgrade h100-training-pool-1 \
  --cluster TRAINING_PROD_CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.x-gke.y
```

### Training-Specific Considerations
- **Compact placement:** Verify replacement H100 nodes maintain placement group topology for RDMA
- **GPUDirect-TCPX:** Confirm networking config survives upgrade (requires GKE 1.27.7+, compatible with 1.32)
- **Multi-host training:** Test cross-node communication after first pool upgrade
- **Checkpoint validation:** Verify training resumes correctly from checkpoints on upgraded nodes

### Success Criteria
- [ ] All H100 nodes upgraded to 1.32 during training gaps
- [ ] GPUDirect-TCPX and RDMA topology functional  
- [ ] Multi-node training jobs resume successfully from checkpoints
- [ ] Training throughput maintained (tokens/sec, samples/sec)
- [ ] No data corruption in distributed training state

---

## Timeline & Dependencies

| Phase | Duration | Dependencies | Parallel Activities |
|-------|----------|-------------|-------------------|
| **Phase 1: T4 Dev** | Days 1-4 | None | GPU driver validation |
| **Phase 2: CPU Services** | Days 5-7 | Phase 1 complete | Platform readiness |  
| **Phase 3: A100 Inference** | Days 8-14 | Phase 2 complete | One pool per day + soak |
| **Phase 4: H100 Training** | Days 15+ | Campaign coordination | Checkpoint before upgrade |

**Total Fleet Upgrade Time:** 3-4 weeks (coordinated with training schedule)

---

## Risk Mitigation

### GPU-Specific Risks
- **Driver compatibility:** Validate CUDA/driver 535.x with all model architectures in staging
- **Memory allocation changes:** Test GPU memory management with new kubelet version
- **Inference latency:** Blue-green approach prevents serving disruption during A100 upgrades
- **Training interruption:** Maintenance exclusions + checkpoint-resume protect long-running jobs

### Large-Scale Risks  
- **Upgrade parallelism:** GKE upgrades ~20 nodes simultaneously regardless of settings
- **Quota exhaustion:** Using `maxUnavailable` (drain-first) avoids surge quota requirements
- **Network partition:** Upgrade one zone at a time for multi-zone pools

### Rollback Strategy
- **Control plane:** Contact GKE support for minor version rollback (not customer-initiated)
- **Node pools:** Create new pool at 1.31, migrate workloads, delete upgraded pool
- **Training data:** PV snapshots taken before each training pool upgrade

---

## Monitoring & Validation

### GPU Health Metrics
```bash
# GPU utilization post-upgrade
kubectl top nodes --selector=accelerator=h100
kubectl top nodes --selector=accelerator=a100

# Driver and CUDA version verification
kubectl get nodes -o json | jq '.items[].status.nodeInfo | {kubeletVersion, kernelVersion}'
```

### Training Workload Validation
```bash  
# Verify multi-node communication
kubectl exec -it training-pod-0 -- python -c "import torch; print(torch.distributed.is_available())"

# Checkpoint resume test
kubectl logs training-job-xyz | grep "Resuming from checkpoint"
```

### Inference SLA Monitoring
- Latency: p95 <100ms maintained across A100 upgrade phases  
- Availability: >99.9% uptime during blue-green transitions
- Throughput: Requests/sec within 5% of pre-upgrade baseline

---

## Success Criteria - Fleet Level

- [ ] **All 5,000 nodes upgraded** to GKE 1.32 within 4-week window
- [ ] **Zero training job failures** due to upgrade-related issues
- [ ] **Inference SLA maintained** throughout A100 pool upgrades  
- [ ] **GPU driver 535.x** functional across all accelerator types
- [ ] **Cost impact <5%** via efficient upgrade strategies (drain-first, autoscaled blue-green)
- [ ] **Platform services** (monitoring, logging) operational throughout

This plan balances the competing priorities of training continuity and inference availability while systematically upgrading your large-scale AI/ML infrastructure. The phased approach provides validation gates and rollback points at each stage.