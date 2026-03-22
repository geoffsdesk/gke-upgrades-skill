# GKE Fleet Upgrade Plan: v1.31 → v1.32

## Executive Summary
Phased upgrade strategy prioritizing training continuity and inference availability across 5,000-node mixed AI/ML platform.

## Pre-Upgrade Preparation

### Phase 0: Assessment & Preparation (Week 1)
- [ ] **Compatibility Audit**
  - Test critical ML frameworks (TensorFlow, PyTorch, JAX) on v1.32
  - Validate GPU drivers and CUDA compatibility
  - Test ML operators and custom resources
  
- [ ] **Backup & Documentation**
  - Document current workload distribution and node configurations
  - Backup critical training checkpoints and model artifacts
  - Create rollback procedures for each node pool

- [ ] **Monitoring Setup**
  - Enhance monitoring for training job health
  - Set up alerts for inference latency/availability
  - Prepare upgrade progress dashboards

## Phased Upgrade Strategy

### Phase 1: CPU Services Nodes (Days 1-2)
**Target**: 1,000 CPU nodes
**Strategy**: Rolling upgrade with 25% surge capacity

```bash
# Upgrade CPU node pools first (least critical path)
kubectl patch nodepool cpu-services-pool \
  --patch='{"spec":{"version":"1.32.x","upgradeSettings":{"maxSurge":"25%","maxUnavailable":"10%"}}}'
```

**Validation Criteria**:
- All support services healthy
- Monitoring/logging systems operational
- API gateway and ingress controllers stable

### Phase 2: Development T4 Nodes (Days 3-4)
**Target**: 500 T4 nodes
**Strategy**: Blue-green upgrade during off-peak hours

```bash
# Create new T4 node pool
gcloud container node-pools create t4-dev-v132 \
  --cluster=ml-cluster \
  --machine-type=g2-standard-4 \
  --accelerator=type=nvidia-tesla-t4,count=1 \
  --node-version=1.32.x \
  --num-nodes=500

# Migrate dev workloads
kubectl drain t4-dev-v131-nodes --ignore-daemonsets --delete-emptydir-data
```

**Validation Criteria**:
- Development environments accessible
- GPU drivers properly initialized
- Sample training jobs complete successfully

### Phase 3: A100 Inference Nodes (Days 5-8)
**Target**: 1,500 A100 nodes
**Strategy**: Canary upgrade with traffic shifting

#### Phase 3A: Canary Deployment (Day 5)
```bash
# Upgrade 10% of A100 nodes first
gcloud container node-pools create a100-inference-v132-canary \
  --cluster=ml-cluster \
  --machine-type=a2-highgpu-1g \
  --accelerator=type=nvidia-tesla-a100,count=1 \
  --node-version=1.32.x \
  --num-nodes=150
```

**Traffic Shifting**:
- Route 5% inference traffic to canary nodes
- Monitor latency, error rates, and GPU utilization
- Gradually increase to 10% over 24 hours

#### Phase 3B: Full A100 Upgrade (Days 6-8)
```bash
# Rolling upgrade remaining A100 nodes
for pool in a100-inference-pool-{1..10}; do
  kubectl patch nodepool $pool \
    --patch='{"spec":{"version":"1.32.x","upgradeSettings":{"maxSurge":"20%","maxUnavailable":"5%"}}}'
  
  # Wait for pool completion before next
  kubectl wait --for=condition=Ready nodepool/$pool --timeout=1h
done
```

**Validation Criteria**:
- Inference SLA maintained (p99 < 100ms)
- Model serving throughput unchanged
- GPU memory utilization normal
- No inference request failures

### Phase 4: H100 Training Nodes (Days 9-14)
**Target**: 2,000 H100 nodes
**Strategy**: Coordinated maintenance windows with checkpoint management

#### Phase 4A: Training Job Coordination (Day 9)
```bash
# Identify long-running training jobs
kubectl get pods -l app=training --field-selector=status.phase=Running \
  -o custom-columns="NAME:.metadata.name,AGE:.status.startTime,NODE:.spec.nodeName"

# Coordinate with ML teams for checkpoint schedules
```

#### Phase 4B: Staged H100 Upgrade (Days 10-14)
Upgrade in 400-node batches during planned maintenance windows:

```bash
# Batch 1: 400 nodes (Day 10)
# Drain nodes gracefully with extended timeout for training jobs
kubectl drain h100-training-nodes-batch1 \
  --ignore-daemonsets \
  --delete-emptydir-data \
  --timeout=3600s \
  --grace-period=1800

# Upgrade node pool
gcloud container node-pools upgrade h100-training-pool-1 \
  --cluster=ml-cluster \
  --node-version=1.32.x

# Repeat for batches 2-5 over subsequent days
```

**Training Job Management**:
- Coordinate 2-hour maintenance windows
- Ensure checkpointing before node drain
- Validate training job resumption post-upgrade

## Risk Mitigation & Rollback

### Rollback Procedures
```bash
# Emergency rollback script
#!/bin/bash
ROLLBACK_VERSION="1.31.x"

case $1 in
  "cpu") 
    kubectl patch nodepool cpu-services-pool \
      --patch='{"spec":{"version":"'$ROLLBACK_VERSION'"}}'
    ;;
  "inference")
    # Shift traffic back to v1.31 nodes
    kubectl patch service inference-service \
      --patch='{"spec":{"selector":{"version":"v131"}}}'
    ;;
  "training")
    # Emergency: keep existing training running, block new jobs
    kubectl patch deployment training-scheduler \
      --patch='{"spec":{"replicas":0}}'
    ;;
esac
```

### Success Criteria & Monitoring

#### Training Continuity Metrics
- Training job completion rate > 98%
- Average checkpoint interval < 2 hours during upgrades
- No training data loss incidents

#### Inference Availability Metrics
- Inference service uptime > 99.9%
- p99 inference latency < 100ms
- Zero customer-facing errors

#### Infrastructure Health
- Node ready state > 99%
- GPU utilization returns to baseline within 24h
- No persistent volume attachment issues

## Timeline Summary

| Phase | Duration | Nodes | Risk Level | Maintenance Window |
|-------|----------|-------|------------|-------------------|
| 0: Prep | 5 days | 0 | Low | Business hours |
| 1: CPU | 2 days | 1,000 | Low | Anytime |
| 2: T4 Dev | 2 days | 500 | Low | Off-peak |
| 3: A100 Inf | 4 days | 1,500 | Medium | 4h windows |
| 4: H100 Train | 6 days | 2,000 | High | 2h planned windows |

**Total Duration**: 19 days
**Business Impact**: Minimal with proper coordination

## Communication Plan
- Daily standups with ML teams during Phase 4
- Slack alerts for each phase completion
- Escalation path to platform team leads
- Post-upgrade performance reports

This plan ensures training continuity while maintaining inference SLA through careful sequencing and risk mitigation strategies.