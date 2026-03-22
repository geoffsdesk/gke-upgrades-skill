# GKE Upgrade Plan: ML Inference Platform (1.31 → 1.32)

## Context
- **Cluster:** Standard mode, GPU-heavy workload
- **Current → Target:** 1.31 → 1.32 (single minor version jump)
- **Node pools:** L4 (inference) + A100 (inference + training)
- **Key requirement:** Minimize inference latency/availability impact

## Upgrade Strategy

### Control Plane
- **Timing:** Off-peak hours when inference traffic is lowest
- **Impact:** Brief API server restart (~2-3 minutes), no workload disruption
- **Schedule:** Weekend maintenance window preferred

### Node Pool Strategy: Rolling with Optimized Settings

Given your inference workload requirements and the 4-8 hour training jobs, I recommend **surge upgrades** with pool-specific settings:

#### L4 Pool (Inference Only)
```bash
# Optimize for availability - higher parallelism
gcloud container node-pools update l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 10 \
  --max-unavailable-upgrade 0
```
- **Rationale:** `maxSurge=10` increases parallelism for faster completion while `maxUnavailable=0` maintains full serving capacity
- **GPU constraint:** Verify you have L4 quota headroom for 10 extra nodes during upgrade
- **Autoscaler interaction:** Upgrade occurs on existing nodes; autoscaler will provision surge nodes

#### A100 Pool (Mixed Workload)
```bash
# Conservative approach for training protection
gcloud container node-pools update a100-mixed-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2
```
- **Rationale:** A100 reservations typically have no surge capacity. `maxUnavailable=2` provides reasonable upgrade velocity while protecting running training jobs
- **Training protection:** Upgrade will respect PDBs for up to 1 hour per node

## Pre-Upgrade Checklist

### Version & Compatibility
- [ ] Confirm 1.32 available in your release channel
- [ ] GPU driver compatibility: GKE 1.32 will auto-install updated NVIDIA drivers - test in staging first
- [ ] Verify PyTorch/TensorFlow framework compatibility with new CUDA version
- [ ] Check inference serving framework (TensorRT, vLLM, etc.) compatibility

### Training Job Protection
```bash
# Add maintenance exclusion to protect active training campaigns
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time "2024-MM-DDTHH:MM:SSZ" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```
- [ ] Set exclusion end time after training jobs complete
- [ ] Coordinate with ML team on training schedule

### Workload Readiness
- [ ] PDBs configured for inference services (allow ~20% unavailability max)
- [ ] Training jobs have checkpointing enabled for resume after upgrade
- [ ] No bare GPU pods - all managed by Deployments/Jobs
- [ ] Adequate `terminationGracePeriodSeconds` for model unloading (recommend 120s+)

### Infrastructure
- [ ] Verify L4 quota headroom for surge nodes (10 additional L4s)
- [ ] Confirm A100 reservation can handle 2 nodes being unavailable
- [ ] Autoscaler configuration allows scaling during upgrade
- [ ] Monitoring active for inference latency/error rates

## Upgrade Runbook

### Phase 1: Control Plane (Weekend, off-peak)
```bash
# Verify pre-conditions
kubectl get nodes | grep -E "NotReady|SchedulingDisabled"
# Should be empty

# Upgrade control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.X-gke.XXXX

# Verify (wait ~15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Phase 2: L4 Pool Upgrade (Inference workloads)
```bash
# Set surge configuration
gcloud container node-pools update l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 10 \
  --max-unavailable-upgrade 0

# Execute upgrade
gcloud container node-pools upgrade l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.XXXX

# Monitor progress
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=l4-inference-pool'
```

**Expected duration:** ~45-60 minutes for 200 nodes with 10-node parallelism

### Phase 3: A100 Pool Upgrade (After training jobs complete)
```bash
# Remove maintenance exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "training-protection"

# Configure conservative settings
gcloud container node-pools update a100-mixed-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2

# Execute upgrade
gcloud container node-pools upgrade a100-mixed-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.XXXX
```

**Expected duration:** ~3-4 hours for 100 nodes with 2-node parallelism

## GPU-Specific Considerations

### Driver Version Changes
- GKE 1.32 may update NVIDIA driver version automatically
- **Critical:** Test inference latency in staging - driver changes can affect performance
- Common issue: New CUDA version breaks framework compatibility

### Inference Serving Impact
- Each node upgrade requires pod restart (no live migration for GPU VMs)
- Autoscaler will handle traffic shifting to available nodes
- Monitor inference latency during L4 pool upgrade

### Training Job Coordination
```bash
# Check for running training jobs before A100 upgrade
kubectl get jobs -n training-namespace
kubectl get pods -l workload-type=training --field-selector=status.phase=Running
```

## Post-Upgrade Validation

### GPU Health
```bash
# Verify GPU visibility
kubectl get nodes -l accelerator=nvidia-l4 -o custom-columns=NAME:.metadata.name,GPU:.status.allocatable."nvidia\.com/gpu"
kubectl get nodes -l accelerator=nvidia-tesla-a100 -o custom-columns=NAME:.metadata.name,GPU:.status.allocatable."nvidia\.com/gpu"

# Test GPU workload
kubectl run gpu-test --image=nvidia/cuda:12.0-runtime-ubuntu20.04 --rm -it --restart=Never -- nvidia-smi
```

### Inference Performance
- [ ] Latency metrics within 5% of pre-upgrade baseline
- [ ] No inference serving errors
- [ ] Autoscaler scaling behavior normal
- [ ] Model loading times unchanged

### Training Capability
- [ ] Submit test training job to A100 pool
- [ ] Verify checkpointing/resumption works
- [ ] Multi-node training jobs function correctly

## Rollback Plan

If inference performance degrades significantly:

1. **Immediate:** Scale up additional capacity on old nodes (if any remain)
2. **Short-term:** Create new node pool at 1.31 with same machine types
3. **Migration:** Gradually migrate workloads to old version nodes

```bash
# Emergency rollback node pool
gcloud container node-pools create l4-rollback-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --machine-type g2-standard-24 \
  --accelerator type=nvidia-l4,count=2 \
  --cluster-version 1.31.X-gke.XXXX \
  --num-nodes 20
```

## Timeline Recommendation

- **Week 1:** Test 1.32 in staging cluster, validate framework compatibility
- **Week 2:** Schedule training downtime, apply maintenance exclusion
- **Weekend:** Execute control plane + L4 pool upgrade
- **Week 3:** Remove exclusion, upgrade A100 pool during training gap
- **Week 4:** Monitor performance, complete validation

This approach prioritizes inference availability while providing safe upgrade paths for your mixed GPU workloads.