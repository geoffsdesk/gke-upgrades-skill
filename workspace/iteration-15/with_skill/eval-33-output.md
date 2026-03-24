# GKE GPU Cluster Upgrade Plan: 1.31 → 1.32

## Cluster Overview
- **Mode**: Standard
- **GPU Pools**: 200x L4 (inference) + 100x A100 (inference + fine-tuning)
- **Current**: 1.31 → **Target**: 1.32
- **Workloads**: Auto-scaled inference + 4-8hr fine-tuning jobs

## Upgrade Strategy Summary

**Recommended approach**: Sequential node pool upgrades with **autoscaled blue-green** for both pools to minimize inference disruption while protecting long-running fine-tuning jobs.

### Why Autoscaled Blue-Green for GPU Pools

1. **L4 Inference Pool**: Maintains serving capacity throughout upgrade - green pool scales up as traffic demands while blue pool scales down as workloads drain
2. **A100 Mixed Pool**: Protects 4-8hr fine-tuning jobs from forced eviction (surge would force-evict after 1 hour) while maintaining inference availability
3. **Cost Efficiency**: Unlike standard blue-green (2x cost), autoscaled blue-green scales down the old pool as new nodes come online
4. **GPU Capacity**: Avoids surge capacity requirements (L4/A100 reservations typically have no headroom for surge nodes)

## Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist - ML Platform GPU Cluster
- [ ] Cluster: _YOUR_CLUSTER_NAME_ | Mode: Standard | Channel: ___
- [ ] Current version: 1.31 | Target version: 1.32

Compatibility & GPU-Specific
- [ ] 1.32 available in release channel (`gcloud container get-server-config --zone ZONE`)
- [ ] GPU driver compatibility confirmed (1.32 may change CUDA version - test in staging)
- [ ] ML framework compatibility (TensorFlow/PyTorch) with new CUDA version
- [ ] No deprecated API usage (`kubectl get --raw /metrics | grep deprecated`)
- [ ] L4 and A100 reservation headroom verified (check if any capacity available for temporary nodes)

Workload Readiness  
- [ ] PDBs configured for inference workloads (allow some disruption but prevent mass eviction)
- [ ] No bare pods - all managed by Deployments/Jobs
- [ ] Fine-tuning jobs have checkpointing enabled (4-8hr jobs must resume, not restart)
- [ ] Inference workload resource requests/limits properly set
- [ ] Auto-scaler configuration reviewed (cluster-autoscaler and HPA settings)

Infrastructure
- [ ] A100 fine-tuning schedule mapped (plan upgrade during gaps between long jobs)
- [ ] Maintenance window: Off-peak inference hours identified
- [ ] Monitoring baseline captured (inference latency p99, throughput, GPU utilization)
```

## Upgrade Plan

### Phase 1: Control Plane Upgrade
```bash
# Upgrade control plane first (required before nodes)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32

# Monitor (~10-15 min, regional clusters stay available)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Phase 2: L4 Inference Pool (Lower Risk First)

**Strategy**: Autoscaled blue-green with conservative settings to maintain inference availability.

```bash
# Configure autoscaled blue-green for L4 pool
gcloud container node-pools update l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 10 \
  --total-max-nodes 250 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.2,blue-green-full-batch-timeout=3600s

# Start upgrade
gcloud container node-pools upgrade l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

**What happens**: 
- Green pool starts with 20% of nodes (~40 L4 nodes)
- Auto-scaler creates more green nodes as inference traffic routes to them
- Blue pool scales down as workloads drain
- 1-hour timeout prevents stuck upgrades

**Monitor L4 upgrade**:
```bash
# Track node versions and auto-scaling
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=l4-inference-pool -o wide'

# Monitor inference latency during transition
# (your monitoring dashboard/kubectl top pods)
```

### Phase 3: A100 Mixed Pool (After L4 Completes + Fine-tuning Gap)

**Critical timing**: Start only during a gap between fine-tuning jobs.

```bash
# First: Verify no active fine-tuning jobs
kubectl get jobs -l workload-type=fine-tuning -A
kubectl get pods -l workload-type=fine-tuning -A | grep Running

# Configure autoscaled blue-green for A100 pool  
gcloud container node-pools update a100-mixed-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 5 \
  --total-max-nodes 120 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=7200s

# Start A100 upgrade (2hr timeout for any stuck fine-tuning jobs)
gcloud container node-pools upgrade a100-mixed-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

**A100 considerations**:
- Extended timeout (7200s = 2hr) respects longer fine-tuning jobs
- 25% initial green capacity maintains inference while allowing fine-tuning migration
- If a fine-tuning job is mid-execution, it will checkpoint and resume on green nodes

## Alternative Strategy: Maintenance Exclusions + Manual Timing

If you prefer maximum control over timing:

```bash
# Block auto-upgrades during active fine-tuning campaigns
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "fine-tuning-campaign" \
  --add-maintenance-exclusion-start-time 2024-01-15T00:00:00Z \
  --add-maintenance-exclusion-end-time 2024-01-30T23:59:59Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Manually trigger upgrades during planned gaps
# (Use the same autoscaled blue-green commands above)
```

## Monitoring During Upgrade

```bash
# GPU node status by pool
kubectl get nodes -l node.kubernetes.io/instance-type -o custom-columns=NAME:.metadata.name,POOL:.metadata.labels.cloud\.google\.com/gke-nodepool,VERSION:.status.nodeInfo.kubeletVersion,GPU:.metadata.labels.cloud\.google\.com/gke-accelerator

# Inference workload health
kubectl get pods -l workload-type=inference -A | grep -v Running

# Fine-tuning job status
kubectl get jobs -l workload-type=fine-tuning -A

# Check for GPU driver issues post-upgrade
kubectl get events -A --field-selector reason=FailedMount | grep nvidia
```

## Post-Upgrade Validation

```markdown
Post-Upgrade Checklist - ML Platform
- [ ] All nodes at 1.32: `kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion`
- [ ] GPU drivers loaded: `kubectl get pods -n kube-system -l name=nvidia-gpu-device-plugin`
- [ ] Inference workloads serving traffic (check your load balancer/ingress)
- [ ] Auto-scaler functioning: Deploy test workload and verify scale-up
- [ ] Fine-tuning job test: Launch short test job on A100 pool
- [ ] ML framework compatibility: Run inference + training smoke tests
- [ ] Inference latency within baseline (p99 < pre-upgrade + 10%)
- [ ] GPU utilization metrics flowing to monitoring
```

## Rollback Strategy

If inference latency degrades or GPU compatibility issues emerge:

```bash
# Cannot downgrade nodes in-place - create new pool at 1.31
gcloud container node-pools create l4-rollback-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x \
  --machine-type g2-standard-24 \
  --accelerator type=nvidia-l4,count=1 \
  --num-nodes 50

# Cordon upgraded pool, migrate workloads
kubectl cordon -l cloud.google.com/gke-nodepool=l4-inference-pool
```

## Key Recommendations

1. **Upgrade during low-traffic inference periods** (minimize blue-green capacity requirements)
2. **Complete L4 pool first** (lower risk, validate GPU driver compatibility)
3. **Wait for fine-tuning job gaps before A100 upgrade** (4-8hr jobs can't be interrupted)
4. **Test in staging first** - verify CUDA version changes don't break your ML pipelines
5. **Monitor inference latency closely** during the transition - auto-scaled blue-green maintains capacity but pod startup time affects initial requests

**Estimated timeline**: 4-6 hours total (2hr L4 pool + 2-4hr A100 pool, depending on workload migration speed and fine-tuning job timing).