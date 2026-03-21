# GKE Upgrade Plan: Large-Scale LLM Training Cluster (512 H100 Nodes)

## Environment Assessment

- **Cluster**: Standard mode, 512 A3 Mega nodes (4,096 H100 GPUs total)
- **Current version**: GKE 1.31 → **Target**: 1.32
- **Critical constraint**: Active 2-3 week training runs cannot be interrupted
- **Networking**: GPUDirect-TCPXO (requires specific GKE versions + network config)

## Executive Summary: Two-Phase Upgrade Strategy

Given your active training workload, I recommend a **two-phase approach**:

1. **Phase 1**: Upgrade control plane only, keep nodes on 1.31
2. **Phase 2**: Upgrade GPU nodes during next scheduled training gap

This protects your current training run while advancing the control plane for security patches.

## Version Compatibility Check

```bash
# Verify 1.32 availability in your channel
gcloud container get-server-config --zone ZONE --format="yaml(channels)"

# Check GPUDirect-TCPXO compatibility
# Confirm 1.32 maintains GPUDirect-TCPXO support for A3 Mega
# (This requires checking GKE release notes - TCPXO has strict version requirements)
```

⚠️ **Critical**: Before proceeding, verify in GKE 1.32 release notes that GPUDirect-TCPXO remains supported. A3 Mega + TCPXO has narrow compatibility windows.

## Phase 1: Control Plane Upgrade (Safe During Training)

### 1.1 Pre-flight Setup

```bash
# Set maintenance exclusion to block node upgrades during training
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-run-protection" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time "2024-MM-DDTHH:MM:SSZ" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

This blocks node pool upgrades while allowing control plane patches.

### 1.2 Control Plane Upgrade

```bash
# Upgrade control plane only (nodes stay on 1.31)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.X-gke.XXXXX
```

**Impact**: Control plane upgrade typically takes 10-15 minutes with minimal disruption. Your training pods continue running on 1.31 nodes.

### 1.3 Post-CP Validation

```bash
# Verify control plane version
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"

# Confirm nodes still on 1.31 (protected by exclusion)
kubectl get nodes -o wide | head -10

# Check training jobs unaffected
kubectl get pods -n TRAINING_NAMESPACE | grep Running
```

## Phase 2: Node Pool Upgrade (During Training Gap)

### 2.1 Timing Strategy

**Wait for natural training gap** (between runs) to upgrade nodes. This avoids forced eviction of multi-week jobs.

### 2.2 GPU Node Pool Upgrade Strategy

For your 512 H100 nodes, recommend **auto-scale blue-green upgrade**:

```bash
# Configure auto-scale blue-green (creates full replacement pool automatically)
gcloud container node-pools update GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscale \
  --enable-autoupgrade \
  --node-pool-upgrade-strategy blue-green
```

**Why blue-green for GPU pools**:
- H100 surge capacity is extremely scarce - surge upgrades often stall
- Blue-green provisions the full 512-node replacement pool upfront
- Instant rollback capability if GPU interconnect breaks
- No partial capacity states that could fragment your training topology

### 2.3 Node Upgrade Execution

```bash
# Remove maintenance exclusion when ready to upgrade nodes
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "training-run-protection"

# Trigger blue-green node upgrade
gcloud container node-pools upgrade GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.XXXXX
```

**Timeline expectation**: 512-node blue-green upgrade will take 4-8 hours depending on node provisioning speed for A3 Mega.

### 2.4 Post-Upgrade Validation

**Critical GPU interconnect tests**:

```bash
# Verify all nodes upgraded
kubectl get nodes -o wide | grep 1.32

# Test GPUDirect-TCPXO functionality
# Run a small multi-node NCCL test to verify interconnect
kubectl apply -f nccl-test-job.yaml

# Verify custom high-MTU VPC config intact
# Check that your RDMA networking survived the upgrade
ip link show | grep mtu
```

**Compact placement policy check**:
```bash
# Verify nodes still in same placement group
gcloud compute instances list --filter="name~'gke-CLUSTER.*'" \
  --format="table(name,zone,resourcePolicies.list())"
```

## Rollback Plan

If GPU interconnect breaks after node upgrade:

```bash
# Blue-green allows instant rollback
gcloud container node-pools rollback GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE
```

This restores the previous node pool within ~15 minutes.

## Risk Mitigation

### Training Job Protection
- **Checkpointing**: Ensure training jobs save checkpoints frequently (every few hours)
- **Pod restart tolerance**: Configure training frameworks to resume from latest checkpoint
- **Preemption handling**: Use node selectors to keep training on stable nodes

### GPU-Specific Considerations
- **Driver compatibility**: GKE 1.32 may install different CUDA drivers - test in staging first
- **Reservation interaction**: Ensure your H100 reservation covers the blue-green replacement pool
- **Network topology**: A3 Mega placement can be sensitive to node recreation

## Alternative: Extended Channel Migration

Consider migrating to **Extended channel** for maximum control:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

**Benefits**:
- Up to 24 months support per version
- Manual control over minor upgrades (only patches auto-apply)
- Better alignment with long training cycles

## Monitoring During Upgrade

```bash
# Watch node pool status
watch 'gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE'

# Monitor training job health
watch 'kubectl get pods -n TRAINING_NAMESPACE -o wide'

# Check GPU utilization
kubectl top nodes --selector=cloud.google.com/gke-accelerator=nvidia-h100-mega-80gb
```

## Summary Timeline

1. **Now**: Apply maintenance exclusion, upgrade control plane (15 min)
2. **During training**: Control plane on 1.32, nodes protected on 1.31
3. **Next training gap**: Remove exclusion, blue-green node upgrade (4-8 hours)
4. **Post-upgrade**: Validate GPU interconnect, resume training

This approach protects your current multi-week training investment while advancing to 1.32 for security and feature benefits.

Would you like me to adjust this plan based on your specific training schedule or provide the detailed runbook commands for your environment?