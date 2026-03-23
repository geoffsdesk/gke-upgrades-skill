# GKE 1.31 → 1.32 Upgrade Plan: AI/ML Platform
**5,000 Node Mixed Fleet Upgrade Strategy**

## Executive Summary

This plan prioritizes **training continuity** (H100 pools) and **inference availability** (A100 pools) while upgrading your mixed AI/ML platform. The strategy uses maintenance exclusions, phased execution, and GPU-optimized upgrade techniques to minimize business impact.

**Total Timeline: 3-4 weeks**
- Phase 1: CPU services (Week 1)
- Phase 2: T4 development (Week 1-2)
- Phase 3: A100 inference (Week 2-3)
- Phase 4: H100 training (Week 3-4, during planned training gaps)

## Fleet Configuration Assessment

```bash
# Verify current state across all clusters
for CLUSTER in cpu-services t4-dev a100-inference h100-training; do
  echo "=== $CLUSTER ==="
  gcloud container clusters describe $CLUSTER --zone=ZONE \
    --format="table(name, currentMasterVersion, releaseChannel.channel, nodePools[].name, nodePools[].version)"
done
```

**Assumptions (please verify):**
- All clusters on Regular or Stable release channel
- 1.32 available in your release channel
- Current training campaigns can accommodate 1-week maintenance window
- H100 pools have no surge capacity (fixed reservations)
- A100 inference pools need 95%+ availability during upgrade

## Phase 1: CPU Services (Week 1)
**1,000 CPU nodes | Risk: LOW | Downtime: Minutes**

### Strategy: Rolling surge upgrade
CPU nodes support surge upgrades and have flexible capacity.

### Pre-Phase Checklist
```
- [ ] Baseline metrics captured (latency, error rates)
- [ ] Load balancer health checks verified
- [ ] PDBs configured (minAvailable: 50% for stateless services)
- [ ] Maintenance window: Weeknight 2-6 AM local time
```

### Commands
```bash
CLUSTER_NAME="cpu-services"
TARGET_VERSION="1.32.x-gke.latest"  # Check actual available version

# Control plane first
gcloud container clusters upgrade $CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version $TARGET_VERSION

# Configure aggressive surge for CPU pools (fast completion)
for POOL in frontend backend api; do
  gcloud container node-pools update $POOL \
    --cluster $CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 10% \
    --max-unavailable-upgrade 0
  
  # Upgrade
  gcloud container node-pools upgrade $POOL \
    --cluster $CLUSTER_NAME \
    --zone ZONE \
    --cluster-version $TARGET_VERSION
done
```

### Validation
```bash
# Verify all services responding
kubectl get pods -A | grep -v Running | grep -v Completed
# Check ingress/load balancer health
# Confirm baseline metrics within 5% of pre-upgrade
```

## Phase 2: T4 Development (Week 1-2)
**500 T4 nodes | Risk: LOW | Downtime: Acceptable**

### Strategy: Maintenance exclusion + scheduled upgrade
T4 is for development - can tolerate restarts. Use this as GPU upgrade rehearsal.

### Pre-Phase Checklist
```
- [ ] Notify dev teams of maintenance window
- [ ] Test GPU driver compatibility: CUDA version may change
- [ ] Backup any long-running experiments
- [ ] Clear maintenance exclusions if any exist
```

### Commands
```bash
CLUSTER_NAME="t4-dev"

# Control plane
gcloud container clusters upgrade $CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version $TARGET_VERSION

# T4 GPU pools: maxUnavailable mode (no surge capacity assumed)
for POOL in t4-pool-1 t4-pool-2; do
  gcloud container node-pools update $POOL \
    --cluster $CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 2  # 2 nodes at a time
  
  gcloud container node-pools upgrade $POOL \
    --cluster $CLUSTER_NAME \
    --zone ZONE \
    --cluster-version $TARGET_VERSION
done
```

### GPU Driver Validation
```bash
# Post-upgrade: verify CUDA/driver versions
kubectl create job gpu-test --image=nvidia/cuda:12.0-runtime-ubuntu20.04 \
  -- nvidia-smi
kubectl logs job/gpu-test
# Confirm CUDA version matches framework requirements
```

## Phase 3: A100 Inference (Week 2-3)
**1,500 A100 nodes | Risk: MEDIUM | Downtime: <5 minutes per batch**

### Strategy: Conservative batched upgrade with availability protection
A100 inference must maintain serving capacity. Use small batches with PDB protection.

### Pre-Phase Checklist
```
- [ ] PDBs configured: minAvailable: 80% for inference workloads
- [ ] GPU reservation capacity confirmed (no surge capacity)
- [ ] Inference model warmup time measured
- [ ] Client retry/circuit breaker logic verified
- [ ] Maintenance window: Weekend, staggered across regions
```

### Commands
```bash
CLUSTER_NAME="a100-inference"

# Control plane
gcloud container clusters upgrade $CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version $TARGET_VERSION

# A100 inference pools: VERY conservative upgrade
for POOL in a100-inference-1 a100-inference-2 a100-inference-3; do
  gcloud container node-pools update $POOL \
    --cluster $CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 1  # 1 node at a time - slowest but safest
  
  # Upgrade with monitoring between batches
  gcloud container node-pools upgrade $POOL \
    --cluster $CLUSTER_NAME \
    --zone ZONE \
    --cluster-version $TARGET_VERSION
  
  # Wait for batch completion, verify serving capacity
  echo "Monitoring $POOL upgrade..."
  # Check inference latency/throughput before continuing
done
```

### Inference Availability Monitoring
```bash
# Monitor during upgrade
watch 'kubectl get pods -l app=inference -o wide | grep Running | wc -l'
# Target: >80% pods Running throughout upgrade
# Check inference endpoint response times
```

## Phase 4: H100 Training (Week 3-4)
**2,000 H100 nodes | Risk: HIGH | Downtime: Coordinated with training schedule**

### Strategy: Maintenance exclusion + coordinated training gap upgrade
H100 training jobs run for days/weeks. Coordinate with ML teams for planned checkpointing.

### Critical Pre-Phase Steps
```
- [ ] Training job checkpoint schedule confirmed
- [ ] All active training jobs will complete or checkpoint by upgrade start
- [ ] H100 maintenance exclusion currently active: "no minor or node upgrades"
- [ ] RDMA/GPUDirect-TCPX configuration documented
- [ ] Compact placement group topology verified
```

### Training Coordination Protocol
1. **T-72h**: Notify ML teams, confirm checkpoint timing
2. **T-24h**: Stop accepting new training jobs
3. **T-4h**: Checkpoint and pause all running jobs
4. **T-0h**: Begin upgrade

### Commands
```bash
CLUSTER_NAME="h100-training"

# FIRST: Remove maintenance exclusion to allow upgrade
gcloud container clusters update $CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "no-training-disruption"

# Control plane
gcloud container clusters upgrade $CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version $TARGET_VERSION

# H100 training pools: Parallel strategy for minimum total time
# All training stopped, so upgrade all nodes simultaneously
for POOL in h100-pool-1 h100-pool-2 h100-pool-3 h100-pool-4; do
  # Use maxUnavailable = ALL nodes in pool for fastest completion
  POOL_SIZE=$(gcloud container node-pools describe $POOL \
    --cluster $CLUSTER_NAME --zone ZONE \
    --format="value(initialNodeCount)")
  
  gcloud container node-pools update $POOL \
    --cluster $CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade $POOL_SIZE  # Drain entire pool at once
done

# Upgrade all H100 pools in parallel (training is stopped anyway)
for POOL in h100-pool-1 h100-pool-2 h100-pool-3 h100-pool-4; do
  gcloud container node-pools upgrade $POOL \
    --cluster $CLUSTER_NAME \
    --zone ZONE \
    --cluster-version $TARGET_VERSION &
done

# Wait for all upgrades to complete
wait
echo "All H100 pools upgraded"
```

### Post-H100 Upgrade Validation
```bash
# Verify GPUDirect-TCPX still functional
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: gpu-test
    image: nvidia/cuda:12.0-runtime-ubuntu20.04
    command: ["nvidia-smi", "-L"]
  nodeSelector:
    accelerator: nvidia-tesla-h100
EOF

# Verify compact placement intact
kubectl get nodes -l accelerator=nvidia-tesla-h100 \
  -o custom-columns=NAME:.metadata.name,ZONE:.metadata.labels.topology\.gke\.io/zone

# Test training job startup (small test job first)
```

### Restore Training Protection
```bash
# Re-apply maintenance exclusion for next training campaign
gcloud container clusters update $CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-training-disruption-post-upgrade" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Timeline and Dependencies

| Week | Phase | Duration | Dependencies |
|------|-------|----------|--------------|
| 1 | CPU Services | 2-3 hours | None |
| 1-2 | T4 Development | 8-12 hours | CPU complete |
| 2-3 | A100 Inference | 24-48 hours | T4 validation complete |
| 3-4 | H100 Training | 16-24 hours | Training checkpoint window |

**Critical Path:** H100 training window availability determines overall timeline.

## Risk Mitigation

### High-Risk Scenarios and Mitigations

**1. GPU Driver Incompatibility**
- **Risk**: CUDA version change breaks training frameworks
- **Mitigation**: Test on T4 first, maintain staging environment on 1.32

**2. H100 Training Job Loss**
- **Risk**: Checkpoint failure during upgrade window
- **Mitigation**: 72h advance notice, mandatory checkpoint verification

**3. A100 Inference Capacity Shortage**
- **Risk**: <80% capacity during upgrade causes user impact
- **Mitigation**: 1-node-at-a-time strategy, PDB enforcement, rollback plan

**4. RDMA/GPUDirect Topology Disruption**
- **Risk**: New H100 nodes break high-speed interconnect
- **Mitigation**: Test compact placement group preservation, verify TCPX post-upgrade

### Rollback Strategy
```bash
# Node pool rollback: create new pool at old version
gcloud container node-pools create POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.xxx \
  --num-nodes NUM_NODES \
  --machine-type MACHINE_TYPE

# Migrate workloads to rollback pool
kubectl cordon -l cloud.google.com/gke-nodepool=ORIGINAL_POOL
# Drain and delete original pool
```

**Control plane rollback**: Contact GKE support - minor version downgrades require assistance.

## Success Criteria

### Per-Phase Validation
- **CPU**: <2% latency increase, 0 failed health checks
- **T4**: GPU workloads can access CUDA, development environments functional
- **A100**: >95% inference availability maintained, <5% latency increase
- **H100**: All GPUs visible, RDMA functional, training jobs can restart

### Fleet-Wide Success
- All clusters on GKE 1.32.x
- All workloads healthy and performing within baseline
- No version skew >1 minor between control plane and nodes
- Training exclusions re-applied for next campaign

## Commands Summary

```bash
# Monitor all phases
watch 'gcloud container operations list --format="table(name,operationType,status,startTime)" --filter="operationType~UPGRADE"'

# Emergency pause (if needed)
# Note: Can't cancel in-progress operations, but can prevent new ones
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "emergency-pause" \
  --add-maintenance-exclusion-scope no_upgrades \
  --add-maintenance-exclusion-end-time $(date -d '+1 day' -u +%Y-%m-%dT%H:%M:%SZ)
```

This plan balances the unique requirements of your AI/ML workloads while minimizing risk through phased execution and workload-specific strategies. The H100 training protection and A100 inference availability preservation are the key differentiators from a standard upgrade approach.