# GKE Upgrade Plan: Large-Scale LLM Training Cluster

## Executive Summary
For your 512-node H100 training cluster, this upgrade requires **careful orchestration around active training runs** due to the 2-3 week duration and GPUDirect-TCPXO networking requirements. The key is using **maintenance exclusions to block upgrades during training** and **validating GPU interconnect compatibility** before proceeding.

## Current Environment Analysis
- **Cluster**: GKE Standard, 512 H100 nodes (A3 Mega)
- **Current version**: GKE 1.31 → **Target**: 1.32
- **GPU interconnect**: GPUDirect-TCPXO (requires GKE 1.27.7-gke.1121000+)
- **Training duration**: 2-3 weeks per run
- **Risk profile**: Extremely high — any mid-training interruption costs weeks of compute

## Critical Prerequisites

### 1. GPUDirect-TCPXO Compatibility Check
```bash
# Verify target GKE 1.32 version supports GPUDirect-TCPXO
gcloud container get-server-config --zone YOUR_ZONE \
  --format="yaml(channels)" | grep -A 10 "1\.32"

# Check current TCPXO status
kubectl get nodes -o wide -L cloud.google.com/gke-accelerator
kubectl describe node NODE_NAME | grep -i tcpx
```

**Action required**: Test GPUDirect-TCPXO functionality on a staging A3 Mega cluster at GKE 1.32 before proceeding. Verify RDMA topology, bandwidth, and training performance are unaffected.

### 2. Training Run Coordination
```bash
# Check current training job status
kubectl get pods -l workload=training -o wide
kubectl get jobs -l workload=training
```

**Critical decision point**: Is there an active 2-3 week training run? If yes, defer this upgrade until the run completes + validation buffer.

## Upgrade Strategy: Maintenance Exclusion + Scheduled Window

### Phase 1: Immediate Protection (if training active)

Apply a maintenance exclusion to **block all upgrades during the active training period**:

```bash
# Block all upgrades for 30 days (maximum exclusion period)
gcloud container clusters update YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "llm-training-protection" \
  --add-maintenance-exclusion-start-time "2024-12-10T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-01-09T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**Chain additional exclusions if needed** (max 3 per cluster):
```bash
# If training extends beyond 30 days, chain a second exclusion
gcloud container clusters update YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "llm-training-protection-2" \
  --add-maintenance-exclusion-start-time "2025-01-09T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-02-08T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

### Phase 2: Staging Validation

While training runs under exclusion protection, validate the target version:

```bash
# Create staging A3 Mega node pool at GKE 1.32
gcloud container node-pools create staging-h100-132 \
  --cluster YOUR_STAGING_CLUSTER \
  --zone YOUR_ZONE \
  --cluster-version 1.32.x-gke.xxxx \
  --machine-type a3-megagpu-8g \
  --accelerator type=nvidia-h100-mega-80gb,count=8 \
  --num-nodes 2 \
  --enable-gvnic \
  --placement-type COMPACT
```

**Validation checklist**:
- [ ] GPUDirect-TCPXO links establish correctly
- [ ] RDMA bandwidth tests pass (`nccl-tests`)
- [ ] Sample training job completes without GPU errors
- [ ] Driver version compatibility (check CUDA version changes)
- [ ] Compact placement preserved (nodes in same physical group)

### Phase 3: Production Upgrade (after training completion)

**Timing**: Schedule upgrade for the gap between training runs (typically 1-3 days for checkpointing, validation, and next run setup).

#### Control Plane Upgrade
```bash
# Remove maintenance exclusion first
gcloud container clusters update YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --remove-maintenance-exclusion "llm-training-protection"

# Upgrade control plane (safe - no workload impact)
gcloud container clusters upgrade YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --master \
  --cluster-version 1.32.x-gke.xxxx
```

#### Node Pool Upgrade Strategy

**For your 512-node GPU pool, use `maxUnavailable` mode** (no surge capacity available for H100s):

```bash
# Configure conservative upgrade settings
gcloud container node-pools update gpu-training-pool \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4
```

**Why maxUnavailable=4**: 
- 512 nodes ÷ ~20 max parallelism = ~26 upgrade batches
- 4 nodes per batch balances speed vs. capacity loss
- Each batch takes ~45-60 minutes (drain + provision + ready)
- **Total upgrade time**: ~20-26 hours for the full pool

#### Upgrade Execution
```bash
# Checkpoint any running workloads first
kubectl scale deployment non-critical-workloads --replicas=0

# Start node pool upgrade
gcloud container node-pools upgrade gpu-training-pool \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --cluster-version 1.32.x-gke.xxxx
```

#### Monitor Progress
```bash
# Real-time node upgrade tracking
watch 'kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,READY:.status.conditions[3].status | grep -E "gpu-training"'

# Check for stuck upgrades
gcloud container operations list \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --filter="operationType=UPGRADE_NODES AND status=RUNNING"
```

## Post-Upgrade Validation

### GPU Interconnect Verification
```bash
# Verify GPUDirect-TCPXO restored
kubectl exec -it gpu-pod-0 -- nvidia-smi topo -m
kubectl exec -it gpu-pod-0 -- /usr/local/nvidia/bin/nccl-tests/all_reduce_perf -b 1G -e 8G -f 2

# Check compact placement preserved
kubectl get nodes -o custom-columns=NAME:.metadata.name,ZONE:.metadata.labels.topology\.gke\.io/zone
```

### Training Readiness Check
```bash
# Deploy test training job (small scale)
kubectl apply -f test-training-job.yaml

# Monitor GPU utilization and interconnect
kubectl exec -it training-pod-0 -- watch nvidia-smi
```

## Risk Mitigation

### 1. Compact Placement Risk
**Risk**: Upgraded nodes may not land in the same physical placement group, breaking RDMA topology.
**Mitigation**: Verify in staging that replacement nodes honor compact placement policy. If not, contact GKE support before production upgrade.

### 2. Training Run Interruption
**Risk**: Exclusion expires or upgrade auto-triggers during training.
**Mitigation**: Set calendar reminders to extend exclusions if training runs longer than expected. Monitor upgrade notifications in Cloud Logging.

### 3. Extended Upgrade Duration
**Risk**: 512 nodes take 20+ hours to upgrade, extending the training gap.
**Mitigation**: 
- Schedule during planned maintenance windows (weekends)
- Have next training job ready to deploy immediately after validation
- Consider upgrading in smaller batches during longer training gaps

### 4. GPU Driver Changes
**Risk**: GKE 1.32 may include different GPU drivers, changing CUDA version or compatibility.
**Mitigation**: Test exact training container images against staging cluster at target version. Rebuild containers if needed.

## Maintenance Window Configuration

Set a recurring weekend window for future upgrades:

```bash
gcloud container clusters update YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --maintenance-window-start "2024-12-15T02:00:00Z" \
  --maintenance-window-end "2024-12-15T10:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Long-term Strategy

1. **Dedicated training node pool**: Isolate training workloads with persistent maintenance exclusions
2. **Extended release channel**: Consider migrating to Extended channel for longer support cycles (24 months)
3. **Rollout sequencing**: Implement fleet-based rollout (dev → staging → prod) once available

## Emergency Contacts

- **GKE support case**: Pre-file for A3 Mega / GPUDirect-TCPXO specific guidance
- **Training team escalation**: Define clear go/no-go criteria for upgrade timing

This plan prioritizes **protecting your active training investment** while ensuring safe upgrade execution during planned maintenance windows.