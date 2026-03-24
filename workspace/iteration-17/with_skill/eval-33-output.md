# ML Inference Platform Upgrade Plan: 1.31 → 1.32

## Cluster Profile
- **Environment**: Production ML inference + fine-tuning
- **Scale**: 200 L4 nodes (inference) + 100 A100 nodes (inference + fine-tuning)
- **Current**: 1.31 → **Target**: 1.32
- **Constraints**: Minimize inference latency/availability impact, protect 4-8h fine-tuning jobs

## Upgrade Strategy Overview

**Recommended approach**: Rolling upgrades with **inference-first sequencing** using autoscaled blue-green for GPU pools to maintain serving capacity throughout the upgrade while respecting long-running jobs.

### Key Strategy Decisions

1. **Control Plane**: Manual upgrade during low-traffic window with two-step upgrade for rollback safety
2. **L4 Pool (inference-only)**: Autoscaled blue-green — maintains serving capacity, no job protection needed
3. **A100 Pool (inference + fine-tuning)**: Autoscaled blue-green with job coordination — protects long-running training
4. **Sequencing**: Control plane → L4 pool → A100 pool (inference workloads validate first)

## Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist
- [ ] Cluster: ML_PLATFORM | Mode: Standard | Channel: ___
- [ ] Current version: 1.31.x | Target version: 1.32.x

Version Compatibility
- [ ] 1.32 available in release channel (`gcloud container get-server-config --zone ZONE --format="yaml(channels)"`)
- [ ] GKE 1.32 release notes reviewed for GPU/ML workload changes
- [ ] GPU driver compatibility confirmed (1.32 may change CUDA version)
- [ ] TensorFlow/PyTorch framework compatibility verified with 1.32 GPU drivers
- [ ] ML serving frameworks (TensorRT, Triton) tested against 1.32

GPU Infrastructure Readiness
- [ ] GPU reservations reviewed — no surge capacity available for L4/A100 pools
- [ ] Autoscaled blue-green strategy confirmed for both GPU pools
- [ ] Current fine-tuning job schedule mapped (identify 4-8h job windows)
- [ ] Cluster autoscaler settings verified (scaling limits, node group priorities)

Workload Protection
- [ ] PDBs configured for inference services (recommend minAvailable: 70% for L4, 50% for A100)
- [ ] Fine-tuning jobs have checkpointing enabled (resume after node migration)
- [ ] No bare pods — all workloads managed by Deployments/StatefulSets/Jobs
- [ ] terminationGracePeriodSeconds adequate (recommend 120s for inference, 600s for training)
- [ ] Inference traffic load balancing verified (can handle capacity fluctuations)

Monitoring & Ops
- [ ] Baseline metrics captured: inference latency (p50/p95/p99), throughput, error rates
- [ ] GPU utilization and job completion rates baselined
- [ ] Upgrade window scheduled during off-peak inference traffic
- [ ] On-call team available for monitoring
```

## Detailed Upgrade Plan

### Phase 1: Control Plane Upgrade (Manual, Two-Step)

**Timing**: During lowest inference traffic period (typically 2-6 AM in your timezone)

```bash
# Two-step upgrade for rollback safety (Preview feature)
gcloud beta container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.xxx \
  --control-plane-soak-duration 6h

# Monitor control plane health
kubectl get pods -n kube-system
kubectl get componentstatuses
```

**Validation**: During 6-hour soak period, monitor inference latency and API responsiveness. If issues arise, rollback is possible:
```bash
# Rollback during soak period (if needed)
gcloud beta container clusters rollback CLUSTER_NAME --zone ZONE
```

After soak validation passes:
```bash
# Complete control plane upgrade
gcloud beta container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --complete-control-plane-upgrade
```

### Phase 2: L4 Inference Pool Upgrade (Autoscaled Blue-Green)

**Why L4 first**: Inference-only workloads, no long-running jobs to protect. Validates GPU driver compatibility before A100 upgrade.

```bash
# Configure autoscaling for blue-green
gcloud container node-pools update l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 50 \
  --total-max-nodes 300 \
  --strategy AUTOSCALED_BLUE_GREEN \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Trigger upgrade
gcloud container node-pools upgrade l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxx
```

**Expected behavior**: 
- Green pool starts with 25% of current capacity (~50 nodes)
- As inference traffic migrates, green pool scales up automatically
- Blue pool scales down as workloads drain
- Total capacity maintained throughout

**Validation during L4 upgrade**:
```bash
# Monitor node distribution and autoscaling
kubectl get nodes -o wide -l cloud.google.com/gke-nodepool=l4-inference-pool
kubectl get pods -n ml-inference -o wide | grep l4

# Check inference latency (replace with your monitoring)
# Ensure p95 latency stays within 20% of baseline
```

### Phase 3: A100 Pool Upgrade (Coordinated Blue-Green)

**Coordination required**: Protect running fine-tuning jobs, maintain inference capacity.

**Step 3a**: Check for running fine-tuning jobs
```bash
# Identify long-running training jobs
kubectl get jobs -n ml-training -o wide
kubectl get pods -n ml-training --field-selector=status.phase=Running \
  -o custom-columns="NAME:.metadata.name,NODE:.spec.nodeName,AGE:.status.startTime"

# Wait for jobs <2h remaining to complete, or checkpoint longer jobs
```

**Step 3b**: Configure and trigger A100 upgrade
```bash
# Configure autoscaling with extended timeout for training workloads
gcloud container node-pools update a100-mixed-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 25 \
  --total-max-nodes 150 \
  --strategy AUTOSCALED_BLUE_GREEN \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.30,blue-green-full-batch-timeout=7200s

# Trigger upgrade
gcloud container node-pools upgrade a100-mixed-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxx
```

**Expected behavior**:
- Green pool creates ~30 A100 nodes initially
- Inference workloads migrate quickly (2-3 minutes)
- Training jobs drain gracefully respecting terminationGracePeriodSeconds (up to 10 minutes)
- Blue pool scales down as workloads complete migration

### Phase 4: Post-Upgrade Validation

```bash
# Verify all nodes upgraded
kubectl get nodes -o custom-columns="NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,POOL:.metadata.labels.cloud\.google\.com/gke-nodepool"

# Check GPU driver version
kubectl describe nodes | grep -A5 "nvidia.com/gpu"

# Validate inference workloads
kubectl get pods -n ml-inference -o wide
kubectl get svc -n ml-inference

# Validate training job capability
kubectl run gpu-test --image=nvidia/cuda:11.8-runtime-ubuntu20.04 \
  --limits=nvidia.com/gpu=1 --rm -it -- nvidia-smi

# Check autoscaler behavior
kubectl get events -n kube-system --field-selector=source=cluster-autoscaler --sort-by='.lastTimestamp' | tail -10
```

## GPU-Specific Considerations

### Driver Compatibility Validation
```bash
# Before upgrade: capture current driver version
kubectl run driver-check --image=nvidia/cuda:11.8-runtime-ubuntu20.04 \
  --limits=nvidia.com/gpu=1 --rm -it -- nvidia-smi --query-gpu=driver_version --format=csv

# After upgrade: verify inference/training still works
# Test inference latency with production traffic sample
# Run short training job to verify CUDA compatibility
```

### Why Autoscaled Blue-Green for GPU Pools

**Standard surge upgrade issues for GPU**:
- No surge GPU capacity available (reservations are fixed)
- maxUnavailable=1 would drain nodes serially → very slow for 200-300 node pools
- Training jobs would be force-evicted after 1 hour

**Autoscaled blue-green advantages**:
- Creates replacement capacity before draining (maintains serving capacity)
- Respects longer termination grace periods for training jobs
- Scales efficiently — old pool scales down as new pool scales up
- Cost-effective compared to standard blue-green (no 2x resource requirement)

### Inference Availability Protection

**PDB Configuration**:
```yaml
# L4 inference pool PDB
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: l4-inference-pdb
spec:
  minAvailable: 70%  # Maintain serving capacity during upgrades
  selector:
    matchLabels:
      workload-type: inference
      gpu-type: l4
---
# A100 inference PDB  
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: a100-inference-pdb
spec:
  minAvailable: 50%  # More conservative due to mixed workload
  selector:
    matchLabels:
      workload-type: inference
      gpu-type: a100
```

## Rollback Plan

**Control Plane**: During 6h soak period, rollback with `gcloud beta container clusters rollback`

**Node Pools**: Create new pools at 1.31, migrate workloads:
```bash
# Emergency rollback for L4 pool
gcloud container node-pools create l4-inference-pool-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.xxx \
  --machine-type g2-standard-12 \
  --accelerator type=nvidia-l4,count=1 \
  --num-nodes 50 \
  --enable-autoscaling --min-nodes 50 --max-nodes 300

# Cordon upgraded pool, let autoscaler migrate workloads
kubectl cordon -l cloud.google.com/gke-nodepool=l4-inference-pool
```

## Timeline Estimate

- **Control Plane**: 30 minutes + 6h soak = ~6.5 hours
- **L4 Pool** (200 nodes): 2-3 hours with autoscaled blue-green
- **A100 Pool** (100 nodes): 1-2 hours with job coordination
- **Total**: 8-10 hours for complete upgrade

**Recommended schedule**: Start Friday evening, complete over weekend to minimize business impact.

## Success Criteria

✅ **Performance**: Inference p95 latency within 10% of baseline  
✅ **Availability**: No inference service downtime >30 seconds  
✅ **Training**: All fine-tuning jobs complete or checkpoint successfully  
✅ **Infrastructure**: All nodes at 1.32, GPU drivers functional  
✅ **Autoscaling**: Cluster autoscaler responsive to traffic patterns  

## Emergency Contacts

- Platform team on-call: ___
- GKE support case (if needed): ___
- ML workload SMEs: ___

This plan balances upgrade speed with production stability, using GKE's autoscaled blue-green strategy to maintain inference availability while protecting long-running training workloads.