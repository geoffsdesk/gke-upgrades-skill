# LLM Training Cluster Upgrade Plan: GKE 1.31 → 1.32

## Executive Summary

**Critical constraint**: 2-3 week training runs cannot tolerate node eviction. This upgrade requires careful orchestration around your training schedule and GPU interconnect requirements.

**Recommended approach**: Use maintenance exclusions to protect active training, upgrade during natural training gaps, and leverage dedicated node pool isolation.

## Environment Assessment

- **Cluster**: 512 H100 nodes (A3 Mega, 8×H100 each = 4,096 total GPUs)
- **Interconnect**: GPUDirect-TCPXO (requires GKE 1.27.7-gke.1121000+)
- **Training duration**: 2-3 weeks per run
- **Current version**: GKE 1.31 → Target: 1.32
- **Upgrade complexity**: High (GPU, RDMA, long-running workloads)

## Critical Considerations

### 1. GPUDirect-TCPXO Compatibility
✅ **Good news**: Both GKE 1.31 and 1.32 support GPUDirect-TCPXO. Your interconnect will remain functional.

**Verification step**: Test the target GKE 1.32 version in a staging cluster to confirm:
- TCPXO driver compatibility
- NCCL library versions
- Training framework compatibility (PyTorch/JAX)

### 2. Training Job Protection Strategy

**Node upgrade behavior**: GPU VMs do not support live migration. Every node upgrade requires pod restart, which would kill your 2-3 week training run.

**Required approach**: Coordinate upgrades with your training schedule using one of these patterns:

## Upgrade Strategy: Training-Aware Approach

### Option A: Maintenance Exclusion + Scheduled Upgrade (Recommended)

**Timeline**: Upgrade during natural gaps between training runs.

```bash
# 1. Apply "no minor or node upgrades" exclusion to protect active training
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# 2. Configure maintenance window for your preferred upgrade time
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-window-start "2024-01-20T02:00:00Z" \
  --maintenance-window-duration "8h" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Upgrade execution** (during training gap):
```bash
# 1. Remove maintenance exclusion
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --remove-maintenance-exclusion "training-protection"

# 2. Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.32.x-gke.XXXX

# 3. Upgrade GPU node pools (will cause full restart)
gcloud container node-pools upgrade gpu-training-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.32.x-gke.XXXX
```

### Option B: Dedicated Training Pool Isolation

**Architecture**: Separate GPU pools for training vs. other workloads.

```bash
# Create dedicated training pool with auto-upgrade disabled via exclusion
gcloud container node-pools create training-pool-v2 \
  --cluster CLUSTER_NAME \
  --region REGION \
  --machine-type a3-megagpu-8g \
  --num-nodes 512 \
  --cluster-version 1.32.x-gke.XXXX \
  --enable-gvnic \
  --placement-type COMPACT

# Apply exclusion to training pool only
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "training-pool-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-node-pool "training-pool-v2" \
  --add-maintenance-exclusion-until-end-of-support
```

## GPU-Specific Upgrade Configuration

### Node Pool Upgrade Settings

For your 512-node H100 cluster, use these surge settings:

```bash
# Configure conservative upgrade strategy for GPU pools
gcloud container node-pools update gpu-training-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 8
```

**Rationale**:
- `maxSurge=0`: H100 capacity is scarce, assume no surge capacity available
- `maxUnavailable=8`: Upgrade 8 nodes at a time (64 GPUs), balancing speed vs. disruption
- **Expected duration**: ~16 hours for 512 nodes (64 batches × 15 min per batch)

### Compact Placement Preservation

**Critical**: Verify replacement nodes land in the same compact placement group to preserve RDMA topology.

```bash
# Check placement policy after upgrade
kubectl get nodes -o custom-columns="NAME:.metadata.name,ZONE:.metadata.labels.topology\.gke\.io/zone,PLACEMENT:.metadata.labels.cloud\.google\.com/gke-placement-group-name"
```

## Pre-Upgrade Checklist

```markdown
## LLM Training Cluster Pre-Upgrade Checklist

### Training Schedule Coordination
- [ ] Current training run completion date confirmed: ___
- [ ] Next training run start date: ___
- [ ] Upgrade window identified between runs: ___
- [ ] Training team notified of maintenance window

### GPU Infrastructure
- [ ] GPUDirect-TCPXO tested on GKE 1.32 in staging cluster
- [ ] CUDA driver version compatibility confirmed
- [ ] NCCL library version tested with target GKE version
- [ ] Training framework (PyTorch/JAX) compatibility verified
- [ ] Compact placement group requirements documented

### Backup & Recovery
- [ ] Latest training checkpoint saved and verified
- [ ] Model artifacts backed up to Cloud Storage
- [ ] Training resumption procedure tested
- [ ] Container images tagged and stored in Artifact Registry

### Cluster State
- [ ] No active training jobs running: `kubectl get pods -l workload-type=training`
- [ ] GPU utilization at 0%: Check monitoring dashboard
- [ ] All training data synced to persistent storage
- [ ] Training node pool health verified: `kubectl get nodes -l node-pool=training-pool`

### Network & Performance
- [ ] High-MTU VPC configuration documented
- [ ] RDMA traffic patterns baselined
- [ ] Network performance benchmarks captured
- [ ] Interconnect topology mapped and documented
```

## Upgrade Execution Runbook

### Phase 1: Control Plane (Low Risk)
```bash
# Control plane upgrade (~15 minutes)
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.32.x-gke.XXXX

# Verify
kubectl get nodes  # Should show old node versions, new CP version
kubectl get pods -n kube-system  # All system pods healthy
```

### Phase 2: GPU Node Pool (High Risk - Requires Training Downtime)
```bash
# Set conservative upgrade strategy
gcloud container node-pools update gpu-training-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 8

# Execute node upgrade (will restart all training pods)
gcloud container node-pools upgrade gpu-training-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.32.x-gke.XXXX

# Monitor progress (~16 hours for 512 nodes)
watch 'kubectl get nodes -o wide | grep -E "v1.31|v1.32" | wc -l'
```

### Phase 3: Validation
```bash
# Verify all nodes upgraded
kubectl get nodes -o custom-columns="NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion"

# Test GPU availability
kubectl apply -f gpu-test-job.yaml
kubectl logs job/gpu-test

# Verify GPUDirect-TCPXO
# Run NCCL bandwidth test across nodes
kubectl apply -f nccl-bandwidth-test.yaml

# Test training resumption
kubectl apply -f training-checkpoint-test.yaml
```

## Risk Mitigation

### 1. Staging Environment Testing
**Critical**: Test the exact upgrade path in a smaller staging cluster first:
- Same GKE versions (1.31 → 1.32)
- Same machine types (A3 Mega)
- Same network configuration (GPUDirect-TCPXO)
- Run abbreviated training job to verify functionality

### 2. Checkpointing Strategy
```yaml
# Ensure training jobs have robust checkpointing
apiVersion: batch/v1
kind: Job
metadata:
  name: llm-training
spec:
  template:
    spec:
      containers:
      - name: trainer
        env:
        - name: CHECKPOINT_INTERVAL
          value: "600"  # Checkpoint every 10 minutes
        - name: CHECKPOINT_PATH
          value: "gs://your-bucket/checkpoints/"
```

### 3. Rollback Plan

**Control plane rollback**: Contact GKE support (minor version downgrade requires assistance).

**Node pool rollback**: Create new pool at old version, migrate workloads:
```bash
# Emergency rollback: create replacement pool
gcloud container node-pools create gpu-training-pool-rollback \
  --cluster CLUSTER_NAME \
  --region REGION \
  --machine-type a3-megagpu-8g \
  --cluster-version 1.31.x-gke.XXXX \
  --num-nodes 512
```

## Timeline Recommendation

**Total upgrade duration**: ~18-20 hours (control plane + node pool upgrade + validation)

**Suggested schedule**:
- **Friday 6 PM**: Complete current training run, save checkpoint
- **Saturday 12 AM**: Begin upgrade (control plane: 12:00-12:15 AM)
- **Saturday 12:30 AM**: Begin node pool upgrade (12:30 AM - 4:30 PM)
- **Saturday 5 PM**: Complete validation and testing
- **Sunday 12 AM**: Resume training if all tests pass

## Cost Considerations

**No additional cost** during upgrade since you're using `maxUnavailable` (not creating extra nodes). However, budget for:
- Lost training time: ~24 hours of cluster downtime
- Compute cost of validation testing
- Potential rollback scenario (temporary double capacity)

This approach protects your multi-week training investment while ensuring a safe upgrade path that preserves your GPU interconnect performance.