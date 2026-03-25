# GKE ML Platform Upgrade Plan: 1.31 → 1.32

## Executive Summary

This plan addresses your 300-GPU cluster upgrade with specific strategies for inference latency protection and fine-tuning job continuity. The key insight: **GPU VMs don't support live migration** — every upgrade causes pod restarts and inference latency spikes. We'll use **autoscaled blue-green** for inference pools and **coordinated scheduling** for fine-tuning jobs.

## Cluster Configuration Analysis

**Current State:**
- **Cluster:** Standard GKE 1.31
- **GPU Pools:** L4 (200 nodes, inference), A100 (100 nodes, inference + fine-tuning)
- **Workloads:** Auto-scaling inference + 4-8h fine-tuning jobs
- **Critical Requirement:** Minimize inference latency impact

**Target:** GKE 1.32 (available in all release channels)

## Upgrade Strategy: Autoscaled Blue-Green

**Why autoscaled blue-green for GPU inference:**
- **Problem with surge:** GPU surge upgrades drain nodes before creating replacements → inference latency spikes and capacity gaps
- **Solution:** Autoscaled blue-green cordons old pools and auto-scales replacement nodes → keeps old pool serving while new pool warms up
- **GPU advantage:** Avoids the "musical chairs" problem where inference pods bounce between draining nodes

## Pre-Upgrade Setup

### 1. GPU Driver Compatibility Check
```bash
# Create staging pool with target version to test driver compatibility
gcloud container node-pools create l4-staging \
  --cluster ML_CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32 \
  --machine-type g2-standard-24 \
  --accelerator type=nvidia-l4,count=2 \
  --num-nodes 2 \
  --node-locations ZONE

# Deploy representative inference workload and validate
kubectl apply -f inference-validation.yaml
# Test model loading, CUDA calls, throughput vs baseline
```

### 2. Fine-Tuning Job Coordination
```bash
# Check current running jobs
kubectl get pods -l workload-type=fine-tuning -o wide

# Estimate completion times
kubectl logs POD_NAME | grep "ETA\|remaining\|progress"
```

### 3. Maintenance Window Configuration
```bash
# Configure weekend maintenance window
gcloud container clusters update ML_CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-13T02:00:00Z" \
  --maintenance-window-duration 8h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Upgrade Execution Plan

### Phase 1: Control Plane (Saturday 2 AM, ~15 minutes)

```bash
# Control plane upgrade
gcloud container clusters upgrade ML_CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32

# Validation
gcloud container clusters describe ML_CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Phase 2: L4 Inference Pool (Saturday 2:30 AM, ~45 minutes)

**Why L4 first:** Lower-tier inference, validates upgrade strategy before A100 pool.

```bash
# Enable autoscaling and configure autoscaled blue-green
gcloud container node-pools update l4-inference \
  --cluster ML_CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 50 \
  --total-max-nodes 250 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Trigger upgrade
gcloud container node-pools upgrade l4-inference \
  --cluster ML_CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

**What happens:**
1. Green pool creates 25% capacity (50 nodes) with 1.32
2. Blue pool (200 nodes) cordoned but continues serving
3. New inference requests → green pool, existing sessions → blue pool
4. Blue pool auto-scales down as green pool serves traffic
5. Gradual transition minimizes latency spikes

**Monitor during upgrade:**
```bash
# Watch pool transition
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=l4-inference -o wide'

# Monitor inference latency
kubectl top pods -l app=inference --sort-by cpu
```

### Phase 3: A100 Pool with Fine-Tuning Protection (Saturday 4 AM, ~90 minutes)

**Fine-tuning job strategy:** Schedule during low-traffic period, pause new job submissions.

```bash
# Pause new fine-tuning job submissions (via job scheduler)
kubectl scale deployment fine-tuning-scheduler --replicas=0

# Wait for current jobs to complete or checkpoint
# Check job progress every 30 minutes

# Configure A100 pool for autoscaled blue-green
gcloud container node-pools update a100-pool \
  --cluster ML_CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 25 \
  --total-max-nodes 125 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.30,blue-green-full-batch-timeout=7200s

# Trigger upgrade
gcloud container node-pools upgrade a100-pool \
  --cluster ML_CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

**A100-specific considerations:**
- **Higher initial percentage (30%):** A100s handle both inference + training → need more capacity
- **Longer timeout (2h):** A100 nodes take longer to initialize
- **Training job checkpointing:** Ensure jobs save state before upgrade window

## Monitoring & Validation

### Real-time Health Checks

```bash
# Inference endpoint health
curl -H "Content-Type: application/json" \
  -d '{"model":"llama2","prompt":"test"}' \
  https://inference.example.com/v1/completions

# GPU utilization during transition
kubectl top nodes -l accelerator=nvidia-l4
kubectl top nodes -l accelerator=nvidia-a100

# No stuck pods
kubectl get pods -A | grep -E "Terminating|Pending|Error"
```

### Post-Upgrade Validation

```bash
# All nodes at 1.32
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion

# GPU driver version
kubectl describe nodes -l accelerator=nvidia-l4 | grep "nvidia.com/gpu"

# Inference latency baseline (compare to pre-upgrade)
# Run load test and compare p95 latency

# Resume fine-tuning jobs
kubectl scale deployment fine-tuning-scheduler --replicas=3
```

## Rollback Plan

If critical issues arise during upgrade:

### L4 Pool Rollback
```bash
# Cancel ongoing upgrade (completes current node batch)
gcloud container operations list --cluster ML_CLUSTER_NAME --zone ZONE

# Traffic will remain on blue pool (old version)
# Green pool can be deleted if needed
```

### A100 Pool Emergency Rollback
```bash
# Create emergency pool at 1.31
gcloud container node-pools create a100-emergency \
  --cluster ML_CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31 \
  --machine-type a2-highgpu-1g \
  --accelerator type=nvidia-tesla-a100,count=1 \
  --num-nodes 50

# Migrate critical workloads manually
kubectl cordon -l cloud.google.com/gke-nodepool=a100-pool
```

## Timeline & Resource Requirements

| Phase | Duration | Resource Impact | Risk Level |
|-------|----------|----------------|------------|
| Control Plane | 15 min | API brief unavailability | Low |
| L4 Pool | 45 min | 25% initial surge capacity | Medium |
| A100 Pool | 90 min | 30% initial surge capacity | Medium-High |
| **Total** | **2.5 hours** | **Peak: +55 GPU nodes** | |

## Cost Optimization

**Autoscaled blue-green cost advantage:**
- Traditional blue-green: 2x node cost during upgrade (600 total GPUs)
- Autoscaled blue-green: ~1.3x peak cost (390 total GPUs)
- **Estimated savings:** 35% reduction in upgrade cost spike

## Risk Mitigation Checklist

```
Pre-Upgrade
- [ ] GPU driver compatibility validated in staging pool
- [ ] Fine-tuning jobs checkpointed or scheduled completion
- [ ] Inference load balancer health checks configured
- [ ] Capacity reservations confirmed for surge nodes
- [ ] Rollback plan tested and documented

During Upgrade
- [ ] Monitor inference latency in real-time
- [ ] Track blue-green pool scaling behavior
- [ ] Verify GPU utilization remains stable
- [ ] Check for stuck pods every 15 minutes

Post-Upgrade
- [ ] GPU workloads validated on new driver version
- [ ] Fine-tuning scheduler re-enabled
- [ ] Inference latency within 5% of baseline
- [ ] Remove staging node pool to reduce costs
```

## Key Commands Reference

```bash
# Monitor upgrade progress
watch 'gcloud container operations list --cluster ML_CLUSTER_NAME --zone ZONE --limit 3'

# GPU-specific validation
kubectl describe nodes | grep -A 5 "nvidia.com/gpu"
kubectl get pods -l accelerator-type=gpu -o wide

# Emergency fine-tuning job pause
kubectl scale deployment fine-tuning-scheduler --replicas=0

# Post-upgrade cleanup
gcloud container node-pools delete l4-staging --cluster ML_CLUSTER_NAME --zone ZONE
```

**Next Steps:** Schedule the upgrade during your next low-traffic weekend window. The autoscaled blue-green approach will minimize inference disruption while protecting your fine-tuning investments.