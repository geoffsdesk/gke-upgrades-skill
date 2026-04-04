# GKE GPU Inference Cluster Upgrade Plan: 1.31 → 1.32

## Overview
**Cluster:** ML Platform Inference
- **Mode:** Standard
- **Current:** 1.31 → **Target:** 1.32 (single minor version jump)
- **GPU Pools:** L4 (200 nodes, inference), A100 (100 nodes, inference + 4-8h fine-tuning)
- **Priority:** Minimize inference latency impact and protect long-running fine-tuning jobs

## Recommended Strategy: Autoscaled Blue-Green for GPU Pools

For GPU inference workloads, **autoscaled blue-green** is the optimal strategy because:
- **Zero inference downtime:** Old pool continues serving while new pool warms up
- **No forced pod restarts:** GPU VMs don't support live migration, so surge upgrades cause inference latency spikes
- **Cost-efficient:** Scales down blue pool as green pool scales up (avoids 2x resource cost of standard blue-green)
- **Respects long jobs:** Fine-tuning jobs get extended graceful termination (no 1-hour force eviction)

## Upgrade Sequence

### Phase 1: Control Plane Upgrade
```bash
# Verify target version availability
gcloud container get-server-config --zone YOUR_ZONE --format="yaml(channels)"

# Upgrade control plane (10-15 minutes, no workload impact)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone YOUR_ZONE \
  --master \
  --cluster-version 1.32.0-gke.LATEST
```

### Phase 2: L4 Inference Pool (Lower Risk First)
Configure autoscaled blue-green for the L4 pool:
```bash
# Enable autoscaling if not already configured
gcloud container node-pools update l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone YOUR_ZONE \
  --enable-autoscaling \
  --total-min-nodes 50 \
  --total-max-nodes 250

# Configure autoscaled blue-green upgrade
gcloud container node-pools update l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone YOUR_ZONE \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Execute upgrade
gcloud container node-pools upgrade l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone YOUR_ZONE \
  --cluster-version 1.32.0-gke.LATEST
```

**Expected behavior:** 25% of L4 nodes created in green pool initially, autoscaler provisions more as inference traffic routes to new nodes, blue pool scales down as pods drain.

### Phase 3: A100 Mixed Workload Pool
**Critical timing consideration:** Schedule during low fine-tuning activity or coordinate with ML teams to pause new fine-tuning jobs.

```bash
# Configure autoscaled blue-green for A100 pool
gcloud container node-pools update a100-mixed-pool \
  --cluster CLUSTER_NAME \
  --zone YOUR_ZONE \
  --enable-autoscaling \
  --total-min-nodes 20 \
  --total-max-nodes 120 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.20,blue-green-full-batch-timeout=7200s

# Execute upgrade (coordinate with ML teams)
gcloud container node-pools upgrade a100-mixed-pool \
  --cluster CLUSTER_NAME \
  --zone YOUR_ZONE \
  --cluster-version 1.32.0-gke.LATEST
```

**Fine-tuning job protection:**
- Autoscaled blue-green respects `terminationGracePeriodSeconds` > 1 hour (unlike surge)
- Set extended grace period on fine-tuning pods: `terminationGracePeriodSeconds: 3600` (1 hour)
- Add `cluster-autoscaler.kubernetes.io/safe-to-evict: "false"` annotation to fine-tuning pods

## Pre-Flight Checklist

```
GPU-Specific Pre-Upgrade Checklist
- [ ] GPU driver compatibility confirmed (1.31 → 1.32 typically maintains CUDA compatibility)
- [ ] Inference models tested against GKE 1.32 + target GPU driver in staging
- [ ] GPU reservation capacity verified (A100/L4 quotas checked)
- [ ] Fine-tuning job checkpointing enabled and tested
- [ ] ML teams notified of maintenance window
- [ ] Cluster autoscaler configured for both pools
- [ ] PDBs configured for inference services (minAvailable: 50% recommended)
- [ ] Monitoring baseline captured (inference latency p99, throughput, GPU utilization)
```

## GPU Driver Version Validation (Critical)

**Before production upgrade:**
```bash
# Create staging node pool with target version
gcloud container node-pools create staging-l4 \
  --cluster CLUSTER_NAME \
  --zone YOUR_ZONE \
  --machine-type g2-standard-24 \
  --accelerator type=nvidia-l4,count=2 \
  --num-nodes 2 \
  --node-version 1.32.0-gke.LATEST

# Deploy representative inference workload
kubectl apply -f staging-inference-deployment.yaml

# Validate model loading, CUDA calls, inference latency
# Check GPU driver version: kubectl get nodes -o yaml | grep nvidia
```

**Never skip staging validation for GPU workloads** — GKE auto-installs GPU drivers matching the target version, which may change CUDA versions.

## Monitoring During Upgrade

```bash
# GPU node status
watch 'kubectl get nodes -l cloud.google.com/gke-accelerator -o wide'

# Inference pod health
kubectl get pods -l workload-type=inference -A

# Fine-tuning job status
kubectl get pods -l workload-type=fine-tuning -A

# GPU utilization
kubectl top nodes --selector=cloud.google.com/gke-accelerator

# Autoscaler events
kubectl get events -A --field-selector involvedObject.kind=Node --sort-by='.lastTimestamp'
```

## Expected Timeline

- **Control plane:** 10-15 minutes
- **L4 pool (200 nodes):** 2-4 hours (depends on inference traffic patterns)
- **A100 pool (100 nodes):** 1-3 hours (+ coordination time for fine-tuning jobs)
- **Total maintenance window:** 4-8 hours

## Rollback Plan

If issues arise during autoscaled blue-green:

```bash
# Cancel ongoing upgrade
gcloud container operations cancel OPERATION_ID --zone YOUR_ZONE

# Scale up blue pool manually to restore capacity
kubectl uncordon -l cloud.google.com/gke-nodepool=POOL_NAME

# Route traffic back to blue pool (application-specific)
# Rollback any inference service configurations if needed
```

## Post-Upgrade Validation

```
GPU Cluster Post-Upgrade Checklist
- [ ] All GPU nodes at 1.32: kubectl get nodes -l cloud.google.com/gke-accelerator -o wide
- [ ] GPU driver version confirmed: kubectl describe nodes | grep nvidia
- [ ] Inference endpoints responding with normal latency
- [ ] GPU utilization metrics flowing to monitoring
- [ ] Fine-tuning job queue operational
- [ ] Cluster autoscaler scaling behavior normal
- [ ] No GPU memory leaks or driver crashes in logs
```

## Key Advantages of This Approach

1. **Zero inference downtime:** Blue-green keeps old nodes serving during transition
2. **Long job protection:** Fine-tuning jobs get graceful eviction, not 1-hour force termination
3. **Cost optimization:** Autoscaled blue-green avoids 2x resource cost spike
4. **Risk mitigation:** L4 pool upgraded first (lower business impact than A100)
5. **Traffic-aware scaling:** Autoscaler provisions green pool capacity based on actual demand

## Alternative Strategy (If Surge Capacity Available)

If you have confirmed GPU surge quota available:
```bash
# L4 pool: conservative surge
gcloud container node-pools update l4-inference-pool \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# A100 pool: drain-first (no surge capacity assumed)
gcloud container node-pools update a100-mixed-pool \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2  # 2% of pool for faster upgrade
```

**However, autoscaled blue-green is still recommended** for inference workloads to eliminate pod restart latency spikes.