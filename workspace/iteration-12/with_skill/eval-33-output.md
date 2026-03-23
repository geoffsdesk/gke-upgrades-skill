# GKE Upgrade Plan: ML Platform GPU Clusters (1.31 → 1.32)

## Cluster Profile
- **Cluster**: GKE Standard with GPU workloads
- **Current**: 1.31 → **Target**: 1.32
- **Node Pools**: 
  - L4 pool (200 nodes) - inference workloads
  - A100 pool (100 nodes) - inference + fine-tuning (4-8h jobs)
- **Workload**: Latency-sensitive inference + long-running training

## Upgrade Strategy

### Control Plane First
Upgrade control plane during low-traffic period. This has minimal impact on running workloads.

### Node Pool Strategy: Rolling with Inference Protection

**L4 Pool (Inference-focused):**
- **Strategy**: Rolling surge upgrade with conservative settings
- **Settings**: `maxSurge=0, maxUnavailable=1`
- **Rationale**: L4 nodes likely have fixed GPU reservations with no surge capacity. Using `maxUnavailable=1` drains one node at a time without needing extra GPUs. This creates brief capacity dips but maintains most inference capacity.

**A100 Pool (Mixed workloads):**
- **Strategy**: Autoscaled blue-green upgrade (GKE's new strategy)
- **Rationale**: Handles long-running fine-tuning jobs gracefully by allowing controlled transitions with longer eviction periods. Green pool scales up based on demand while blue pool scales down as jobs complete.

### Timing Coordination
1. **Schedule during low-traffic hours** for L4 pool upgrade
2. **Coordinate with ML team** to pause new fine-tuning jobs during A100 upgrade
3. **Stagger pools**: Upgrade L4 first (faster), then A100 when no active training

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist - ML Platform GPU Clusters
- [ ] Cluster: ML_PLATFORM | Mode: Standard | Channel: ___
- [ ] Current version: 1.31 | Target version: 1.32

GPU-Specific Compatibility
- [ ] Target version available in release channel
- [ ] CUDA driver compatibility verified with GKE 1.32 node image
- [ ] L4/A100 driver versions tested in staging cluster
- [ ] Inference framework (TensorFlow/PyTorch) compatible with new driver
- [ ] Fine-tuning pipelines tested against 1.32

Workload Protection
- [ ] PDBs configured for inference deployments (allow 10-20% disruption)
- [ ] Active fine-tuning jobs inventory completed
- [ ] Inference autoscaler min replicas set appropriately
- [ ] Long-running job checkpoint/resume capability verified
- [ ] GPU reservations confirmed (no surge capacity assumed)

Infrastructure Readiness
- [ ] L4 pool: maxSurge=0, maxUnavailable=1 (conservative rolling)
- [ ] A100 pool: autoscaled blue-green configured
- [ ] Maintenance window: Low-traffic hours (e.g., 2-6 AM PST)
- [ ] Monitoring dashboards active (GPU utilization, inference latency)
- [ ] Baseline metrics captured (QPS, p95 latency, job completion rates)

Coordination
- [ ] ML team notified: pause new fine-tuning jobs during A100 upgrade
- [ ] Traffic routing: can shift load between clusters if needed
- [ ] Rollback plan: new node pool at 1.31 ready to create if needed
```

## Upgrade Runbook

### Phase 1: Control Plane (Minimal impact)

```bash
# Upgrade control plane first
gcloud container clusters upgrade ML_PLATFORM_CLUSTER \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.xxxxx

# Verify control plane (wait ~15 minutes)
gcloud container clusters describe ML_PLATFORM_CLUSTER \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Phase 2: L4 Pool (Inference) - Conservative Rolling

```bash
# Configure conservative settings for L4 pool
gcloud container node-pools update l4-inference-pool \
  --cluster ML_PLATFORM_CLUSTER \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

# Start L4 pool upgrade
gcloud container node-pools upgrade l4-inference-pool \
  --cluster ML_PLATFORM_CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxxxx

# Monitor inference capacity and latency
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=l4-inference-pool'
# Monitor inference pod distribution
kubectl get pods -l app=inference -o wide
```

### Phase 3: A100 Pool (Training) - Autoscaled Blue-Green

```bash
# Pause new fine-tuning job submissions
# (Coordinate with ML team)

# Configure autoscaled blue-green for A100 pool
gcloud container node-pools update a100-training-pool \
  --cluster ML_PLATFORM_CLUSTER \
  --zone ZONE \
  --enable-autoscaled-blue-green-upgrade \
  --node-pool-soak-duration 1800s  # 30 min soak time

# Start A100 pool upgrade
gcloud container node-pools upgrade a100-training-pool \
  --cluster ML_PLATFORM_CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxxxx

# Monitor training job completion on blue pool
kubectl get pods -l workload-type=training -o wide
```

## GPU-Specific Validation

```bash
# Verify GPU drivers post-upgrade
kubectl get nodes -l accelerator=nvidia-l4 -o yaml | grep nvidia.com/gpu
kubectl get nodes -l accelerator=nvidia-tesla-a100 -o yaml | grep nvidia.com/gpu

# Test GPU availability
kubectl run gpu-test --rm -it --restart=Never \
  --image=nvidia/cuda:11.8-runtime-ubuntu20.04 \
  --overrides='{"spec":{"nodeSelector":{"cloud.google.com/gke-nodepool":"l4-inference-pool"},"containers":[{"name":"gpu-test","image":"nvidia/cuda:11.8-runtime-ubuntu20.04","command":["nvidia-smi"],"resources":{"limits":{"nvidia.com/gpu":"1"}}}]}}' \
  -- nvidia-smi

# Verify inference endpoints responding
curl -X POST http://INFERENCE_ENDPOINT/predict -d '{"test": "data"}'

# Check training job resume capability
kubectl get jobs -l workload-type=training
```

## Monitoring During Upgrade

**Key Metrics to Watch:**
- GPU utilization (`kubectl top nodes`)
- Inference request latency (p95, p99)
- Training job completion rates
- Node pool readiness
- Pod eviction events

**Alert Thresholds:**
- Inference latency >2x baseline → pause upgrade
- GPU utilization drops >50% → verify pod rescheduling
- Training jobs failing to restart → check driver compatibility

## Expected Timeline

- **Control Plane**: 15 minutes
- **L4 Pool** (200 nodes, 1 at a time): ~6-8 hours
- **A100 Pool** (100 nodes, blue-green): ~2-4 hours depending on job completion
- **Total Window**: 10-14 hours

## Rollback Plan

If inference degradation occurs:

```bash
# Create new node pool at 1.31 for emergency rollback
gcloud container node-pools create l4-inference-rollback \
  --cluster ML_PLATFORM_CLUSTER \
  --zone ZONE \
  --cluster-version 1.31.x-gke.xxxxx \
  --machine-type g2-standard-12 \
  --accelerator type=nvidia-l4,count=1 \
  --num-nodes 10

# Scale up rollback pool
gcloud container node-pools update l4-inference-rollback \
  --cluster ML_PLATFORM_CLUSTER \
  --zone ZONE \
  --enable-autoscaling \
  --min-nodes 10 \
  --max-nodes 200

# Cordon problematic nodes and let autoscaler migrate workloads
kubectl cordon -l cloud.google.com/gke-nodepool=l4-inference-pool
```

## Post-Upgrade Validation

```
Post-Upgrade Checklist - GPU Clusters
- [ ] All nodes at 1.32: `kubectl get nodes -o wide`
- [ ] GPU driver versions: `kubectl describe nodes | grep nvidia`
- [ ] Inference latency within baseline (±10%)
- [ ] GPU utilization restored to pre-upgrade levels
- [ ] Training jobs resuming successfully from checkpoints
- [ ] Autoscaler responding correctly to traffic spikes
- [ ] No GPU allocation errors in pod events
- [ ] Fine-tuning job submissions re-enabled
```

This strategy minimizes inference disruption by using conservative rolling upgrades for L4 nodes and protecting long-running training jobs with blue-green upgrades for A100 nodes. The key is sequencing and coordination with your ML team.