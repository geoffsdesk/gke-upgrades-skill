# GKE GPU Cluster Upgrade Plan: ML Platform (1.31 → 1.32)

## Cluster Profile
- **Cluster**: GKE Standard
- **Current**: 1.31 → **Target**: 1.32
- **GPU Pools**: 200 L4 (inference) + 100 A100 (inference + fine-tuning)
- **Workload Mix**: Latency-sensitive inference + 4-8h fine-tuning jobs
- **Auto-scaling**: Traffic-based

## Recommended Upgrade Strategy

### For L4 Pool (Inference Only) — Autoscaled Blue-Green
The L4 pool should use **autoscaled blue-green upgrade** for minimal inference disruption:
- Zero capacity loss during transition
- Gradual traffic shift from blue to green nodes
- Fast rollback if inference quality degrades

### For A100 Pool (Mixed Workload) — Controlled Rolling with Job Protection
The A100 pool needs **surge upgrade with job awareness**:
- Coordinate with fine-tuning job scheduler
- Use maintenance exclusions during active training campaigns
- Rolling replacement to maintain inference capacity

## Pre-Upgrade Checklist

```
GPU ML Platform Upgrade Checklist
- [ ] Cluster: ML_PLATFORM | Mode: Standard | Channel: ___
- [ ] Current version: 1.31 | Target version: 1.32

GPU-Specific Compatibility
- [ ] GPU driver compatibility verified (1.32 may change CUDA version)
- [ ] Inference framework compatibility tested (TensorRT, PyTorch, etc.)
- [ ] Fine-tuning framework compatibility verified
- [ ] GPU reservation headroom checked for surge capacity (if any)
- [ ] Model serving health checks configured with appropriate timeouts

Workload Assessment
- [ ] Current fine-tuning job schedule reviewed (identify upgrade windows)
- [ ] Inference traffic patterns analyzed (low-traffic windows identified)
- [ ] Model loading times measured (for capacity planning)
- [ ] PDBs configured for inference deployments (not overly restrictive)
- [ ] Auto-scaler metrics and thresholds documented

Infrastructure
- [ ] L4 pool: Autoscaled blue-green strategy configured
- [ ] A100 pool: Surge settings optimized for mixed workload
- [ ] Maintenance exclusion ready for active training periods
- [ ] Monitoring active (GPU utilization, inference latency, job completion rates)
```

## Detailed Upgrade Runbook

### Phase 1: Control Plane Upgrade

```bash
# Verify current state
gcloud container clusters describe ML_PLATFORM \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check GPU driver compatibility
kubectl get nodes -o wide -l accelerator=nvidia-l4
kubectl get nodes -o wide -l accelerator=nvidia-tesla-a100

# Upgrade control plane (10-15 minutes)
gcloud container clusters upgrade ML_PLATFORM \
  --zone ZONE \
  --master \
  --cluster-version 1.32

# Verify control plane
kubectl get pods -n kube-system | grep -E "gke-metadata|nvidia"
```

### Phase 2: L4 Pool (Inference) — Autoscaled Blue-Green

```bash
# Configure autoscaled blue-green for L4 pool
gcloud container node-pools update l4-inference-pool \
  --cluster ML_PLATFORM \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 10 --total-max-nodes 250 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Initiate upgrade (this will take 1-2 hours depending on traffic)
gcloud container node-pools upgrade l4-inference-pool \
  --cluster ML_PLATFORM \
  --zone ZONE \
  --cluster-version 1.32

# Monitor traffic shift and GPU utilization
kubectl get nodes -l accelerator=nvidia-l4 -o wide
watch 'kubectl get pods -l app=inference -o wide | grep l4'
```

**Key advantage**: Green pool scales up based on actual inference demand while blue pool scales down as traffic shifts. No 2x resource cost or capacity loss.

### Phase 3: A100 Pool (Mixed Workload) — Job-Aware Rolling

```bash
# First, check for running fine-tuning jobs
kubectl get pods -l workload-type=fine-tuning -o wide

# If jobs are running, apply maintenance exclusion
gcloud container clusters update ML_PLATFORM \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+8 hours' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Configure conservative surge settings for A100 pool
# GPU pools typically have no surge capacity, so maxUnavailable is the primary lever
gcloud container node-pools update a100-mixed-pool \
  --cluster ML_PLATFORM \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2

# Upgrade during low fine-tuning activity window
gcloud container node-pools upgrade a100-mixed-pool \
  --cluster ML_PLATFORM \
  --zone ZONE \
  --cluster-version 1.32

# Monitor both inference and training workloads
watch 'kubectl get pods -l accelerator=nvidia-tesla-a100 -o wide'
```

### Phase 4: Validation

```bash
# Verify all nodes upgraded
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,ACCELERATOR:.metadata.labels.accelerator

# Check GPU drivers
kubectl describe nodes -l accelerator=nvidia-l4 | grep "nvidia.com/gpu"
kubectl describe nodes -l accelerator=nvidia-tesla-a100 | grep "nvidia.com/gpu"

# Validate inference workloads
kubectl get pods -l app=inference | grep -v Running
kubectl get hpa -l workload-type=inference

# Check fine-tuning job health
kubectl get pods -l workload-type=fine-tuning -o wide

# Test inference endpoints
# Run your standard inference smoke tests here
```

## Key Considerations for GPU Inference

### 1. Model Loading Time Impact
- **L4 pool**: Autoscaled blue-green minimizes cold starts by gradually shifting traffic
- **A100 pool**: 2-node `maxUnavailable` allows staggered model reloading
- Monitor model loading metrics during upgrade

### 2. CUDA Version Changes
GKE 1.32 may update GPU drivers and CUDA versions:
```bash
# Check CUDA version post-upgrade
kubectl exec -it $(kubectl get pods -l app=inference -o jsonpath='{.items[0].metadata.name}') -- nvidia-smi
```

### 3. Auto-scaler Interaction
- Auto-scaler may compete with upgrade for node lifecycle
- Consider temporarily reducing scale-down aggressiveness:
```bash
kubectl annotate deployment.apps/cluster-autoscaler \
  cluster-autoscaler.kubernetes.io/scale-down-delay-after-add=15m \
  -n kube-system
```

### 4. Fine-Tuning Job Protection
For 4-8 hour jobs, standard surge upgrade timeout (1 hour) will force-evict:
```bash
# Increase terminationGracePeriodSeconds for fine-tuning pods
# Add to your fine-tuning job spec:
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 28800  # 8 hours
```

## Timing Recommendations

1. **Start upgrade**: During your lowest inference traffic period (typically late night/early morning)
2. **L4 pool first**: Less disruptive, validates GPU driver compatibility
3. **A100 pool window**: Schedule between fine-tuning job batches
4. **Total duration**: 3-4 hours for both pools

## Rollback Plan

If inference quality degrades post-upgrade:

### L4 Pool Rollback (Autoscaled Blue-Green)
```bash
# Fast rollback - uncordon blue pool
kubectl uncordon -l cloud.google.com/gke-nodepool=l4-inference-pool
# Traffic will naturally shift back as green pool scales down
```

### A100 Pool Rollback (Create New Pool)
```bash
# Create new pool at 1.31
gcloud container node-pools create a100-rollback \
  --cluster ML_PLATFORM \
  --zone ZONE \
  --cluster-version 1.31 \
  --accelerator type=nvidia-tesla-a100,count=1 \
  --num-nodes 100

# Migrate workloads, then delete upgraded pool
```

## Success Metrics

- [ ] Inference latency p99 within 5% of baseline
- [ ] No inference request failures during upgrade
- [ ] Fine-tuning job completion rate maintained
- [ ] GPU utilization patterns restored post-upgrade
- [ ] All model serving endpoints healthy

This strategy minimizes inference disruption through autoscaled blue-green on L4 while protecting long-running fine-tuning jobs on A100. The staggered approach validates GPU compatibility before upgrading your most critical mixed workload pool.