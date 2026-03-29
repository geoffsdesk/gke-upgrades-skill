# GKE GPU Inference Cluster Upgrade Plan
**ML Platform Team | Standard Cluster | GPU Workloads**

## Cluster Configuration
- **Current version:** 1.31
- **Target version:** 1.32
- **Node pools:** 200x L4 (inference), 100x A100 (inference + fine-tuning)
- **Workload sensitivity:** Inference latency, 4-8 hour fine-tuning jobs

## Upgrade Strategy

### GPU Pool Strategy Selection
Given your inference latency requirements and mixed workloads, recommend **autoscaled blue-green** for both pools:

**Why autoscaled blue-green for GPU inference:**
- Avoids inference latency spikes from pod restarts (GPU VMs don't support live migration)
- Keeps old pool serving while new pool warms up
- Auto-scales replacement capacity, avoiding 2x resource cost of standard blue-green
- Respects longer graceful termination periods for fine-tuning jobs (8+ hours)

**Alternative for L4 inference-only pool:** Could use surge with `maxSurge=0, maxUnavailable=1` if capacity constraints exist, but this causes temporary inference capacity loss.

## Pre-Upgrade Checklist

```
GPU ML Platform Upgrade Checklist
- [ ] Cluster: ___ | Mode: Standard | Channel: ___
- [ ] Current version: 1.31 | Target version: 1.32

GPU-Specific Validation
- [ ] GPU driver compatibility confirmed between 1.31 → 1.32 (test in staging cluster)
- [ ] CUDA version changes validated with representative inference models
- [ ] GPU reservation headroom checked for autoscaled blue-green capacity
- [ ] Model serving framework (TensorFlow Serving, TorchServe, etc.) compatible with target version
- [ ] GPUDirect/RDMA networking tested if using high-performance interconnect

Fine-tuning Job Protection
- [ ] Active fine-tuning jobs inventory completed
- [ ] Job checkpoint/resume capability verified
- [ ] PDBs configured for fine-tuning workloads
- [ ] Maintenance window scheduled during low fine-tuning activity

Infrastructure Readiness
- [ ] Autoscaling enabled on both GPU pools with appropriate min/max limits
- [ ] Sufficient GPU quota for blue-green replacement pools (check reservations)
- [ ] Inference traffic load balancing validated (can handle temporary capacity shifts)
- [ ] Baseline metrics captured: inference latency (p50/p95/p99), throughput, GPU utilization
```

## Upgrade Sequence & Commands

### Phase 1: Control Plane Upgrade
```bash
# Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32

# Monitor completion (~10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Phase 2: L4 Inference Pool (Lower Risk First)
```bash
# Configure autoscaled blue-green for L4 pool
gcloud container node-pools update l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 50 --total-max-nodes 300 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Start upgrade
gcloud container node-pools upgrade l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor autoscaled blue-green progress
kubectl get nodes -l cloud.google.com/gke-nodepool=l4-inference-pool -o wide
kubectl get pods -l accelerator=nvidia-l4 -o wide
```

### Phase 3: A100 Mixed Pool (After L4 Validation)
**Wait 2-4 hours after L4 upgrade completes to validate inference performance**

```bash
# Check for active fine-tuning jobs
kubectl get pods -l accelerator=nvidia-tesla-a100 | grep -E "Running.*[4-9]h|Running.*[1-9][0-9]h"

# Configure autoscaled blue-green for A100 pool
gcloud container node-pools update a100-mixed-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 25 --total-max-nodes 150 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.20,blue-green-full-batch-timeout=7200s

# Start upgrade (only when no long-running fine-tuning jobs active)
gcloud container node-pools upgrade a100-mixed-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

## Monitoring During Upgrade

### Inference Performance Monitoring
```bash
# Monitor inference latency via metrics
kubectl top nodes -l accelerator=nvidia-l4
kubectl top nodes -l accelerator=nvidia-tesla-a100

# Check for inference serving pod disruptions
kubectl get events -A --field-selector reason=EvictionBlocked,reason=PodEvicted

# Monitor GPU utilization
kubectl describe nodes -l accelerator=nvidia-l4 | grep -A5 "nvidia.com/gpu"
```

### Fine-tuning Job Protection
```bash
# Monitor long-running jobs during A100 upgrade
kubectl get pods -l job-type=fine-tuning -o custom-columns=NAME:.metadata.name,AGE:.status.startTime,NODE:.spec.nodeName

# Check PDB violations
kubectl get pdb -A -o wide | grep -v "0.*0"
```

## Risk Mitigation

### GPU-Specific Risks
1. **GPU driver incompatibility:** Test target GKE version in staging with representative models first
2. **CUDA version changes:** May break inference containers — validate before production
3. **Inference latency spikes:** Autoscaled blue-green keeps old pool active during transition
4. **Fine-tuning job eviction:** 8-hour jobs exceed GKE's 1-hour surge timeout — autoscaled blue-green respects longer termination periods

### Capacity Management
1. **GPU reservation limits:** Autoscaled blue-green requires capacity for replacement nodes — verify headroom
2. **Autoscaler conflicts:** May create nodes at old version during upgrade — acceptable, upgrade will catch up
3. **Load balancer behavior:** Ensure inference traffic can handle gradual node transitions

## Rollback Plan

### If inference performance degrades after L4 upgrade:
```bash
# Create new L4 pool at 1.31
gcloud container node-pools create l4-inference-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31 \
  --machine-type g2-standard-48 \
  --accelerator type=nvidia-l4,count=4 \
  --num-nodes 50 \
  --enable-autoscaling --min-nodes 50 --max-nodes 300

# Migrate inference workloads
kubectl cordon -l cloud.google.com/gke-nodepool=l4-inference-pool
# Wait for traffic to shift to rollback pool
kubectl delete nodepool l4-inference-pool
```

### If A100 fine-tuning jobs fail:
- Jobs with checkpoints can resume on new nodes
- Jobs without checkpoints will need to restart (accept this risk or wait for completion)

## Timeline Estimate

- **Control plane upgrade:** 10-15 minutes
- **L4 pool (200 nodes):** 4-6 hours (autoscaled blue-green with gradual transition)
- **Validation window:** 2-4 hours (monitor inference performance)
- **A100 pool (100 nodes):** 2-3 hours (smaller pool, faster transition)
- **Total upgrade window:** 8-12 hours

## Post-Upgrade Validation

```bash
# Verify all GPU nodes at 1.32
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# Confirm GPU driver versions
kubectl describe nodes -l accelerator | grep "nvidia.com/gpu"

# Validate inference endpoints
curl -X POST INFERENCE_ENDPOINT/predict -d @sample_request.json

# Check fine-tuning job resume capability
kubectl logs -l job-type=fine-tuning | grep -i checkpoint
```

## Key Success Factors

1. **Stage in order:** L4 inference → validate → A100 mixed (lower risk first)
2. **Timing:** Upgrade A100 pool during low fine-tuning activity periods
3. **Autoscaled blue-green:** Essential for GPU inference to avoid latency spikes
4. **Driver validation:** Test GPU driver + CUDA changes in staging before production
5. **Capacity planning:** Verify GPU quota can handle blue-green replacement pools

This approach prioritizes inference availability while protecting long-running fine-tuning jobs through GKE's autoscaled blue-green strategy designed specifically for GPU workloads.