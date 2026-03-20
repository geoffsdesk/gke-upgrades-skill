# GKE Fleet Upgrade Plan: 1.29 → 1.30
**AI/ML Platform (5,000 nodes)**

## Executive Summary

This plan prioritizes training continuity and inference availability through staged upgrades over 4 weeks. H100 training nodes upgrade last during scheduled maintenance windows, while inference and development tiers upgrade progressively to validate each phase.

**Key Strategy:**
- CPU services first (lowest risk)
- T4 dev nodes for early validation 
- A100 inference with rolling availability
- H100 training during planned job gaps only

---

## Cluster Architecture Assessment

| Node Pool | Count | Purpose | Risk Level | Upgrade Priority |
|-----------|-------|---------|------------|------------------|
| CPU services | 1,000 | Platform services, ingress, monitoring | Low | **Phase 1** |
| T4 development | 500 | Experiment, model dev, CI/CD | Low-Medium | **Phase 2** |
| A100 inference | 1,500 | Production inference serving | High | **Phase 3** |
| H100 training | 2,000 | Large model training, research | **Critical** | **Phase 4** |

**Current State:** GKE 1.29
**Target State:** GKE 1.30  
**Timeline:** 4 weeks with 1-week soak time between phases

---

## Phase 1: CPU Services (Week 1)
*Lowest risk, establishes upgrade baseline*

### Pre-Phase Validation
```bash
# Verify 1.30 availability in release channel
gcloud container get-server-config --zone ZONE --format="yaml(channels)"

# Check deprecated API usage across all clusters
for cluster in cpu-cluster inference-cluster dev-cluster training-cluster; do
  echo "=== $cluster ==="
  kubectl --context=$cluster get --raw /metrics | grep apiserver_request_total | grep deprecated
done
```

### Upgrade Sequence
1. **Control plane first** (all CPU clusters)
2. **CPU node pools** with surge settings:
   - `maxSurge=3, maxUnavailable=0` (fast, safe)
   - Platform services have good horizontal scalability

### Commands
```bash
# CPU cluster control plane
gcloud container clusters upgrade cpu-services-cluster \
  --zone us-central1-a \
  --master \
  --cluster-version 1.30.x-gke.latest

# CPU node pools (after CP upgrade completes)
gcloud container node-pools update cpu-pool \
  --cluster cpu-services-cluster \
  --zone us-central1-a \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade cpu-pool \
  --cluster cpu-services-cluster \
  --zone us-central1-a \
  --cluster-version 1.30.x-gke.latest
```

### Success Criteria
- [ ] All CPU nodes on 1.30
- [ ] Platform services (ingress, monitoring, CI/CD) fully operational
- [ ] No degradation in build/deployment pipelines
- [ ] Baseline metrics within normal ranges

---

## Phase 2: T4 Development (Week 2)
*Early GPU validation environment*

### Pre-Phase Checks
```bash
# Verify CUDA driver compatibility with 1.30
# GKE 1.30 includes driver version X.X - verify compatibility with dev frameworks
kubectl --context=dev-cluster get nodes -o yaml | grep 'nvidia.com/cuda'
```

### Upgrade Strategy
- **Conservative surge:** `maxSurge=1, maxUnavailable=0`
- **GPU driver testing:** Validate CUDA version changes with dev workloads
- **Framework validation:** Test PyTorch, TensorFlow, JAX compatibility

### Commands
```bash
# T4 cluster control plane
gcloud container clusters upgrade dev-cluster \
  --zone us-west1-b \
  --master \
  --cluster-version 1.30.x-gke.latest

# T4 GPU node pools
gcloud container node-pools update t4-pool \
  --cluster dev-cluster \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade t4-pool \
  --cluster dev-cluster \
  --zone us-west1-b \
  --cluster-version 1.30.x-gke.latest
```

### Validation Tests
```bash
# Test GPU driver and CUDA after first few nodes upgrade
kubectl --context=dev-cluster run gpu-test \
  --image=nvidia/cuda:12.2-runtime-ubuntu20.04 \
  --restart=Never \
  --rm -it -- nvidia-smi

# Run framework compatibility tests
kubectl --context=dev-cluster apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: framework-validation
spec:
  template:
    spec:
      containers:
      - name: pytorch-test
        image: pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime
        resources:
          limits:
            nvidia.com/gpu: 1
        command: ["python", "-c"]
        args:
        - |
          import torch
          print(f"PyTorch: {torch.__version__}")
          print(f"CUDA available: {torch.cuda.is_available()}")
          print(f"GPU count: {torch.cuda.device_count()}")
      restartPolicy: Never
      nodeSelector:
        cloud.google.com/gke-nodepool: t4-pool
EOF
```

### Success Criteria
- [ ] T4 nodes on 1.30 with working GPU drivers
- [ ] PyTorch, TensorFlow, JAX validate successfully
- [ ] Development workflows unimpacted
- [ ] CUDA version documented and communicated to teams

---

## Phase 3: A100 Inference (Week 3)
*Production inference with rolling availability*

### Critical Considerations
- **Zero-downtime requirement:** Inference services must maintain availability
- **Multi-zone deployment:** Upgrade zones sequentially
- **Load balancer drainage:** Coordinate with L7 load balancers
- **Model serving validation:** Test inference latency/throughput post-upgrade

### Maintenance Window Strategy
```bash
# Configure maintenance windows for off-peak hours (2-6 AM PT)
gcloud container clusters update inference-cluster \
  --zone us-central1-a \
  --maintenance-window-start 2024-MM-DDTXX:XX:XXZ \
  --maintenance-window-end 2024-MM-DDTXX:XX:XXZ \
  --maintenance-window-recurrence "FREQ=DAILY"
```

### Upgrade Strategy
- **Conservative surge:** `maxSurge=1, maxUnavailable=0`
- **Zone-by-zone:** If multi-zonal, upgrade one zone at a time
- **25% capacity batches:** Ensure 75% inference capacity always available

### Commands
```bash
# A100 inference control plane
gcloud container clusters upgrade inference-cluster \
  --zone us-central1-a \
  --master \
  --cluster-version 1.30.x-gke.latest

# A100 node pools (very conservative)
gcloud container node-pools update a100-inference-pool \
  --cluster inference-cluster \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade a100-inference-pool \
  --cluster inference-cluster \
  --zone us-central1-a \
  --cluster-version 1.30.x-gke.latest
```

### Inference Validation
```bash
# Monitor inference latency during upgrade
kubectl --context=inference-cluster run latency-test \
  --image=your-inference-client:latest \
  --restart=Never \
  --rm -it -- benchmark-inference-endpoints.sh

# Validate model serving after node upgrade
kubectl --context=inference-cluster get pods -l app=model-server -o wide
kubectl --context=inference-cluster logs -l app=model-server --tail=100 | grep "inference_latency_ms"
```

### Success Criteria
- [ ] All A100 inference nodes on 1.30
- [ ] Inference latency within 5% of baseline (p95 < Xms)
- [ ] Throughput maintained (requests/second ≥ baseline)
- [ ] No model serving errors or GPU memory issues
- [ ] Load balancer health checks passing

---

## Phase 4: H100 Training (Week 4)
*Most critical - training continuity paramount*

### Training Job Coordination
**CRITICAL:** Coordinate with ML teams for training schedule gaps

```bash
# Apply maintenance exclusion to prevent auto-upgrades during active training
gcloud container clusters update training-cluster \
  --zone us-west1-a \
  --add-maintenance-exclusion-name "training-campaign-protection" \
  --add-maintenance-exclusion-start-time 2024-XX-XXTXX:XX:XXZ \
  --add-maintenance-exclusion-end-time 2024-XX-XXTXX:XX:XXZ \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### Pre-Upgrade Requirements
- [ ] **Checkpoint all active training jobs**
- [ ] **Coordinate 48-hour training gap window**
- [ ] **Verify H100 surge capacity availability** (contact GCP TAM if needed)
- [ ] **Backup training data and checkpoints**

### Upgrade Strategy
- **Minimal surge:** `maxSurge=1, maxUnavailable=0` (H100s are scarce)
- **Pool-by-pool:** If multiple H100 pools, upgrade sequentially
- **Extended timeline:** Allow 48-72 hours for 2,000 nodes

### Commands
```bash
# H100 training control plane (during scheduled gap)
gcloud container clusters upgrade training-cluster \
  --zone us-west1-a \
  --master \
  --cluster-version 1.30.x-gke.latest

# H100 node pools (minimal surge due to capacity constraints)
gcloud container node-pools update h100-training-pool \
  --cluster training-cluster \
  --zone us-west1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade h100-training-pool \
  --cluster training-cluster \
  --zone us-west1-a \
  --cluster-version 1.30.x-gke.latest
```

### Alternative: Blue-Green for H100 (if surge capacity unavailable)
```bash
# If H100 surge nodes can't be provisioned, use blue-green
gcloud container node-pools create h100-training-pool-130 \
  --cluster training-cluster \
  --zone us-west1-a \
  --cluster-version 1.30.x-gke.latest \
  --machine-type a3-highgpu-8g \
  --num-nodes 250 \
  --disk-size 200GB \
  --disk-type pd-balanced \
  --enable-gvnic \
  --placement-policy-type COMPACT

# Migrate training workloads, then delete old pool
kubectl cordon -l cloud.google.com/gke-nodepool=h100-training-pool
# Wait for jobs to reschedule to new pool
gcloud container node-pools delete h100-training-pool \
  --cluster training-cluster \
  --zone us-west1-a
```

### Training Resumption Validation
```bash
# Test GPU interconnect (GPUDirect-TCPX) after upgrade
kubectl --context=training-cluster run nccl-test \
  --image=nvcr.io/nvidia/pytorch:24.01-py3 \
  --restart=Never \
  --rm -it \
  --overrides='{"spec":{"containers":[{"name":"nccl-test","resources":{"limits":{"nvidia.com/gpu":"8"}}}]}}' \
  -- python -c "
import torch
import torch.distributed as dist
print(f'NCCL version: {torch.cuda.nccl.version()}')
print(f'GPU-GPU bandwidth test...')
"

# Verify training job can resume from checkpoint
kubectl --context=training-cluster apply -f training-resume-test.yaml
```

### Success Criteria
- [ ] All H100 nodes on 1.30
- [ ] GPU interconnect (NCCL/GPUDirect) working
- [ ] Training jobs resume successfully from checkpoints
- [ ] Multi-node training communication validated
- [ ] No CUDA/driver issues with training frameworks

---

## Multi-Cluster Coordination

### Fleet Status Dashboard
Create a tracking sheet for all phases:

```bash
#!/bin/bash
# Fleet upgrade status script
echo "=== GKE Fleet Upgrade Status ==="
for cluster in cpu-services dev-t4 inference-a100 training-h100; do
  version=$(gcloud container clusters describe $cluster --zone=$zone --format="value(currentMasterVersion)")
  echo "$cluster: $version"
done
```

### Communication Plan
- **Week -1:** Training teams notified of H100 maintenance window
- **Each phase:** Status updates to ML platform users
- **Post-upgrade:** Performance metrics shared with stakeholders

### Rollback Strategy
Control plane downgrade requires GKE support. For nodes:

```bash
# Emergency rollback: create new pool at 1.29 (per cluster)
gcloud container node-pools create POOL-rollback \
  --cluster CLUSTER \
  --zone ZONE \
  --cluster-version 1.29.x-gke.latest \
  --machine-type MACHINE_TYPE \
  --num-nodes NUM_NODES
```

---

## Timeline Summary

| Week | Phase | Nodes | Risk | Key Activities |
|------|-------|-------|------|---------------|
| **1** | CPU Services | 1,000 | Low | Platform validation, monitoring setup |
| **2** | T4 Development | 500 | Medium | GPU driver validation, framework testing |
| **3** | A100 Inference | 1,500 | High | Rolling upgrade, inference metrics validation |
| **4** | H100 Training | 2,000 | **Critical** | Coordinated with training gaps, checkpoint validation |

**Total Duration:** 4 weeks  
**Soak Time:** 1 week between phases  
**Rollback Window:** 48 hours per phase

This phased approach ensures your training workloads experience minimal disruption while systematically validating GPU driver compatibility and framework behavior at each tier.