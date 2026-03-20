# GKE Upgrade Plan for Large-Scale LLM Training Cluster

**Cluster Profile:**
- Mode: GKE Standard
- Size: 512 H100 GPU nodes (A3 Mega, 8 GPUs each = 4,096 total GPUs)
- Current: GKE 1.29 | Target: GKE 1.30
- Workload: Multi-week LLM training with GPUDirect-TCPXO
- Training duration: 2-3 weeks per run

## Critical Constraints

### 1. GPU Interconnect Compatibility
- **GPUDirect-TCPXO requires GKE 1.27.7-gke.1121000+** — your target 1.30 is compatible
- **A3 Mega networking stack** uses custom high-MTU VPC configuration for RDMA traffic
- **Physical placement policies** ensure nodes are co-located for optimal interconnect performance

### 2. Training Job Protection
- **No mid-run eviction possible** — 2-3 week training runs cannot survive node upgrades
- **GPU VMs do not support live migration** — every node upgrade requires pod restart
- **H100 capacity scarcity** — surge upgrades may fail due to unavailable H100 quota

## Recommended Upgrade Strategy

### Phase 1: Control Plane First (No Workload Impact)

The control plane upgrade is safe — it doesn't affect running training jobs.

```bash
# Verify target version availability
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels)"

# Upgrade control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.30.x-gke.latest

# Verify (wait ~15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Phase 2: Node Pool Strategy - Maintenance Exclusion + Dedicated Pool Approach

**Recommended approach: Split your GPU workload across two node pools**

#### Option A: Immediate Protection (Safest)
```bash
# Apply "no minor or node upgrades" exclusion to protect active training
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-protection-$(date +%Y%m%d)" \
  --add-maintenance-exclusion-start-time "$(date -Iseconds)" \
  --add-maintenance-exclusion-end-time "2025-12-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

This blocks all node upgrades while allowing control plane security patches. Upgrade the GPU nodes during your next scheduled training gap.

#### Option B: Two-Pool Strategy (For Future Runs)
Create separate pools for active training vs. standby/staging:

```bash
# Create dedicated training pool with auto-upgrade disabled
gcloud container node-pools create training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --machine-type a3-megagpu-8g \
  --num-nodes 256 \
  --cluster-version 1.29.x \
  --enable-autoupgrade=false \
  --placement-policy-policy-name YOUR_PLACEMENT_POLICY

# Create staging pool for testing/next run
gcloud container node-pools create staging-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --machine-type a3-megagpu-8g \
  --num-nodes 256 \
  --cluster-version 1.30.x \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

### Phase 3: Validation in Staging Pool

Before upgrading your training nodes, validate the target version:

```bash
# Deploy a test training job on the 1.30 staging pool
kubectl label nodes -l cloud.google.com/gke-nodepool=staging-pool training=staging
```

**Critical validations:**
- GPUDirect-TCPXO interconnect performance (run NCCL tests)
- CUDA version compatibility with your training framework
- High-MTU RDMA networking still functional
- Compact placement policy behavior unchanged

### Phase 4: Production Training Pool Upgrade (During Training Gap)

**Wait for current training run to complete naturally, then:**

```bash
# Remove maintenance exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "training-protection-YYYYMMDD"

# Configure conservative upgrade settings for H100 pool
gcloud container node-pools update training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

# Upgrade the training pool
gcloud container node-pools upgrade training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30.x-gke.latest
```

**Why `maxSurge=0, maxUnavailable=1`?**
- H100 quota is extremely scarce — surge upgrades likely to fail
- Drains one node at a time, creates replacement, then moves to next
- Slower but doesn't require extra H100 capacity
- For 512 nodes, expect 24-48 hours total upgrade time

## Pre-Upgrade Checklist

```
Large-Scale GPU Training Cluster Upgrade Checklist

Critical Validation
- [ ] Current training run completion timeline: ___ (upgrade only during gaps)
- [ ] GPUDirect-TCPXO compatibility confirmed: GKE 1.30 ≥ required 1.27.7-gke.1121000
- [ ] H100 node quota available for surge (if using surge upgrade): ___/512 nodes
- [ ] Compact placement policy verified in staging
- [ ] High-MTU VPC configuration documented and tested
- [ ] Training framework + CUDA version compatibility with target GKE 1.30 tested

Training Job Protection
- [ ] Checkpointing enabled and tested (can resume after node restart)
- [ ] Current training run progress saved/documented
- [ ] Maintenance exclusion applied: "no minor or node upgrades"
- [ ] PDBs configured to block eviction of active training pods
- [ ] Training pool isolated from auto-upgrade (separate from inference/staging pools)

Infrastructure Readiness
- [ ] Staging/test pool created at target version for validation
- [ ] NCCL performance tests completed on 1.30 staging environment
- [ ] GPU driver version change documented (1.29→1.30 may change CUDA)
- [ ] Reservation headroom verified (if using committed use discounts)
- [ ] Network performance baseline captured pre-upgrade

Operational
- [ ] Upgrade scheduled during training gap (no active multi-week runs)
- [ ] Rollback plan: create new pool at 1.29, migrate workloads
- [ ] Monitoring for GPU interconnect performance metrics
- [ ] On-call team aware of upgrade timeline (24-48h for 512 nodes)
```

## Post-Upgrade Validation

```bash
# Verify all nodes upgraded
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# Check GPU driver version
kubectl get nodes -o json | jq -r '.items[0].status.nodeInfo.kernelVersion'

# Test GPUDirect-TCPXO performance
kubectl apply -f nccl-test-job.yaml  # Deploy NCCL all-reduce test

# Verify placement policy
kubectl describe nodes -l cloud.google.com/gke-nodepool=training-pool | grep topology.gke.io

# Network performance validation
# Run bandwidth tests between nodes to confirm RDMA performance
```

## Troubleshooting GPU-Specific Issues

### Upgrade Stalls Due to H100 Capacity
```bash
# Check for quota/capacity errors
kubectl get events -A --field-selector reason=FailedScheduling | grep H100

# Switch to maxUnavailable mode if surge fails
gcloud container node-pools update training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

### GPUDirect Performance Degradation
- Verify high-MTU VPC configuration survived the upgrade
- Check that nodes landed in the same compact placement group
- Validate GPU driver version didn't regress RDMA capabilities
- Test with `nvidia-smi topo -m` to confirm GPU topology

## Timeline Recommendation

1. **Week 1**: Control plane upgrade + staging pool validation
2. **Week 2-4**: Wait for current training run completion
3. **Week 5**: Training pool upgrade during gap
4. **Week 6**: New training run on upgraded infrastructure

This approach protects your active training investment while ensuring a safe, validated upgrade path.