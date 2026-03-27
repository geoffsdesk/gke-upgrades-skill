# GKE Mixed AI/ML Platform Upgrade Plan: 1.31 → 1.32

## Executive Summary
This plan upgrades a 5,000-node mixed AI/ML platform prioritizing training continuity (H100s) and inference availability (A100s) while managing the complex GPU reservation constraints typical of large-scale AI workloads.

**Key Strategy:** Staggered upgrade by workload criticality with dedicated maintenance exclusions and custom upgrade strategies per node pool type.

## Environment Overview
- **Cluster Size:** 5,000 nodes total
- **Versions:** Current 1.31 → Target 1.32
- **GPU Pools:**
  - H100 training: 2,000 nodes (highest priority - training continuity)
  - A100 inference: 1,500 nodes (second priority - serving availability)  
  - T4 development: 500 nodes (lowest priority - can tolerate downtime)
- **CPU services:** 1,000 nodes (standard workloads)

## Phase Structure & Timeline

### Phase 1: Control Plane Upgrade (Week 1)
**Duration:** 2-3 hours  
**Risk:** Low (regional clusters maintain availability)

### Phase 2: Low-Risk Pools First (Weeks 2-3)
**Duration:** 1-2 weeks
- T4 development nodes (500)
- CPU service nodes (1,000) 

### Phase 3: Production Inference (Weeks 4-5)
**Duration:** 1-2 weeks
- A100 inference nodes (1,500)

### Phase 4: Training Infrastructure (Weeks 6-8)
**Duration:** 2-3 weeks (coordinated with training campaign gaps)
- H100 training nodes (2,000)

**Total Duration:** 6-8 weeks

## Pre-Upgrade Preparation

### 1. Version Compatibility Verification
```bash
# Verify 1.32 available in your release channel
gcloud container get-server-config --region REGION \
  --format="yaml(channels)" | grep -A 10 "1.32"

# Check deprecated API usage (critical for ML operators)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Verify GPU driver compatibility with GKE 1.32
# Test in a staging T4 node pool first
```

### 2. GPU Driver & CUDA Compatibility
**Critical:** GKE 1.32 may change GPU driver versions, affecting CUDA compatibility.

```bash
# Create staging node pool with target version
gcloud container node-pools create staging-gpu-test \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.32.x-gke.latest \
  --machine-type g2-standard-4 \
  --num-nodes 1 \
  --accelerator type=nvidia-l4,count=1

# Test representative ML workloads
kubectl run cuda-test --image=nvidia/cuda:12.0-devel-ubuntu20.04 \
  --overrides='{"spec":{"nodeSelector":{"cloud.google.com/gke-nodepool":"staging-gpu-test"}}}' \
  -- nvidia-smi
```

### 3. Maintenance Exclusions by Pool Type

**H100 Training Pools - Maximum Protection:**
```bash
# Block ALL upgrades on training pools until scheduled window
gcloud container node-pools update h100-training-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --enable-autoupgrade=false

# Alternative: Use cluster-level exclusion with scope
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "protect-training" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**A100 Inference Pools - Controlled Timing:**
```bash
# Set maintenance window during lowest traffic (e.g., 2-6 AM PST Saturdays)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-window-start "2024-12-07T10:00:00Z" \
  --maintenance-window-end "2024-12-07T14:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### 4. GPU Reservation Capacity Assessment
```bash
# Check GPU reservation headroom
gcloud compute reservations list --filter="zone:ZONE" \
  --format="table(name, specificSkuReservation.count, specificSkuReservation.inUseCount)"

# Verify no surge capacity for fixed reservations
# Most GPU customers have ZERO surge capacity - plan accordingly
```

## Phase-by-Phase Execution

### Phase 1: Control Plane Upgrade

**Pre-flight:**
```bash
# Capture baseline metrics
kubectl top nodes > baseline-node-utilization.txt
kubectl get pods -A --field-selector=status.phase=Running | wc -l > baseline-pod-count.txt

# Ensure no long-running training jobs will be disrupted by API downtime
# (Regional clusters maintain availability, but brief API interruptions possible)
```

**Execution:**
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.32.x-gke.latest
```

**Validation:**
```bash
# Verify control plane version
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="value(currentMasterVersion)"

# Check system pods health
kubectl get pods -n kube-system
kubectl get events -n kube-system --sort-by='.lastTimestamp' | tail -10

# Test GPU workload deployment (should work on existing nodes)
kubectl run test-training --image=tensorflow/tensorflow:latest-gpu \
  --limits="nvidia.com/gpu=1" \
  --rm -i --restart=Never \
  -- python -c "import tensorflow as tf; print(tf.config.list_physical_devices('GPU'))"
```

### Phase 2: Low-Risk Development & Services (Weeks 2-3)

**T4 Development Pool (500 nodes):**
```bash
# Surge upgrade with higher concurrency - dev workloads tolerate disruption
gcloud container node-pools update t4-dev-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 10 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade t4-dev-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.32.x-gke.latest
```

**CPU Services Pool (1,000 nodes):**
```bash
# Conservative surge for production services
gcloud container node-pools update cpu-services-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 50 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade cpu-services-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.32.x-gke.latest
```

**Monitoring:**
```bash
# Track upgrade progress (GKE upgrades ~20 nodes simultaneously)
watch 'kubectl get nodes -o wide | grep -c 1.32'

# Expected duration: ~3-5 days for 1,500 nodes total
# Monitor for PDB violations in inference workloads
kubectl get events -A --field-selector reason=EvictionBlocked
```

### Phase 3: A100 Inference Pool (Weeks 4-5)

**Strategy:** Autoscaled blue-green to minimize inference latency spikes.

**Pre-upgrade:**
```bash
# Capture inference baseline metrics
# Monitor request latency, throughput, error rates

# Configure autoscaling for blue-green
gcloud container node-pools update a100-inference-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --enable-autoscaling \
  --total-min-nodes 1200 \
  --total-max-nodes 1800
```

**Execution (Autoscaled Blue-Green):**
```bash
# Requires capacity for replacement nodes - verify reservation headroom
gcloud container node-pools update a100-inference-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --strategy=AUTOSCALED_BLUE_GREEN \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

gcloud container node-pools upgrade a100-inference-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.32.x-gke.latest
```

**Alternative if no surge capacity:**
```bash
# Drain-first approach - causes inference capacity dips
gcloud container node-pools update a100-inference-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 5

# Monitor inference latency during upgrade
# Scale up other inference pools if needed to compensate
```

**Validation:**
```bash
# Verify inference workloads are healthy
kubectl get pods -l workload-type=inference -A
kubectl get hpa -A

# Check inference endpoint latency
# Run load tests against inference services
curl -X POST https://inference-endpoint/health

# Rollback plan if issues detected:
# kubectl get pods -l cloud.google.com/gke-nodepool=a100-inference-pool -o wide
# If blue-green: complete upgrade or rollback during soak period
```

### Phase 4: H100 Training Pool (Weeks 6-8)

**Strategy:** Coordinate with training campaigns. Use parallel host maintenance for fastest completion.

**Pre-upgrade Coordination:**
```bash
# Identify active training jobs
kubectl get jobs -A -l workload-type=training
kubectl get pods -A -l workload-type=training --field-selector=status.phase=Running

# Checkpoint all active training runs
# Pause new job submissions
# Wait for in-flight jobs to reach checkpoint
```

**Execution (Parallel Host Maintenance):**
```bash
# Scale training workloads to zero
kubectl scale deployment training-controller --replicas=0 -n training

# Apply maintenance label to ALL H100 nodes simultaneously
kubectl get nodes -l node-type=h100 -o name | \
  xargs -I {} kubectl label {} cloud.google.com/perform-maintenance=true

# Monitor host maintenance progress (~4 hours)
kubectl get nodes -l node-type=h100 -o wide
kubectl get events --field-selector involvedObject.kind=Node
```

**Alternative (Rolling Strategy if partial availability needed):**
```bash
# If some training must continue, use rolling approach
# Batch size = 200 nodes (10% of pool)

# Batch 1: Cordon first 200 nodes
kubectl get nodes -l node-type=h100 | head -200 | awk '{print $1}' | \
  xargs kubectl cordon

# Drain and apply maintenance labels
kubectl get nodes -l node-type=h100 -o name | head -200 | \
  xargs -I {} kubectl drain {} --ignore-daemonsets --delete-emptydir-data --grace-period=3600

kubectl get nodes -l node-type=h100 -o name | head -200 | \
  xargs -I {} kubectl label {} cloud.google.com/perform-maintenance=true
```

**Post-upgrade Validation:**
```bash
# Verify all H100 nodes at target version
kubectl get nodes -l node-type=h100 -o wide | grep 1.32

# Test RDMA/GPUDirect connectivity (if applicable)
kubectl run gpu-topology-test --image=nvcr.io/nvidia/pytorch:24.01-py3 \
  --limits="nvidia.com/gpu=8" \
  --overrides='{"spec":{"nodeSelector":{"node-type":"h100"}}}' \
  -- nvidia-smi topo -m

# Restart training workloads
kubectl scale deployment training-controller --replicas=1 -n training

# Monitor training job startup and performance
kubectl logs -f deployment/training-controller -n training
```

## Upgrade Strategy Configuration Summary

| Node Pool | Strategy | Settings | Rationale |
|-----------|----------|----------|-----------|
| **T4 Dev** | Surge | `maxSurge=10, maxUnavailable=0` | Development workloads tolerate disruption |
| **CPU Services** | Surge | `maxSurge=50, maxUnavailable=0` | Standard production settings |
| **A100 Inference** | Autoscaled Blue-Green | `initial-node-percentage=25%` | Minimize latency spikes, maintain serving |
| **H100 Training** | Parallel Host Maintenance | All nodes simultaneously | Fastest completion during training gaps |

## Risk Mitigation & Rollback Plans

### GPU Driver Issues
```bash
# If CUDA compatibility breaks after upgrade:
# 1. Create new node pool with previous version
gcloud container node-pools create h100-rollback \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.31.x-gke.previous \
  --machine-type a3-highgpu-8g

# 2. Migrate training workloads
# 3. Delete problematic pool after validation
```

### Inference Performance Regression
```bash
# If A100 inference latency increases post-upgrade:
# 1. Check for API version changes affecting serving
kubectl get events -A --field-selector reason=Warning | grep -i "version"

# 2. Verify resource allocations unchanged
kubectl describe pods -l workload-type=inference | grep -A 5 "Requests\|Limits"

# 3. Rollback option: recreate pool at 1.31
# (Cannot downgrade existing nodes in-place)
```

### Training Job Recovery
```bash
# If training jobs fail to resume after H100 upgrade:
# 1. Check for GPU driver/CUDA version changes
kubectl run debug-cuda --image=nvidia/cuda:12.0-devel \
  --limits="nvidia.com/gpu=1" \
  --rm -i --restart=Never \
  -- nvidia-smi

# 2. Verify checkpoint/model loading
# 3. Update container images if needed for new CUDA version
```

## Monitoring & Alerting During Upgrade

### Key Metrics to Watch
```bash
# Node availability by pool
kubectl get nodes -l node-type=h100 --no-headers | wc -l
kubectl get nodes -l node-type=a100 --no-headers | wc -l

# GPU utilization (via DCGM or custom metrics)
kubectl top nodes --selector=accelerator=nvidia-tesla-h100

# Inference latency and error rates
curl -s https://monitoring-endpoint/metrics | grep inference_latency

# Training job throughput
kubectl logs -f training-job-xyz | grep "steps/sec\|loss"
```

### Alert Thresholds
- **Inference latency >2x baseline** → Pause A100 upgrades
- **Training throughput <50% baseline** → Investigate H100 upgrade
- **GPU utilization <80% expected** → Check node availability
- **PDB violations >10/hour** → Adjust surge settings

## Post-Upgrade Validation Checklist

```markdown
### Cluster Health
- [ ] All 5,000 nodes at GKE 1.32: `kubectl get nodes -o wide | grep -c 1.32`
- [ ] No nodes in NotReady state: `kubectl get nodes | grep NotReady | wc -l`
- [ ] System pods healthy: `kubectl get pods -n kube-system | grep -v Running | wc -l`

### GPU Workloads
- [ ] H100 training jobs resume successfully
- [ ] A100 inference latency within 10% of baseline
- [ ] T4 development environments accessible
- [ ] GPU driver versions verified: `kubectl get nodes -l accelerator -o jsonpath='{.items[*].status.nodeInfo.kubeletVersion}'`

### Performance Validation
- [ ] Training throughput ≥90% of pre-upgrade baseline
- [ ] Inference p99 latency ≤1.2x pre-upgrade baseline  
- [ ] No GPU memory allocation failures
- [ ] RDMA/GPUDirect connectivity verified (if applicable)

### Operational
- [ ] All maintenance exclusions removed/updated
- [ ] Monitoring and alert