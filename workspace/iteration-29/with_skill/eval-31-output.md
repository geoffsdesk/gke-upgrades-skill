# GKE Upgrade Plan: Large-Scale LLM Training Cluster (H100/A3 Mega)

## Executive Summary

For your 512-node H100 training cluster, this upgrade requires **careful orchestration around active training runs** and **GPUDirect-TCPXO compatibility verification**. The recommended approach uses maintenance exclusions to block upgrades during training, then upgrades during planned training gaps with parallel host maintenance strategy.

## Environment Analysis

- **Cluster**: 512 H100 nodes (A3 Mega, 8 GPUs each = 4,096 total GPUs)
- **Current**: GKE 1.31 → **Target**: GKE 1.32
- **Workload**: Multi-week LLM training (disruption-intolerant)
- **Networking**: GPUDirect-TCPXO (requires validation)
- **Scale**: Frontier AI cluster requiring specialized approach

## Critical Constraints

### 1. GPUDirect-TCPXO Compatibility
GPUDirect-TCPXO has specific GKE version requirements for A3 Mega machines. **Before proceeding**, verify GKE 1.32 supports TCPXO:

```bash
# Check current TCPXO status
kubectl get nodes -o jsonpath='{.items[*].metadata.labels.cloud\.google\.com/gke-accelerator}' | grep nvidia-h100-mega
# Verify TCPXO networking config survives version bump in staging
```

⚠️ **Pre-requisite**: Test GKE 1.32 + TCPXO in a small staging cluster with representative multi-node communication before production upgrade.

### 2. Training Run Protection
- **GKE's default pod eviction timeout**: 1 hour (far shorter than your 2-3 week runs)
- **GPU VM constraint**: No live migration support — every upgrade requires pod restart
- **Surge capacity**: Fixed GPU reservations likely have NO surge capacity available

## Recommended Upgrade Strategy

### Phase 1: Training Campaign Coordination (2-4 weeks before)

1. **Implement maintenance exclusions** to block all upgrades during active training:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

2. **Schedule upgrade window** between training runs:
- Identify 3-5 day gap between training campaigns
- Coordinate with ML team on checkpoint timing
- Plan for host maintenance duration (~4 hours per node batch)

### Phase 2: Pre-Upgrade Preparation (1 week before)

3. **Stage and validate target environment**:
```bash
# Create small staging node pool at GKE 1.32
gcloud container node-pools create staging-1-32 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --machine-type a3-megagpu-8g \
  --num-nodes 4 \
  --cluster-version 1.32.x \
  --enable-autoscaling --max-nodes 4 --min-nodes 0

# Test TCPXO + training workload compatibility
kubectl apply -f staging-training-job.yaml
# Verify: RDMA topology, inter-node bandwidth, training convergence
```

4. **Verify GPU driver compatibility**:
```bash
# Check new CUDA version in GKE 1.32
kubectl describe nodes staging-node | grep -A5 "nvidia.com/cuda"
# Test model loading, CUDA calls, and throughput match production baseline
```

5. **Configure parallel host maintenance strategy**:
```bash
# Prepare for bulk node maintenance (all nodes updated simultaneously)
# Best for training workloads that can tolerate full restart
```

### Phase 3: Upgrade Execution (During Training Gap)

6. **Control plane upgrade** (safe during active training):
```bash
# CP upgrade doesn't affect running pods
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x

# Verify CP health (10-15 min)
kubectl get pods -n kube-system
```

7. **Checkpoint current training** (if active):
- Trigger training job checkpoint
- Verify checkpoint integrity and resumability
- Scale training workload to zero: `kubectl scale statefulset training-job --replicas=0`

8. **Node pool upgrade with parallel host maintenance**:
```bash
# GPU pools: maxSurge=0 (no surge capacity), maxUnavailable controls speed
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 20  # Start conservative, increase if needed

# Trigger upgrade
gcloud container node-pools upgrade gpu-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x
```

**Critical timing consideration**: With maxUnavailable=20 and GKE's ~20-node parallelism limit, your 512-node pool will take **~26 batches minimum**. At ~4 hours per host maintenance batch, expect **4-5 days total upgrade time**. Plan your training gap accordingly.

### Phase 4: Post-Upgrade Validation

9. **Verify cluster health**:
```bash
# All nodes at target version
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool

# GPU driver and CUDA version
kubectl describe nodes | grep -A3 "nvidia.com/cuda"

# TCPXO networking health
kubectl apply -f tcpxo-validation-job.yaml
```

10. **Resume training with validation soak**:
- Start training from last checkpoint
- Monitor: inter-node communication latency, GPU utilization, training loss convergence
- **Soak period**: Run for 4-8 hours before declaring success
- Keep staging nodes available for 24h as rollback option

11. **Remove maintenance exclusions**:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion training-campaign-protection
```

## Rollback Plan

If TCPXO or training issues arise post-upgrade:

1. **Immediate**: Scale training to staging node pool (GKE 1.31) while debugging
2. **Short-term**: Create new node pool at GKE 1.31, migrate training workload
3. **Long-term**: Contact GKE support for control plane rollback assistance (requires support involvement for minor version downgrades)

## Alternative: Rolling Upgrade Strategy (Lower Risk)

If your training workload supports **partial cluster capacity** during upgrade:

```bash
# Create new node pool at GKE 1.32 (25% of capacity)
gcloud container node-pools create gpu-pool-1-32 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --machine-type a3-megagpu-8g \
  --num-nodes 128 \
  --cluster-version 1.32.x

# Cordon old pool, gradually migrate training workload
kubectl cordon -l cloud.google.com/gke-nodepool=gpu-pool-original
# Scale training to reduced capacity, validate, then complete migration
```

This approach provides a safer rollback path but reduces training capacity during transition.

## Timeline Summary

- **T-4 weeks**: Apply maintenance exclusions, begin staging validation
- **T-1 week**: Confirm TCPXO compatibility, finalize training gap timing
- **T-0**: Control plane upgrade (safe during training)
- **Training gap**: Node pool upgrade (4-5 days)
- **T+1 week**: Training resumed, staging cleanup

## Key Success Metrics

- [ ] TCPXO inter-node bandwidth matches pre-upgrade baseline
- [ ] Training job resumes from checkpoint without convergence issues  
- [ ] GPU utilization maintains 95%+ efficiency across all 4,096 GPUs
- [ ] No CUDA compatibility issues with new driver version
- [ ] Cluster completes upgrade within planned training gap window

This plan prioritizes **training workload continuity** while ensuring **systematic validation** of the critical GPU interconnect functionality your LLM training depends on.