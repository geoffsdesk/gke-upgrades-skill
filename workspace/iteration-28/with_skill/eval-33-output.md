# GKE ML Platform Upgrade Plan: 1.31 → 1.32

**Cluster:** ML Platform | **Mode:** Standard | **Current:** 1.31 | **Target:** 1.32
**GPU Pools:** 200x L4 (inference) + 100x A100 (inference + fine-tuning)

## Executive Summary

For GPU inference workloads, **autoscaled blue-green upgrade strategy** is recommended to minimize inference latency spikes. Standard surge upgrades cause pod restarts and inference downtime since GPU VMs don't support live migration. Blue-green keeps old nodes serving while new nodes warm up.

## Pre-Upgrade Assessment

### GPU-Specific Constraints
- **No live migration:** Every GPU node upgrade requires pod restart
- **Driver version coupling:** GKE will auto-install GPU drivers matching 1.32 - verify CUDA compatibility
- **Reservation capacity:** Check if your GPU reservations have headroom for blue-green (requires 2x capacity temporarily)

### Fine-tuning Job Protection
4-8 hour fine-tuning jobs exceed GKE's 1-hour surge eviction timeout and need special handling.

## Recommended Upgrade Strategy

### Phase 1: Control Plane (Minimal Impact)
```bash
# Regional clusters maintain availability during CP upgrade
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest
```

### Phase 2: L4 Inference Pool (Autoscaled Blue-Green)
```bash
# Configure autoscaled blue-green for L4 pool
gcloud container node-pools update l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 50 --total-max-nodes 250 \
  --strategy=AUTOSCALED_BLUE_GREEN \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Trigger upgrade
gcloud container node-pools upgrade l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Why autoscaled blue-green for L4:**
- Avoids inference latency spikes from pod restarts
- Green pool scales up based on demand while blue pool continues serving
- Cost-efficient: scales down blue pool as traffic moves to green
- Respects autoscaler behavior during upgrade

### Phase 3: A100 Mixed Pool (Coordinated Approach)

**Option A: Wait for Fine-tuning Gap (Recommended)**
```bash
# 1. Pause new fine-tuning job submissions
# 2. Wait for current 4-8h jobs to complete naturally
# 3. Use autoscaled blue-green once pool is inference-only

gcloud container node-pools update a100-mixed-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 25 --total-max-nodes 125 \
  --strategy=AUTOSCALED_BLUE_GREEN \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.30,blue-green-full-batch-timeout=7200s
```

**Option B: Mixed Workload Protection (If Can't Wait)**
```bash
# Add maintenance exclusion to block auto-upgrades during training
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "fine-tuning-protection" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time $(date -u -d "+2 weeks" +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Manual upgrade when jobs complete
# (Remove exclusion first, then upgrade)
```

## Pre-Flight Checklist

```markdown
Pre-Upgrade Checklist - ML Platform
- [ ] Cluster: ML Platform | Mode: Standard | Channel: ___
- [ ] Current version: 1.31 | Target version: 1.32

GPU-Specific Readiness
- [ ] GPU driver compatibility verified for 1.32 (create test node pool first)
- [ ] CUDA version compatibility confirmed with inference models
- [ ] GPU reservation capacity checked for blue-green (2x temporary requirement)
- [ ] Inference endpoint health checks configured
- [ ] Model loading time benchmarked (expect ~2-5min warmup on new nodes)

Fine-tuning Job Protection
- [ ] Current fine-tuning jobs identified and runtime estimated
- [ ] Job submission pause process documented
- [ ] Checkpointing enabled on long-running training jobs
- [ ] PDBs configured for training workloads: `minAvailable: 1`

Infrastructure
- [ ] Autoscaler configuration reviewed (min/max nodes per pool)
- [ ] Inference traffic patterns understood (peak hours identified)
- [ ] Monitoring setup: GPU utilization, inference latency, queue depth
- [ ] Rollback plan documented (cordon new pool, uncordon old pool)
```

## Upgrade Commands

### L4 Pool Upgrade (Autoscaled Blue-Green)
```bash
# Enable autoscaling if not already configured
gcloud container node-pools update l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 50 \
  --total-max-nodes 250

# Configure blue-green strategy
gcloud container node-pools update l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Start upgrade
gcloud container node-pools upgrade l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest

# Monitor progress
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=l4-inference-pool -o wide'
```

### A100 Pool Upgrade (After Fine-tuning Jobs Complete)
```bash
# Configure for mixed workload
gcloud container node-pools update a100-mixed-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 25 \
  --total-max-nodes 125 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.30,blue-green-full-batch-timeout=7200s

# Upgrade
gcloud container node-pools upgrade a100-mixed-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

## Monitoring During Upgrade

### Key Metrics to Watch
```bash
# Inference latency and availability
kubectl get pods -l app=inference -o wide
curl -s http://your-inference-endpoint/health

# GPU utilization during transition
kubectl top nodes -l accelerator=nvidia-l4
kubectl top nodes -l accelerator=nvidia-tesla-a100

# Blue-green transition progress
kubectl get nodes -l cloud.google.com/gke-nodepool=l4-inference-pool \
  -o custom-columns=NAME:.metadata.name,STATUS:.status.conditions[-1].type,VERSION:.status.nodeInfo.kubeletVersion
```

### Expected Timeline
- **Control plane:** 10-15 minutes
- **L4 pool (200 nodes):** 2-4 hours with blue-green
- **A100 pool (100 nodes):** 1-2 hours with blue-green
- **Total:** 4-6 hours (can overlap L4/A100 if no fine-tuning jobs)

## Rollback Plan

If inference latency degrades post-upgrade:

```bash
# Blue-green allows fast rollback during soak period
# Uncordon blue pool, drain green pool
kubectl uncordon -l cloud.google.com/gke-nodepool=POOL_NAME,upgrade-phase=blue

# Or complete rollback by recreating old version pool
gcloud container node-pools create POOL_NAME-v131 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.latest \
  --machine-type g2-standard-24 \
  --accelerator type=nvidia-l4,count=2
```

## Post-Upgrade Validation

```bash
# Verify all GPU nodes upgraded
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,GPU:.metadata.labels.accelerator

# Test inference endpoints
curl -X POST http://your-inference-endpoint/predict -d '{"test": "data"}'

# Verify GPU driver version
kubectl get nodes -o jsonpath='{.items[*].status.nodeInfo.kernelVersion}'

# Check model loading times (should be similar to pre-upgrade)
kubectl logs -l app=inference | grep "Model loaded"
```

This strategy prioritizes inference availability while protecting long-running fine-tuning jobs. The autoscaled blue-green approach is specifically designed for GPU inference workloads where pod restart latency is unacceptable.