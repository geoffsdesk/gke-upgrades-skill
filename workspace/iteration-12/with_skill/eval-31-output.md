# GKE Upgrade Plan: Large-Scale LLM Training Cluster

## Cluster Profile
- **Mode:** GKE Standard
- **Scale:** 512 H100 nodes (A3 Mega, 8 GPUs per node = 4,096 H100s total)
- **Workload:** Multi-week LLM training (2-3 weeks per run)
- **Networking:** GPUDirect-TCPXO inter-node communication
- **Current:** GKE 1.31 → **Target:** GKE 1.32
- **Critical constraint:** Cannot interrupt active training runs

## Key Challenges & Solutions

### 1. GPU Interconnect Compatibility ✅
**Good news:** GPUDirect-TCPXO is supported on both GKE 1.31 and 1.32. This upgrade path should preserve your GPU interconnect functionality.

**Verification required:**
- Test NCCL communication benchmarks on 1.32 in a staging environment
- Confirm A3 Mega + H100 driver compatibility with target node image
- Validate RDMA/InfiniBand topology survives node replacement

### 2. Training Job Protection Strategy

**Recommended approach:** Dedicated training vs. infrastructure node pools

```bash
# Create dedicated training node pool (if not already separated)
gcloud container node-pools create training-pool \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --machine-type a3-megagpu-8g \
  --num-nodes 512 \
  --cluster-version 1.31.x \
  --enable-autorepair \
  --enable-autoupgrade=false \  # CRITICAL: Disable auto-upgrade
  --node-labels=workload=training,upgrade-policy=manual
```

**Maintenance exclusion for training pool:**
```bash
# Block ALL upgrades on training pool during active runs
gcloud container node-pools update training-pool \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "training-campaign-q1" \
  --add-maintenance-exclusion-start-time 2024-01-15T00:00:00Z \
  --add-maintenance-exclusion-end-time 2024-04-01T00:00:00Z \
  --add-maintenance-exclusion-scope no_upgrades
```

### 3. Staged Upgrade Strategy

**Phase 1: Control Plane + Infrastructure (Non-disruptive)**
```bash
# Upgrade control plane first (no training impact)
gcloud container clusters upgrade YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --master \
  --cluster-version 1.32.x

# Upgrade non-GPU node pools (system, monitoring, etc.)
gcloud container node-pools upgrade system-pool \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --cluster-version 1.32.x
```

**Phase 2: GPU Node Pool (Scheduled between training runs)**
- Wait for current training run to complete and checkpoint
- Schedule upgrade during the gap between training campaigns
- Use autoscaled blue-green upgrade to minimize risk

### 4. GPU-Optimized Upgrade Configuration

**For 512-node GPU pool, use autoscaled blue-green:**
```bash
# Configure autoscaled blue-green upgrade (preserves capacity)
gcloud container node-pools update training-pool \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --enable-blue-green-autoscaled-node-upgrade \
  --blue-green-node-pool-soak-duration 1h \
  --max-unavailable-upgrade 0 \
  --max-surge-upgrade 0
```

**Critical considerations:**
- **Capacity requirement:** Autoscaled blue-green needs capacity for replacement nodes. With 512 A3 Mega nodes, verify your reservation covers this.
- **If no surge capacity available:** Use sequential drain approach with `maxUnavailable=20` (respects GKE's ~20 node max parallelism)
- **Compact placement:** Verify replacement nodes maintain RDMA topology in the same placement group

### 5. Pre-Upgrade Validation Checklist

```bash
# Checkpoint active training job
kubectl exec -it TRAINING_POD -- /checkpoint-script.sh

# Verify GPU driver compatibility
gcloud container get-server-config --zone YOUR_ZONE \
  --format="yaml(validNodeVersions)" | grep 1.32

# Test interconnect on staging cluster
# Deploy NCCL all-reduce benchmark on 1.32 staging cluster
kubectl apply -f nccl-benchmark.yaml

# Verify reservation capacity
gcloud compute reservations list --filter="name~a3-mega"
```

**Training Job Protection:**
```bash
# Configure PDB for training workload (prevents eviction)
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
spec:
  minAvailable: "100%"  # Prevent ANY eviction during training
  selector:
    matchLabels:
      workload: llm-training
```

### 6. Execution Timeline

**Immediate (Control Plane):**
```bash
# Upgrade control plane (safe during active training)
gcloud container clusters upgrade YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --master \
  --cluster-version 1.32.x
```

**Next training gap (GPU nodes):**
1. Ensure training job checkpointed and stopped
2. Remove/relax PDB temporarily
3. Execute autoscaled blue-green upgrade of training pool
4. Validate GPU interconnect with NCCL benchmarks
5. Resume training from checkpoint

### 7. Rollback Plan

**If interconnect issues detected:**
```bash
# Create new pool at 1.31 (faster than rolling back)
gcloud container node-pools create training-pool-rollback \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --machine-type a3-megagpu-8g \
  --cluster-version 1.31.x \
  --num-nodes 512 \
  --enable-autoupgrade=false

# Migrate training workload back
kubectl cordon -l cloud.google.com/gke-nodepool=training-pool
# Drain and reschedule on rollback pool
```

## Maintenance Runbook

### Pre-flight Commands
```bash
# Current state
gcloud container clusters describe YOUR_CLUSTER --zone YOUR_ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Active training jobs
kubectl get pods -l workload=llm-training -o wide

# GPU topology health
kubectl get nodes -l workload=training -o yaml | grep topology.gke.io
```

### Upgrade Execution
```bash
# Phase 1: Control plane (safe during training)
gcloud container clusters upgrade YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --master \
  --cluster-version 1.32.x

# Phase 2: Training pool (only between runs)
gcloud container node-pools upgrade training-pool \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --cluster-version 1.32.x
```

### Validation
```bash
# Node health
kubectl get nodes -l workload=training

# GPU driver version
kubectl describe nodes -l workload=training | grep nvidia.com/gpu

# Interconnect test (deploy NCCL benchmark)
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: nccl-test
spec:
  template:
    spec:
      containers:
      - name: nccl-test
        image: nvcr.io/nvidia/nccl-tests:latest
        command: ["/usr/local/bin/all_reduce_perf", "-b", "1G", "-e", "8G"]
        resources:
          limits:
            nvidia.com/gpu: 8
      nodeSelector:
        workload: training
      restartPolicy: Never
EOF
```

## Expected Timeline
- **Control plane upgrade:** ~15 minutes (no training impact)
- **GPU node pool upgrade:** 4-6 hours for 512 nodes (20 nodes parallel max)
- **Total maintenance window:** Plan 8-hour weekend window between training runs

## Risk Mitigation
- ✅ Control plane upgrade is non-disruptive to running training
- ✅ Training pool upgrade only during scheduled gaps
- ✅ Autoscaled blue-green minimizes capacity disruption risk
- ✅ PDB prevents accidental training job eviction
- ✅ Rollback plan via new node pool creation

Your GPUDirect-TCPXO interconnect should survive this upgrade path, but stage the GPU node upgrade carefully between training campaigns to avoid disrupting multi-week runs.