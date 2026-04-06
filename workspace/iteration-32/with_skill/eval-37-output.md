# GKE AI/ML Platform Upgrade Plan: 1.31 → 1.32

## Executive Summary

5,000-node mixed AI/ML platform upgrade with priority on **training continuity** (H100) and **inference availability** (A100). Phased approach over 3-4 weeks with comprehensive validation gates.

**Cluster Details:**
- Current: GKE 1.31 | Target: 1.32
- 2,000 H100 nodes (training) | 1,500 A100 nodes (inference) 
- 500 T4 nodes (dev) | 1,000 CPU nodes (services)
- Assumption: Standard clusters, Regional release channel

## Phase Structure & Rationale

### Phase 1: CPU Services (Week 1)
- **Rationale:** Lowest risk, validates upgrade mechanics, unblocks GPU phases
- **Node pools:** 1,000 CPU service nodes
- **Strategy:** Surge upgrade, `maxSurge=5%` (50 nodes), `maxUnavailable=0`
- **Duration:** 2-3 days given GKE's ~20-node parallelism limit

### Phase 2: T4 Development (Week 1-2) 
- **Rationale:** Non-production, tests GPU upgrade mechanics with lower-tier hardware
- **Node pools:** 500 T4 development nodes  
- **Strategy:** Surge upgrade, `maxSurge=0, maxUnavailable=2` (GPU reservations likely fixed)
- **Duration:** 2-3 days

### Phase 3: A100 Inference (Week 2-3)
- **Rationale:** Production inference, requires availability but shorter workloads than training
- **Node pools:** 1,500 A100 inference nodes
- **Strategy:** **Autoscaled blue-green** (maintains serving capacity during upgrade)
- **Duration:** 4-7 days with validation gates

### Phase 4: H100 Training (Week 3-4)
- **Rationale:** Highest priority, longest workloads, most disruptive to interrupt
- **Node pools:** 2,000 H100 training nodes  
- **Strategy:** Maintenance exclusion + manual checkpoint-resume cycle
- **Duration:** 5-10 days with careful orchestration

---

## Detailed Phase Plans

### Phase 1: CPU Services Upgrade
**Target:** 1,000 CPU service nodes | **Duration:** 2-3 days

#### Pre-flight
```bash
# Verify control plane upgrade readiness
gcloud container clusters describe AI-PLATFORM-CLUSTER \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Check deprecated API usage (common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Validate PDBs are not overly restrictive
kubectl get pdb -A -o wide | grep "ALLOWED.*0"
```

#### Control plane upgrade (all phases depend on this)
```bash
# Upgrade control plane first - required before any node pools
gcloud container clusters upgrade AI-PLATFORM-CLUSTER \
  --zone ZONE \
  --master \
  --cluster-version 1.32.0-gke.LATEST

# Verify control plane health (wait 10-15 min)
kubectl get pods -n kube-system
kubectl get nodes  # Should all remain Ready during CP upgrade
```

#### CPU node pool configuration & upgrade
```bash
# Configure surge for service workloads (stateless, restart-tolerant)
gcloud container node-pools update cpu-services \
  --cluster AI-PLATFORM-CLUSTER \
  --zone ZONE \
  --max-surge-upgrade 50 \
  --max-unavailable-upgrade 0

# Execute upgrade
gcloud container node-pools upgrade cpu-services \
  --cluster AI-PLATFORM-CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.0-gke.LATEST

# Monitor progress (~2-3 days for 1,000 nodes at ~20 node parallelism)
watch 'kubectl get nodes -l node-pool=cpu-services -o wide'
```

#### Validation gate
- [ ] All CPU service pods Running
- [ ] API latency within baseline (check HPA/VPA behavior changes)
- [ ] No deprecated API warnings in new cluster version
- [ ] Monitoring/logging pipeline healthy

---

### Phase 2: T4 Development Upgrade  
**Target:** 500 T4 development nodes | **Duration:** 2-3 days

#### Strategy rationale
- **GPU-specific constraint:** Fixed reservations = no surge capacity
- **Primary lever:** `maxUnavailable` (NOT `maxSurge`)
- **Dev workloads:** Shorter jobs, restart-tolerant

#### Pre-flight GPU validation
```bash
# Verify GPU driver compatibility with GKE 1.32
# Create staging T4 node pool to test driver + CUDA compatibility
gcloud container node-pools create t4-test-1-32 \
  --cluster AI-PLATFORM-CLUSTER \
  --zone ZONE \
  --machine-type g2-standard-4 \
  --accelerator type=nvidia-tesla-t4,count=1 \
  --num-nodes 1 \
  --cluster-version 1.32.0-gke.LATEST

# Test representative workload on staging pool
kubectl run gpu-test --image=tensorflow/tensorflow:latest-gpu \
  --limits=nvidia.com/gpu=1 \
  --rm -it -- python -c "import tensorflow as tf; print(tf.config.list_physical_devices('GPU'))"
```

#### T4 upgrade execution
```bash
# GPU pools: maxUnavailable is the primary lever (no surge capacity)
gcloud container node-pools update t4-dev \
  --cluster AI-PLATFORM-CLUSTER \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2

# Execute upgrade
gcloud container node-pools upgrade t4-dev \
  --cluster AI-PLATFORM-CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.0-gke.LATEST

# Clean up staging pool after validation
gcloud container node-pools delete t4-test-1-32 --cluster AI-PLATFORM-CLUSTER --zone ZONE
```

#### Validation gate
- [ ] CUDA/driver versions compatible with dev workloads
- [ ] GPU device plugin healthy: `kubectl get daemonset -n kube-system | grep nvidia`
- [ ] Sample training job completes successfully
- [ ] No GPU reservation issues in staging tests

---

### Phase 3: A100 Inference Upgrade
**Target:** 1,500 A100 inference nodes | **Duration:** 4-7 days

#### Strategy: Autoscaled Blue-Green
**Rationale:** 
- Maintains inference serving capacity during upgrade
- Avoids inference latency spikes from surge drain-restart
- GPU VMs don't support live migration - every upgrade = pod restart
- Blue-green keeps old pool serving while new pool warms up

#### Pre-flight for inference
```bash
# Create A100 staging pool for validation
gcloud container node-pools create a100-test-1-32 \
  --cluster AI-PLATFORM-CLUSTER \
  --zone ZONE \
  --machine-type a2-highgpu-1g \
  --accelerator type=nvidia-tesla-a100,count=1 \
  --num-nodes 2 \
  --cluster-version 1.32.0-gke.LATEST \
  --enable-autoscaling \
  --max-nodes 5

# Test inference workloads on 1.32
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inference-test-1-32
spec:
  replicas: 2
  selector:
    matchLabels:
      app: inference-test
  template:
    metadata:
      labels:
        app: inference-test
    spec:
      nodeSelector:
        cloud.google.com/gke-nodepool: a100-test-1-32
      containers:
      - name: inference
        image: YOUR_INFERENCE_IMAGE
        resources:
          limits:
            nvidia.com/gpu: 1
EOF

# Validate inference latency/throughput on new version
curl -X POST https://INFERENCE_ENDPOINT/predict -d @sample_request.json
```

#### A100 autoscaled blue-green upgrade
```bash
# Configure autoscaled blue-green
gcloud container node-pools update a100-inference \
  --cluster AI-PLATFORM-CLUSTER \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 100 \
  --total-max-nodes 1500 \
  --enable-autoscaled-blue-green \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Execute upgrade (autoscaled blue-green respects longer termination periods)
gcloud container node-pools upgrade a100-inference \
  --cluster AI-PLATFORM-CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.0-gke.LATEST

# Monitor blue-green phases: Create → Cordon → Drain → Soak → Delete
watch 'kubectl get nodes -l node-pool=a100-inference -o wide'
```

#### Blue-green monitoring
```bash
# Track inference availability during upgrade
kubectl get pods -l app=inference-service -o wide
curl -w "@curl-format.txt" -s -o /dev/null https://INFERENCE_ENDPOINT/health

# Blue-green can be paused/resumed if issues arise
# Complete upgrade early if soak validates successfully:
gcloud container node-pools complete-upgrade a100-inference \
  --cluster AI-PLATFORM-CLUSTER --zone ZONE
```

#### Validation gate
- [ ] Inference endpoints remain available throughout upgrade
- [ ] Model loading time within SLA on new nodes
- [ ] GPU utilization metrics normal
- [ ] No CUDA compatibility issues with inference frameworks
- [ ] Autoscaler behavior normal on new node version

---

### Phase 4: H100 Training Upgrade  
**Target:** 2,000 H100 training nodes | **Duration:** 5-10 days

#### Strategy: Maintenance exclusion + manual checkpoint cycle
**Rationale:**
- Training jobs run for days/weeks - cannot tolerate mid-job eviction
- H100 nodes are most expensive/scarce - minimize disruption
- Coordinate with training team for natural checkpoint boundaries

#### Pre-flight for training
```bash
# Apply "no minor or node upgrades" exclusion to block auto-upgrades
# Allows CP patches but prevents disruptive node upgrades
gcloud container clusters update AI-PLATFORM-CLUSTER \
  --zone ZONE \
  --add-maintenance-exclusion-name "h100-training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Create H100 staging pool for extensive testing
gcloud container node-pools create h100-test-1-32 \
  --cluster AI-PLATFORM-CLUSTER \
  --zone ZONE \
  --machine-type a3-highgpu-8g \
  --accelerator type=nvidia-h100-80gb,count=8 \
  --num-nodes 4 \
  --cluster-version 1.32.0-gke.LATEST
```

#### Training workload validation (critical gate)
```bash
# Test multi-node training on 1.32 staging pool
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: h100-training-test-1-32
spec:
  parallelism: 4
  template:
    spec:
      nodeSelector:
        cloud.google.com/gke-nodepool: h100-test-1-32
      containers:
      - name: trainer
        image: YOUR_TRAINING_IMAGE
        resources:
          limits:
            nvidia.com/gpu: 8
        command: ["python", "distributed_training_test.py"]
EOF

# Validate GPUDirect-TCPX/RDMA if used (GKE 1.27.7+ required)
kubectl exec -it h100-training-test-1-32-POD -- nvidia-smi topo -m
```

#### Coordinated training upgrade
```bash
# Coordinate with ML team for checkpoint timing
# Wait for natural training job completion or planned checkpoint

# Option A: Cordon and wait (minimal disruption)
kubectl cordon -l cloud.google.com/gke-nodepool=h100-training
# Wait for jobs to complete naturally (days to weeks)

# Option B: Checkpoint-resume cycle (faster, requires coordination)  
# Save training state, scale workloads to 0, then upgrade
kubectl scale deployment training-job-1 --replicas=0
kubectl scale deployment training-job-2 --replicas=0

# Configure for H100 upgrade (fixed reservations = no surge)
gcloud container node-pools update h100-training \
  --cluster AI-PLATFORM-CLUSTER \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1  # Conservative: 1 node at a time

# Execute upgrade in batches (2,000 nodes = ~100 batches at 1 node/batch)
gcloud container node-pools upgrade h100-training \
  --cluster AI-PLATFORM-CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.0-gke.LATEST
```

#### Training-specific monitoring
```bash
# Monitor GPUDirect/RDMA topology preservation
kubectl get nodes -l node-pool=h100-training -o custom-columns=NAME:.metadata.name,ZONE:.metadata.labels.topology\\.kubernetes\\.io/zone

# Verify compact placement groups maintained
gcloud compute instances describe INSTANCE_NAME --zone ZONE --format="value(resourcePolicies)"

# Clean up staging and remove maintenance exclusion after completion
gcloud container node-pools delete h100-test-1-32 --cluster AI-PLATFORM-CLUSTER --zone ZONE

gcloud container clusters update AI-PLATFORM-CLUSTER \
  --zone ZONE \
  --remove-maintenance-exclusion-name "h100-training-protection"
```

#### Validation gate
- [ ] Multi-node training jobs resume successfully from checkpoints  
- [ ] GPU interconnect (GPUDirect-TCPX) functional
- [ ] Training throughput within expected baseline
- [ ] RDMA/high-MTU networking preserved
- [ ] Compact placement maintained for distributed training

---

## Risk Mitigation & Rollback

### Upgrade failure scenarios
1. **Deprecated API blocking auto-upgrade:** GKE automatically pauses upgrades when deprecated APIs detected
2. **GPU driver incompatibility:** CUDA version changes breaking inference/training code
3. **Resource exhaustion:** Surge nodes failing to provision on GPU reservations  
4. **Training job interruption:** Force-eviction during long-running H100 workloads

### Rollback procedures
```bash
# Node pool rollback (cannot downgrade in-place - requires new pool)
gcloud container node-pools create POOL-rollback \
  --cluster AI-PLATFORM-CLUSTER \
  --zone ZONE \
  --cluster-version 1.31.X-gke.PREVIOUS \
  --machine-type ORIGINAL_MACHINE_TYPE \
  --num-nodes ORIGINAL_SIZE

# Migrate workloads to rollback pool
kubectl cordon -l cloud.google.com/gke-nodepool=ORIGINAL_POOL
# Drain and delete original pool after workload migration
```

### Emergency procedures
- **Maintenance exclusion:** 30-day "no upgrades" freeze for critical issues
- **Blue-green abortion:** Cancel during soak period if validation fails  
- **Training job protection:** Extended `terminationGracePeriodSeconds` + `safe-to-evict=false`

---

## Timeline & Resource Requirements

### Weekly schedule
- **Week 1:** Control plane + CPU services + T4 dev (Phases 1-2)
- **Week 2:** A100 inference blue-green upgrade (Phase 3) 
- **Week 3:** H100 training coordination + checkpoint cycle start (Phase 4)
- **Week 4:** H100 upgrade completion + final validation

### Operational requirements
- **On-call coverage:** 24/7 during GPU phases (3-4)
- **ML team coordination:** Checkpoint planning for H100 training jobs
- **Monitoring:** Enhanced alerting for inference latency, training throughput
- **