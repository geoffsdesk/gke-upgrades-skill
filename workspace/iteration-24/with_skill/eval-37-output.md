# GKE AI/ML Fleet Upgrade Plan: 1.31 → 1.32

**Fleet Overview:**
- **Total nodes:** 5,000 (mixed AI/ML workloads)
- **Current:** GKE 1.31 → **Target:** GKE 1.32
- **Critical constraints:** Training continuity (H100), inference availability (A100)
- **Cluster mode:** Standard (assumed for GPU node pool management)

## Executive Summary

**Timeline:** 3-4 weeks total with careful sequencing
**Key principle:** Non-disruptive pools first, inference pools with blue-green protection, training pools only during scheduled gaps

## Phase 1: Foundation & Development (Week 1)

### Priority: CPU services + T4 development pools
**Rationale:** Lowest risk, establishes upgrade confidence, validates new version behavior

#### CPU Services Pool (1,000 nodes)
```bash
# Configure surge for stateless services
gcloud container node-pools update cpu-services \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 50 \
  --max-unavailable-upgrade 0

# Control plane upgrade first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.xxx

# Node pool upgrade (batched)
gcloud container node-pools upgrade cpu-services \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxx
```
**Expected duration:** 8-12 hours for 1,000 nodes (GKE upgrades ~20 nodes simultaneously)

#### T4 Development Pool (500 nodes)
```bash
# GPU pools: maxUnavailable is the primary lever (no surge capacity assumed)
gcloud container node-pools update t4-dev \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2

gcloud container node-pools upgrade t4-dev \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxx
```
**Expected duration:** 6-8 hours
**Validation:** Test GPU driver compatibility, CUDA version changes, dev workload functionality

## Phase 2: Inference Pools (Week 2)

### Priority: A100 inference pools with blue-green protection
**Rationale:** Minimize inference latency spikes, maintain serving capacity throughout upgrade

#### A100 Inference Pools (1,500 nodes)
**Strategy:** Autoscaled blue-green upgrade to avoid inference interruption

```bash
# Enable autoscaling (required for autoscaled blue-green)
gcloud container node-pools update a100-inference \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 1400 \
  --total-max-nodes 1800

# Configure autoscaled blue-green
gcloud container node-pools update a100-inference \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --strategy=AUTOSCALED_BLUE_GREEN \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Upgrade
gcloud container node-pools upgrade a100-inference \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxx
```

**Expected duration:** 12-16 hours (autoscaled blue-green is deliberate)
**Benefits:** Keeps old pool serving while new pool warms up, scales down blue pool as green pool scales up (cost-efficient)
**Critical validation:** Verify inference latency, model loading times, throughput post-upgrade

## Phase 3: Training Pool Preparation (Week 3)

### H100 Training Pools (2,000 nodes) - Preparation Phase

**Critical constraint:** Training jobs cannot be interrupted mid-run. Coordinate with training teams.

#### Pre-upgrade steps:
```bash
# Block auto-upgrades during active training
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-protection" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+14 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**Coordination checklist:**
- [ ] Training team confirms no active multi-day jobs
- [ ] Checkpoint all running jobs to persistent storage
- [ ] Verify GPUDirect-TCPX/RDMA configuration will survive upgrade
- [ ] Confirm compact placement policies for replacement nodes

## Phase 4: Training Pool Execution (Week 4)

### H100 Training Pools (2,000 nodes) - Upgrade Execution

**Strategy:** Parallel host maintenance approach for fastest completion

```bash
# Option A: Parallel upgrade (if training can tolerate full restart)
# Scale training workloads to zero first
kubectl scale deployment training-job-1 --replicas=0
kubectl scale statefulset distributed-training --replicas=0

# Apply maintenance label to all H100 nodes simultaneously
kubectl label nodes -l cloud.google.com/gke-nodepool=h100-training \
  cloud.google.com/perform-maintenance=true

# Upgrade all H100 pools
gcloud container node-pools upgrade h100-training \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxx
```

**Expected duration:** 4-6 hours (parallel approach)
**Risk mitigation:** Full training restart, but fastest total time

```bash
# Option B: Rolling upgrade (if some training capacity must remain)
# Upgrade pools sequentially with cordon/drain pattern
for pool in h100-training-zone-a h100-training-zone-b h100-training-zone-c; do
  gcloud container node-pools update $pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 10
  
  gcloud container node-pools upgrade $pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version 1.32.x-gke.xxx
  
  # Wait for completion before next zone
  sleep 7200  # 2-hour soak between zones
done
```

**Expected duration:** 12-18 hours (rolling approach)

## Critical Validation Points

### Post-Control Plane Upgrade
```bash
# Verify API compatibility
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Check system component health
kubectl get pods -n kube-system | grep -v Running

# Validate HPA/VPA behavior (common regression point)
kubectl describe hpa -A | grep -A5 "Current"
```

### Post-GPU Pool Upgrades
```bash
# GPU driver verification
kubectl run gpu-test --image=tensorflow/tensorflow:latest-gpu \
  --rm -it --restart=Never -- python -c "import tensorflow as tf; print(tf.test.is_gpu_available())"

# CUDA version check
kubectl run cuda-check --image=nvidia/cuda:11.8-runtime-ubuntu20.04 \
  --rm -it --restart=Never -- nvcc --version

# GPUDirect-TCPX validation (if applicable)
kubectl run tcpx-test --image=TCPX_TEST_IMAGE \
  --rm -it --restart=Never -- /test-rdma-topology.sh
```

### Training Workload Restart
```bash
# Scale training back up
kubectl scale deployment training-job-1 --replicas=ORIGINAL_COUNT
kubectl scale statefulset distributed-training --replicas=ORIGINAL_COUNT

# Monitor distributed training health
kubectl logs -f distributed-training-0 | grep -i "collective\|nccl\|horovod"

# Verify checkpoint resumption
kubectl exec distributed-training-0 -- ls -la /checkpoints/
```

## Risk Mitigation

### GPU Capacity Constraints
- **H100/A100 pools:** Assume NO surge capacity available (fixed reservations)
- **Primary strategy:** `maxUnavailable` mode for GPU pools
- **Fallback:** If upgrade fails due to capacity, contact Customer Care for temporary quota increase

### Training Job Protection
```bash
# Emergency rollback for training pools (if needed)
gcloud container node-pools create h100-training-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.xxx \
  --num-nodes 2000 \
  --machine-type a3-highgpu-8g

# Migrate workloads back
kubectl cordon -l cloud.google.com/gke-nodepool=h100-training
```

### Version Compatibility Risks
- **GPU driver changes:** 1.31→1.32 may change CUDA versions - validate in T4 dev pools first
- **API behavioral changes:** Monitor HPA scaling decisions, VPA recommendations
- **Admission webhook compatibility:** cert-manager, policy controllers may need updates

## Timeline Summary

| Week | Phase | Pools | Risk Level | Duration |
|------|-------|-------|------------|----------|
| 1 | Foundation | CPU (1,000) + T4 Dev (500) | **Low** | 14-20 hours |
| 2 | Inference | A100 Inference (1,500) | **Medium** | 12-16 hours |
| 3 | Preparation | H100 Training coordination | **High** | Planning only |
| 4 | Training | H100 Training (2,000) | **High** | 4-18 hours* |

**Total fleet upgrade time:** 42-54 hours of actual upgrade work spread over 3-4 weeks

## Success Criteria

- [ ] All 5,000 nodes at GKE 1.32
- [ ] Zero training job data loss (checkpoint/resume verified)
- [ ] Inference SLA maintained (< 1% error rate increase)
- [ ] GPU workloads validated (CUDA, driver compatibility)
- [ ] No deprecated API usage detected
- [ ] All system components healthy

## Emergency Contacts & Escalation

- **Training disruption:** Coordinate with ML Platform team lead
- **Inference outage:** Page on-call SRE, implement traffic failover
- **Stuck upgrades:** GKE support with cluster name, zone, operation ID
- **Quota issues:** Customer Care for emergency capacity increase

**Next recommended upgrade:** Plan 1.32→1.33 in 3-6 months following the same phased approach.