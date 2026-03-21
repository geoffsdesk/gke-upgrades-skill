# GKE Upgrade Plan: ML Inference Platform (1.31 → 1.32)

## Environment Summary
- **Cluster**: Standard mode with GPU workloads
- **Current**: 1.31 → **Target**: 1.32
- **Node pools**: L4 inference (200 nodes) + A100 mixed (100 nodes)
- **Workloads**: Auto-scaling inference + 4-8h fine-tuning jobs
- **Priority**: Minimize inference latency/availability impact

## Upgrade Strategy Overview

**Rolling strategy** with pool-specific approaches:
- **L4 inference pool**: Conservative surge to maintain serving capacity
- **A100 mixed pool**: Coordinated upgrade during fine-tuning gaps
- **Control plane first**: Standard minor upgrade path
- **Skip-level consideration**: Not applicable (single minor version jump)

## Node Pool Upgrade Strategies

### L4 Inference Pool (Priority: Zero serving disruption)
```bash
# Configure conservative surge settings
gcloud container node-pools update l4-inference-pool \
  --cluster ML_CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 0
```

**Rationale**: `maxSurge=5` adds 5 extra L4 nodes for gradual replacement while maintaining full serving capacity. Assumes L4 reservation has headroom—if not, reduce to `maxSurge=2` or use `maxUnavailable=1` mode.

### A100 Mixed Pool (Priority: Coordinate with training schedule)
```bash
# Wait for fine-tuning jobs to complete, then use faster upgrade
gcloud container node-pools update a100-mixed-pool \
  --cluster ML_CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 3
```

**Rationale**: `maxUnavailable=3` drains 3 A100 nodes at a time—no extra GPU quota needed but creates capacity dips. Only proceed when no active fine-tuning jobs. For A100 pools, `maxUnavailable` is the primary lever since surge capacity is typically unavailable.

## Pre-Upgrade Checklist

```markdown
### Compatibility & Versions
- [ ] Target 1.32 available in release channel: `gcloud container get-server-config --zone ZONE --format="yaml(channels)"`
- [ ] GKE 1.32 release notes reviewed for GPU/ML-specific changes
- [ ] GPU driver compatibility confirmed (1.32 may change CUDA version)
- [ ] ML framework compatibility tested (TensorFlow, PyTorch, JAX versions)
- [ ] Inference serving stack compatible (TensorRT, Triton, custom containers)

### GPU Workload Readiness
- [ ] L4 inference pools: PDBs configured to prevent > 10% simultaneous pod eviction
- [ ] A100 fine-tuning: Current jobs will complete within upgrade window
- [ ] No bare GPU pods—all managed by Deployments/StatefulSets
- [ ] GPU reservations have headroom for L4 surge nodes (5 extra) OR switch to maxUnavailable mode
- [ ] terminationGracePeriodSeconds adequate for model unloading (recommend 60s+)

### Auto-scaling Configuration  
- [ ] HPA/VPA behavior tested with node churn
- [ ] Cluster autoscaler max node limits accommodate surge
- [ ] Node auto-provisioning (NAP) compatible with 1.32 if enabled
- [ ] Resource requests/limits properly set for GPU scheduling

### Monitoring & Baselines
- [ ] Inference latency baselines captured (p50/p95/p99)
- [ ] Error rate baselines established
- [ ] GPU utilization metrics active
- [ ] Queue depth/request backlog monitoring ready
```

## Maintenance Configuration

```bash
# Set maintenance window during low-traffic period
gcloud container clusters update ML_CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-12-15T02:00:00Z" \
  --maintenance-window-end "2024-12-15T08:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"

# Optional: Block future auto-upgrades during training campaigns
gcloud container clusters update ML_CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-season" \
  --add-maintenance-exclusion-start-time "2024-12-20T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-01-15T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

## Upgrade Runbook

### Phase 1: Control Plane Upgrade
```bash
# Verify pre-flight
gcloud container clusters describe ML_CLUSTER_NAME \
  --zone ZONE \
  --format="table(currentMasterVersion, nodePools[].name, nodePools[].version)"

kubectl get nodes | grep -E "Ready|NotReady"

# Upgrade control plane (10-15 min)
gcloud container clusters upgrade ML_CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version "1.32.0-gke.XXXXX"

# Validate control plane
kubectl get pods -n kube-system | grep -v Running
gcloud container clusters describe ML_CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Phase 2: L4 Inference Pool (Maintain serving capacity)
```bash
# Configure surge for gradual replacement
gcloud container node-pools update l4-inference-pool \
  --cluster ML_CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 0

# Start upgrade
gcloud container node-pools upgrade l4-inference-pool \
  --cluster ML_CLUSTER_NAME \
  --zone ZONE \
  --cluster-version "1.32.0-gke.XXXXX"

# Monitor inference traffic during upgrade
watch 'kubectl get pods -l workload=inference -o wide | grep -E "Running|Pending"'
```

### Phase 3: A100 Mixed Pool (During training gap)
```bash
# Verify no active fine-tuning jobs
kubectl get pods -l workload=training -o wide
# Wait for completion or coordinate with ML engineers

# Upgrade A100 pool with unavailable strategy
gcloud container node-pools update a100-mixed-pool \
  --cluster ML_CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 3

gcloud container node-pools upgrade a100-mixed-pool \
  --cluster ML_CLUSTER_NAME \
  --zone ZONE \
  --cluster-version "1.32.0-gke.XXXXX"

# Monitor node replacement
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=a100-mixed-pool -o wide'
```

## Post-Upgrade Validation

```bash
# Cluster health
kubectl get nodes | grep -v Ready
kubectl get pods -A | grep -v Running | grep -v Completed

# GPU scheduling validation
kubectl describe nodes | grep -A 5 "nvidia.com/gpu"

# Inference workload health
kubectl get deployments -l workload=inference
curl -s INFERENCE_ENDPOINT/health

# Performance regression check
# Compare current latency to pre-upgrade baseline
# Monitor error rates for 24h post-upgrade
```

## GPU-Specific Considerations

### Driver Version Changes
GKE 1.32 may auto-install updated GPU drivers:
- **Test impact**: Deploy 1.32 in staging first to verify CUDA compatibility
- **Framework compatibility**: Ensure TensorFlow/PyTorch support new driver/CUDA versions
- **Custom CUDA code**: Recompile if using custom kernels

### Inference Serving Protection
```yaml
# Recommended PDB for inference workloads
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: inference-pdb
spec:
  minAvailable: 90%  # Allow max 10% simultaneous disruption
  selector:
    matchLabels:
      workload: inference
```

### Fine-Tuning Job Coordination
- **Checkpoint before upgrade**: Ensure training jobs save state
- **Queue management**: Pause new job submissions during A100 pool upgrade
- **Resume strategy**: Restart interrupted jobs from latest checkpoint

## Rollback Plan

If inference latency degrades significantly:

```bash
# Create rollback node pool at 1.31
gcloud container node-pools create l4-inference-rollback \
  --cluster ML_CLUSTER_NAME \
  --zone ZONE \
  --cluster-version "1.31.X-gke.XXXXX" \
  --machine-type g2-standard-48 \
  --accelerator type=nvidia-l4,count=4 \
  --num-nodes 200

# Cordon upgraded pool and migrate traffic
kubectl cordon -l cloud.google.com/gke-nodepool=l4-inference-pool
# Wait for natural pod rescheduling to rollback pool
```

## Timeline Estimate
- **Control plane**: 15 minutes
- **L4 pool** (200 nodes, surge=5): ~8-10 hours 
- **A100 pool** (100 nodes, unavailable=3): ~6-8 hours
- **Total window**: 12-16 hours (pools can overlap if capacity permits)

## Risk Mitigation
1. **Inference SLA protection**: Surge strategy maintains serving capacity
2. **Training job coordination**: Upgrade A100 pool only during gaps
3. **Gradual rollout**: Start with smaller batch if concerned (reduce maxSurge/maxUnavailable)
4. **Monitoring**: Alert on latency p95 >10% increase from baseline
5. **Quick rollback**: New node pool creation takes ~10 minutes for fast recovery