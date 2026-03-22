# GKE Upgrade Plan: ML Platform (GPU Inference + Training)

## Environment Summary
- **Cluster**: Standard mode, GPU-heavy (200 L4 + 100 A100 nodes)
- **Workload types**: Inference (latency-sensitive) + fine-tuning training (4-8h jobs)
- **Upgrade path**: 1.31 → 1.32 (single minor version, good)
- **Primary concern**: Minimize inference impact while protecting training jobs

## Upgrade Strategy Overview

**Control plane**: Standard minor upgrade (rollbackable first step)
**Node pools**: Different strategies per workload type:
- **L4 pool (inference)**: Rolling strategy with autoscaled blue-green upgrade
- **A100 pool (training)**: Maintenance exclusion + manual coordination

## Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist
- [ ] Cluster: ML-Platform | Mode: Standard | Channel: ___
- [ ] Current version: 1.31 | Target version: 1.32

GPU-Specific Compatibility
- [ ] CUDA driver compatibility verified for 1.32 (test in staging cluster first)
- [ ] GPU reservations checked — L4 and A100 capacity confirmed
- [ ] Inference framework compatibility (TensorFlow/PyTorch/TensorRT) with new node image
- [ ] Fine-tuning operator/controller compatibility verified
- [ ] No deprecated APIs in ML workloads (check deprecation insights dashboard)

Workload Protection Strategy
- [ ] A100 training pool: "no minor or node upgrades" exclusion configured
- [ ] L4 inference pool: autoscaled blue-green upgrade selected
- [ ] Current training jobs catalogued — coordinate upgrade during job gaps
- [ ] PDBs on inference workloads reviewed (not overly restrictive)
- [ ] Inference health checks and load balancer configuration verified

Infrastructure Readiness
- [ ] GPU quota sufficient for blue-green (L4 pool needs temporary 2x capacity)
- [ ] Maintenance window scheduled during low-traffic period
- [ ] Monitoring baseline captured (inference latency, throughput, GPU utilization)
- [ ] Rollback plan documented
```

## Step-by-Step Runbook

### Phase 1: Control Plane Upgrade (15-20 minutes)

```bash
# Check current versions
gcloud container clusters describe ML-Platform \
  --zone ZONE \
  --format="table(currentMasterVersion, nodePools[].name, nodePools[].version)"

# Upgrade control plane first
gcloud container clusters upgrade ML-Platform \
  --zone ZONE \
  --master \
  --cluster-version=1.32.X-gke.Y

# Verify control plane health
kubectl get pods -n kube-system
kubectl get nodes  # Should still show 1.31 for node pools
```

### Phase 2: Protect A100 Training Pool

```bash
# Add maintenance exclusion to A100 pool (blocks node upgrades)
gcloud container clusters update ML-Platform \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-freeze" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time $(date -u -d '+7 days' +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Verify exclusion applied
gcloud container clusters describe ML-Platform \
  --zone ZONE \
  --format="value(maintenancePolicy.window.exclusions)"
```

### Phase 3: L4 Inference Pool Upgrade (Auto-scale Blue-Green)

```bash
# Configure autoscaled blue-green for L4 inference pool
gcloud container node-pools update l4-inference-pool \
  --cluster ML-Platform \
  --zone ZONE \
  --enable-autoscaling \
  --enable-blue-green-update \
  --node-pool-soak-duration 300s \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 0

# Start the upgrade (creates green pool, gradually migrates traffic)
gcloud container node-pools upgrade l4-inference-pool \
  --cluster ML-Platform \
  --zone ZONE \
  --cluster-version 1.32.X-gke.Y

# Monitor progress - blue pool cordoned, green pool scaling up
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=l4-inference-pool -o wide'
```

**Why autoscaled blue-green for inference?**
- Maintains serving capacity throughout upgrade
- Green pool auto-scales based on actual demand
- 5-minute soak period validates new nodes before full cutover
- Fast rollback if issues detected (uncordon blue pool)

### Phase 4: Monitor Inference Impact

```bash
# Track inference pod distribution during migration
kubectl get pods -n inference -o wide | grep l4-inference-pool

# Monitor key metrics
kubectl top nodes -l accelerator=nvidia-l4
kubectl get hpa -n inference  # Horizontal Pod Autoscaler behavior

# Check for any pod scheduling issues
kubectl get events -A --field-selector reason=FailedScheduling | grep l4
```

### Phase 5: A100 Training Pool (Coordinate with Jobs)

**Wait for training jobs to complete naturally, then:**

```bash
# Check current training jobs
kubectl get pods -n training -o wide | grep a100-training-pool

# When jobs finish, remove maintenance exclusion
gcloud container clusters update ML-Platform \
  --zone ZONE \
  --remove-maintenance-exclusion-name "training-freeze"

# Configure A100 pool for upgrade (no surge capacity assumed)
gcloud container node-pools update a100-training-pool \
  --cluster ML-Platform \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1  # One node at a time

# Upgrade A100 pool
gcloud container node-pools upgrade a100-training-pool \
  --cluster ML-Platform \
  --zone ZONE \
  --cluster-version 1.32.X-gke.Y
```

**Why `maxUnavailable=1` for A100?**
- A100 reservations typically have no surge capacity
- Drains one node at a time, creates replacement
- Slower but works within fixed GPU allocations
- Training workloads can wait for available capacity

## GPU-Specific Considerations

### CUDA Driver Version Changes
- GKE 1.32 may ship with newer CUDA drivers than 1.31
- **Critical**: Test inference and training workloads in staging first
- Common issue: TensorRT engines compiled for older CUDA won't run on newer drivers

### GPU Node Upgrade Behavior
- **No live migration**: Every GPU pod restarts during node upgrade
- **Reservation interaction**: Surge upgrades consume reservation slots
- **Driver installation**: ~2-3 minutes additional boot time for GPU driver setup

### Autoscaler Interactions
- Cluster autoscaler can only scale one node pool at a time
- During blue-green upgrade, both pools may scale simultaneously
- Monitor for resource contention or quota limits

## Rollback Plan

### If Inference Issues Detected
```bash
# Fast rollback during blue-green phase (uncordon blue pool)
kubectl uncordon -l cloud.google.com/gke-nodepool=l4-inference-pool-blue

# Scale down green pool if needed
gcloud container node-pools update l4-inference-pool-green \
  --cluster ML-Platform \
  --zone ZONE \
  --num-nodes 0
```

### If CUDA/Driver Issues
```bash
# Create replacement pool at old version
gcloud container node-pools create l4-inference-rollback \
  --cluster ML-Platform \
  --zone ZONE \
  --cluster-version 1.31.X-gke.Y \
  --machine-type g2-standard-8 \
  --accelerator type=nvidia-l4,count=1 \
  --num-nodes 50

# Migrate inference workloads to rollback pool
kubectl label nodes -l cloud.google.com/gke-nodepool=l4-inference-rollback inference-ready=true
```

## Post-Upgrade Validation

```markdown
Post-Upgrade Validation

GPU Health
- [ ] All GPU nodes at 1.32: `kubectl get nodes -l accelerator`
- [ ] GPU drivers loaded: `kubectl get pods -n kube-system -l name=nvidia-driver-installer`
- [ ] CUDA version verified: `kubectl exec -it GPU_POD -- nvidia-smi`

Inference Workloads
- [ ] All inference pods Running and Ready
- [ ] Load balancer health checks passing
- [ ] P95 latency within baseline (±10%)
- [ ] Throughput (requests/sec) maintained
- [ ] GPU utilization normal (check monitoring)

Training Capability
- [ ] Sample training job completes successfully on A100 pool
- [ ] Checkpointing and resumption working
- [ ] Multi-node training communication verified (if applicable)

Autoscaling
- [ ] HPA responding to traffic changes
- [ ] Cluster autoscaler creating/destroying nodes properly
- [ ] No scheduling conflicts between pools
```

## Timeline Estimate

- **Control plane**: 15-20 minutes
- **L4 pool (blue-green)**: 2-3 hours for 200 nodes
- **A100 pool (wait + upgrade)**: Variable based on training schedule + 3-4 hours upgrade time
- **Total**: 6-24 hours depending on training job coordination

## Key Success Metrics

1. **Zero inference downtime** during L4 pool upgrade
2. **No training job termination** on A100 pool
3. **P95 latency increase <10%** during and after upgrade
4. **All GPU workloads healthy** within 1 hour of completion

This strategy prioritizes your inference SLA while safely upgrading the training infrastructure during natural job gaps.