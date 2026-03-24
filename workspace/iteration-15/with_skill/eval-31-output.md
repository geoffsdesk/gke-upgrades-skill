# GKE Upgrade Plan: Large-Scale LLM Training Cluster (512 H100 Nodes)

## Executive Summary

Your 512-node H100 training cluster requires special handling due to:
- **2-3 week training runs** that cannot tolerate interruption
- **GPUDirect-TCPXO networking** with strict version requirements
- **A3 Mega compact placement** that must be preserved
- **Massive scale** (512 nodes = ~26 batches at GKE's 20-node parallelism limit)

**Recommended strategy:** Use maintenance exclusions to protect active training, then execute upgrades during scheduled gaps with parallel host maintenance for maximum speed.

## Current Environment Assessment

```bash
# Verify current state
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Check GPUDirect-TCPXO compatibility
kubectl get nodes -o jsonpath='{.items[0].status.nodeInfo.kernelVersion}'
# Verify 1.31 → 1.32 maintains TCPXO support for A3 Mega

# Check training job status
kubectl get pods -l app=training -A
```

## Version Compatibility Analysis

✅ **GKE 1.31 → 1.32 upgrade path:**
- Both versions support GPUDirect-TCPXO on A3 Mega machines
- No breaking changes to GPU driver stack
- Kubernetes API changes are backward compatible for training workloads

⚠️ **Critical considerations:**
- A3 Mega nodes do NOT support surge capacity (fixed GPU reservations)
- Compact placement groups must be preserved during upgrade
- RDMA topology cannot be broken mid-training

## Upgrade Strategy: Maintenance Exclusions + Parallel Host Maintenance

### Phase 1: Protect Active Training (Immediate)

```bash
# Block all node upgrades during active training campaign
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-protection-$(date +%Y%m)" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Verify exclusion is active
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(maintenancePolicy.window.maintenanceExclusions)"
```

**This exclusion will:**
- ✅ Block node pool upgrades that would disrupt training
- ✅ Still allow control plane security patches
- ✅ Automatically track version EoS and renew when 1.32 is adopted

### Phase 2: Control Plane Upgrade (Can do immediately)

The control plane can be upgraded without affecting running training pods:

```bash
# Control plane upgrade (safe during active training)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.X-gke.LATEST

# Monitor (no workload impact)
watch 'gcloud container clusters describe CLUSTER_NAME --zone ZONE --format="value(currentMasterVersion)"'
```

**Why this is safe:**
- Regional cluster maintains CP availability during upgrade
- Running pods continue training uninterrupted
- No node-level changes occur

### Phase 3: Node Upgrade During Training Gap (Scheduled)

**Timing:** Execute during your next planned training break (between runs).

**Strategy:** Parallel host maintenance for fastest completion (~4-6 hours vs 3-4 days with rolling)

```bash
# Step 1: Scale down training workload (checkpoint first!)
kubectl scale deployment training-workload --replicas=0

# Step 2: Apply parallel maintenance to ALL nodes simultaneously
kubectl label nodes -l cloud.google.com/gke-nodepool=gpu-pool \
  cloud.google.com/perform-maintenance=true

# Step 3: Monitor maintenance progress
kubectl get nodes -o custom-columns=NAME:.metadata.name,STATUS:.status.conditions[-1].type,MAINTENANCE:.metadata.labels['cloud\.google\.com/perform-maintenance']
```

**Parallel maintenance timeline:**
- ~4 hours for all 512 nodes to complete host maintenance
- Nodes maintain compact placement (same placement group)
- GPU interconnect topology preserved

**Alternative: Rolling upgrade (if you can't coordinate training stops):**
```bash
# Remove the maintenance exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "training-protection-$(date +%Y%m)"

# Configure drain-first strategy (no surge capacity available)
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4

# This will take 3-4 days for 512 nodes (26 batches × 20-node limit)
```

## GPU-Specific Upgrade Considerations

### A3 Mega Constraint Matrix

| Factor | Impact | Mitigation |
|--------|--------|------------|
| **No surge capacity** | Can't use standard rolling upgrade | Use `maxUnavailable` mode or parallel maintenance |
| **Compact placement** | Nodes must stay in same placement group | Verify replacement nodes land correctly |
| **TCPXO networking** | Version-sensitive interconnect | Test 1.32 compatibility in staging first |
| **2-3 week jobs** | Cannot tolerate mid-job eviction | Maintenance exclusions during training |

### Recommended Node Pool Settings

```bash
# For rolling upgrade (if parallel maintenance isn't feasible)
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2
  # Conservative: 2 nodes at a time to minimize blast radius

# Check GPU reservation headroom (should show 0 available)
gcloud compute reservations describe GPU_RESERVATION_NAME --zone ZONE
```

## Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist: Large-Scale LLM Training

Training Protection
- [ ] Maintenance exclusion "no_minor_or_node_upgrades" active
- [ ] Current training run checkpointed and can resume
- [ ] Training gap identified for node upgrades (minimum 8-hour window)
- [ ] Training team notified of upgrade schedule

GPU Infrastructure  
- [ ] GPUDirect-TCPXO compatibility verified for GKE 1.32
- [ ] Compact placement policy active on node pool
- [ ] A3 Mega reservation has 0 surge capacity (expected)
- [ ] RDMA/high-MTU VPC networking tested in staging
- [ ] GPU driver compatibility confirmed (auto-installed by GKE)

Scale Considerations
- [ ] 512 nodes = ~26 batches at 20-node parallelism (3-4 day rolling upgrade)
- [ ] Parallel host maintenance preferred (4-6 hour total time)
- [ ] Monitoring configured for large-scale upgrade tracking
- [ ] Node upgrade concurrency set to maxUnavailable=2-4 (conservative)

Validation Environment
- [ ] Staging cluster tested 1.31→1.32 upgrade with same GPU setup
- [ ] Training framework compatibility verified on 1.32
- [ ] GPUDirect-TCPXO performance benchmarked post-upgrade
```

## Rollback Plan

**Control plane rollback:** Not recommended once 1.32 is adopted. Coordinate with GKE support if critical issues arise.

**Node rollback (if issues during upgrade):**
```bash
# Create new pool at 1.31 (emergency only)
gcloud container node-pools create gpu-pool-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --node-version 1.31.X-gke.VERSION \
  --machine-type a3-megagpu-8g \
  --placement-policy-policy-name PLACEMENT_POLICY \
  --reservation-affinity consume,GPU_RESERVATION_NAME
```

## Timeline

1. **Immediate (Day 0):** Apply maintenance exclusion, upgrade control plane
2. **Next training gap (Days 7-21):** Execute node upgrade with parallel maintenance
3. **Post-upgrade (Day +1):** Validate GPU interconnect, restart training

**Total disruption:** ~4-6 hours (parallel maintenance) vs 0 hours (wait for natural training break)

This approach protects your multi-week training investment while ensuring you stay current with GKE versions. The key insight is using maintenance exclusions as a surgical tool rather than avoiding upgrades entirely.