# GKE Upgrade Plan: Large-Scale AI Training Cluster (H100/A3 Mega)

**Cluster Profile:**
- **Size:** 512 H100 nodes (A3 Mega, 8 GPUs each = 4,096 GPUs total)
- **Interconnect:** GPUDirect-TCPXO (high-performance GPU networking)
- **Workload:** 2-3 week LLM training runs
- **Current:** GKE 1.31 → **Target:** GKE 1.32
- **Critical constraints:** Active training protection + GPU interconnect preservation

## Executive Summary

**Recommended approach:** Maintenance exclusion during active training + dedicated upgrade window between training campaigns. This cluster size and workload sensitivity require careful timing rather than mid-training upgrades.

## Version Compatibility Assessment

✅ **GPUDirect-TCPXO compatibility:** GKE 1.32 maintains support for GPUDirect-TCPXO on A3 Mega instances
✅ **Version path:** 1.31→1.32 is a single minor version jump (no intermediate steps needed)
✅ **GPU driver:** GKE 1.32 will auto-install compatible CUDA drivers for H100

**⚠️ Critical validation required:** Deploy a small staging A3 Mega cluster at GKE 1.32, run representative training workloads, and verify:
- GPUDirect-TCPXO topology detection
- Inter-node bandwidth benchmarks (nccl-tests)
- Training throughput matches baseline
- CUDA compatibility with your training framework

## Upgrade Strategy: Maintenance Exclusion + Scheduled Window

### Phase 1: Protect Active Training (Immediate)

```bash
# Block all node upgrades during active training campaign
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time "YYYY-MM-DDTHH:MM:SSZ" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**Key points:**
- This blocks node pool upgrades but allows control plane security patches
- Control plane upgrade (1.31→1.32) has minimal impact on running training workloads
- Maximum exclusion duration: until version 1.31 reaches End of Support
- Plan upgrade window for the gap between current and next training campaign

### Phase 2: Control Plane Upgrade (Low Risk)

**Timing:** Can be done during active training with minimal impact
**Duration:** ~15 minutes, no workload interruption

```bash
# Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.32.x-gke.LATEST

# Verify control plane health
kubectl get pods -n kube-system
kubectl get nodes  # Should show Ready status maintained
```

**Why this is safe during training:** Regional clusters maintain API availability during control plane upgrades. Training workloads continue running uninterrupted.

### Phase 3: Node Pool Upgrade (High Risk - Requires Training Gap)

**Critical:** Only perform during scheduled maintenance window between training campaigns.

**Recommended strategy:** Parallel maintenance strategy (all nodes updated simultaneously)
- **Rationale:** Training workloads require all 512 nodes anyway—partial capacity is useless
- **Duration:** ~4 hours for host maintenance completion
- **Zero surge capacity:** A3 Mega reservations are typically fixed with no surge headroom

#### Pre-upgrade checklist:
```bash
# Verify no active training jobs
kubectl get pods -l job-type=training -A

# Confirm GPU reservation headroom (likely zero for A3 Mega)
gcloud compute reservations describe RESERVATION_NAME --zone ZONE

# Checkpoint any in-progress work
# [Workload-specific checkpointing commands]

# Scale training workloads to zero
kubectl scale deployment TRAINING_DEPLOYMENT --replicas=0
```

#### Node upgrade with parallel maintenance:
```bash
# Configure for GPU pools - maxUnavailable is the primary lever
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 20

# Apply maintenance label to trigger host maintenance on all GPU nodes
kubectl label nodes -l cloud.google.com/gke-nodepool=gpu-pool \
  cloud.google.com/perform-maintenance=true

# Monitor maintenance progress
watch 'kubectl get nodes -o wide | grep -E "NAME|NotReady|Ready"'
```

**Expected timeline:**
- Maintenance label applied: immediate
- Host maintenance completion: ~4 hours
- Node registration and readiness: additional 30 minutes
- **Total window:** ~5 hours

## Critical Validations

### GPU Interconnect Verification
```bash
# After upgrade, verify GPUDirect-TCPXO topology
kubectl exec -it training-pod-test -- nvidia-smi topo -m

# Run NCCL bandwidth test across nodes
kubectl apply -f nccl-test-job.yaml  # Multi-node NCCL all-reduce test

# Verify compact placement preserved
kubectl get nodes -o wide -l cloud.google.com/gke-nodepool=gpu-pool
```

### Performance Baseline Validation
```bash
# Deploy representative training workload
kubectl apply -f training-validation-job.yaml

# Compare throughput metrics:
# - Tokens/second/GPU
# - Inter-node communication bandwidth
# - Memory bandwidth utilization
# - Training loss convergence (first few steps)
```

## Rollback Strategy

**If GPU interconnect breaks post-upgrade:**
1. **Immediate:** Scale training workloads to zero
2. **Create new node pool** at GKE 1.31 (can't downgrade existing pool in-place)
3. **Migrate workloads** to new pool with validated configuration
4. **Delete upgraded pool** after confirming workload health

```bash
# Emergency rollback - create new pool at previous version
gcloud container node-pools create gpu-pool-rollback \
  --cluster CLUSTER_NAME \
  --region REGION \
  --machine-type a3-megagpu-8g \
  --num-nodes 512 \
  --cluster-version 1.31.x-gke.PREVIOUS \
  --placement-type COMPACT \
  --max-pods-per-node 15
```

## Timeline and Coordination

### Immediate (Today)
- [ ] Apply maintenance exclusion to protect current training
- [ ] Set up staging cluster for 1.32 validation
- [ ] Schedule upgrade window between training campaigns

### Pre-upgrade Window (24-48h before)
- [ ] Complete staging validation with representative workloads
- [ ] Checkpoint any active training state
- [ ] Confirm no critical training runs scheduled during window
- [ ] Alert stakeholders of maintenance window

### Upgrade Window (5-hour block)
- [ ] Scale training to zero
- [ ] Upgrade control plane (low risk, can do earlier)
- [ ] Apply parallel maintenance to all GPU nodes
- [ ] Monitor progress and validate interconnect
- [ ] Performance testing before resuming production training

### Post-upgrade
- [ ] Remove maintenance exclusion
- [ ] Resume training workloads
- [ ] Monitor performance baselines for 24-48h
- [ ] Document lessons learned

## Risk Mitigation

**Compact placement preservation:** With 512 nodes, verify replacement nodes land in the same placement groups to maintain RDMA topology. If placement breaks, training performance will degrade severely.

**Reservation management:** A3 Mega instances are scarce. Coordinate with your Google Cloud account team to ensure replacement capacity is guaranteed during the maintenance window.

**Alternative: Extended support:** Consider enrolling in Extended release channel to delay forced upgrades and get up to 24 months on 1.31, buying time to align upgrades with natural training campaign gaps.

**Monitoring setup:** Configure alerts for GPU utilization drops, NCCL timeout errors, and training throughput degradation to catch interconnect issues immediately.

This approach prioritizes workload protection while ensuring your cluster stays current with security patches and feature updates. The key is aligning disruptive node upgrades with your natural training campaign schedule.