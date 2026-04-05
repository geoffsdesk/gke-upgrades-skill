# GKE Large-Scale LLM Training Cluster Upgrade Plan

## Executive Summary

**Critical constraints identified:**
- 512 H100 nodes (4,096 GPUs total) with 2-3 week training runs
- GPUDirect-TCPXO dependency requires careful version validation
- Fixed GPU reservations = zero surge capacity available
- Training workloads cannot tolerate mid-job eviction

**Recommended approach:** Maintenance exclusion + planned training gap upgrade using AI Host Maintenance with parallel strategy.

---

## Current Environment Analysis

- **Cluster:** GKE Standard 1.31 → 1.32 upgrade
- **Scale:** 512 A3 Mega nodes (8x H100 each = 4,096 GPUs)
- **Interconnect:** GPUDirect-TCPXO (requires GKE 1.27.7-gke.1121000+, so 1.32 is compatible)
- **Workload:** Multi-week LLM training (cannot checkpoint frequently)
- **Constraint:** Fixed GPU reservation = no surge capacity for traditional upgrades

---

## Phase 1: Immediate Protection (Apply Now)

### Block auto-upgrades during active training

```bash
# Apply "no minor or node upgrades" exclusion to prevent auto-upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Verify exclusion is active
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy.window.maintenanceExclusions)"
```

**What this does:** Prevents both control plane minor upgrades AND node pool upgrades while allowing critical security patches on the control plane. Tracks automatically until 1.31 reaches End of Support.

---

## Phase 2: Pre-Upgrade Validation (During Next Training Gap)

### Test GPUDirect-TCPXO compatibility with 1.32

```bash
# Create a small staging node pool with target version
gcloud container node-pools create staging-a3-test \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --machine-type a3-megagpu-8g \
  --accelerator type=nvidia-h100-mega-80gb,count=8 \
  --num-nodes 4 \
  --cluster-version 1.32.x-gke.LATEST \
  --placement-type COMPACT \
  --enable-ip-alias \
  --network-performance-config total-egress-bandwidth-tier=TIER_1

# Deploy test training workload to validate:
# 1. GPUDirect-TCPXO functionality
# 2. RDMA topology preservation
# 3. Driver compatibility (CUDA version changes)
# 4. Compact placement group integrity
```

**Critical validation checklist:**
- [ ] GPUDirect-TCPXO detection: `nvidia-smi topo -m`
- [ ] RDMA connectivity between test nodes
- [ ] CUDA version compatibility with training framework
- [ ] Placement group co-location maintained
- [ ] Network MTU settings preserved (9000 for RDMA)

---

## Phase 3: Production Upgrade Strategy

### Option A: AI Host Maintenance with Parallel Strategy (Recommended)

**Best for:** Training runs that can checkpoint at natural boundaries (between epochs/phases)

```bash
# Step 1: Checkpoint current training run at epoch boundary
# (Application-specific - trigger via your training orchestrator)

# Step 2: Scale training workload to zero
kubectl scale deployment llm-training --replicas=0

# Step 3: Apply maintenance label to ALL nodes simultaneously
kubectl label nodes -l node.kubernetes.io/instance-type=a3-megagpu-8g \
  cloud.google.com/perform-maintenance=true

# Step 4: Wait for host maintenance to complete (~4 hours)
# Monitor progress:
watch 'kubectl get nodes -o custom-columns="NAME:.metadata.name,STATUS:.status.conditions[?(@.type==\"Ready\")].status,VERSION:.status.nodeInfo.kubeletVersion" -l node.kubernetes.io/instance-type=a3-megagpu-8g'
```

**Timeline:** ~4-6 hours total downtime (parallel maintenance across all nodes)

### Option B: Scheduled Training Gap Upgrade

**Best for:** Training campaigns with natural breaks between experiments

1. **Plan upgrade during scheduled training gap** (between model experiments)
2. **Use cluster-level "no upgrades" exclusion** to control exact timing:

```bash
# Schedule upgrade window during training gap
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-name "upgrade-window" \
  --add-maintenance-exclusion-start TRAINING_END_TIME \
  --add-maintenance-exclusion-end UPGRADE_WINDOW_END \
  --add-maintenance-exclusion-scope no_upgrades

# Manually trigger upgrade at planned time
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.LATEST

# Then upgrade node pools with maxUnavailable strategy
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4

gcloud container node-pools upgrade POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.LATEST
```

---

## Phase 4: Post-Upgrade Validation

### Critical validation for LLM training environment

```bash
# 1. Verify all nodes at target version
kubectl get nodes -o custom-columns="NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion"

# 2. Validate GPUDirect-TCPXO topology
kubectl debug node/NODE_NAME -it --image=gcr.io/gke-release/nvidia-driver-installer:latest -- nvidia-smi topo -m

# 3. Test RDMA connectivity between nodes
# Deploy test workload that validates inter-node GPU communication

# 4. Verify compact placement preserved
gcloud compute instances describe INSTANCE_NAME --zone ZONE --format="value(scheduling.nodeAffinities)"

# 5. Confirm GPU driver version and CUDA compatibility
kubectl debug node/NODE_NAME -it --image=gcr.io/gke-release/nvidia-driver-installer:latest -- nvidia-smi
```

### Resume training operations

```bash
# Re-enable normal maintenance policy
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-protection-ongoing" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Scale training workload back up
kubectl scale deployment llm-training --replicas=REPLICA_COUNT
```

---

## Risk Mitigation

### GPU-specific risks and mitigations:

1. **Placement group fragmentation**
   - **Risk:** Surge/replacement nodes may not land in same placement group
   - **Mitigation:** Use parallel host maintenance instead of rolling upgrades

2. **RDMA topology changes**
   - **Risk:** Network topology changes break GPUDirect-TCPXO
   - **Mitigation:** Validate in staging first, verify post-upgrade

3. **CUDA driver version changes**
   - **Risk:** GKE auto-installs new GPU drivers, potentially changing CUDA version
   - **Mitigation:** Test training framework compatibility in staging pool

4. **Training data checkpoint corruption**
   - **Risk:** Abrupt termination corrupts training state
   - **Mitigation:** Only upgrade at natural checkpoint boundaries

### Rollback plan:

```bash
# If GPUDirect-TCPXO fails post-upgrade, create emergency rollback pool
gcloud container node-pools create emergency-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --machine-type a3-megagpu-8g \
  --accelerator type=nvidia-h100-mega-80gb,count=8 \
  --cluster-version 1.31.x-gke.PREVIOUS \
  --num-nodes 512 \
  --placement-type COMPACT

# Migrate training workload to rollback pool
# Delete problematic 1.32 pool after validation
```

---

## Timeline Recommendation

1. **Week 1:** Apply maintenance exclusion protection (immediate)
2. **Week 2-3:** Current training run completes
3. **Week 4:** Staging validation with 4-node test pool
4. **Week 5:** Production upgrade during planned training gap
5. **Week 6:** Resume training operations on 1.32

**Total training downtime:** 4-6 hours (parallel host maintenance approach)

---

## Key Considerations for Future Upgrades

1. **Establish maintenance exclusion as standard practice** during active training
2. **Build upgrade validation into training pipeline** (staging clusters)
3. **Coordinate upgrades with training campaign scheduling**
4. **Consider Extended release channel** for maximum upgrade control (up to 24 months support)
5. **Monitor GKE release notes** for GPUDirect-TCPXO compatibility changes

This approach minimizes training disruption while ensuring GPU interconnect compatibility is validated before production deployment.