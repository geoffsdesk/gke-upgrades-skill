# GKE Upgrade Plan for Large-Scale GPU Training Cluster

## Executive Summary

Your 512-node H100 cluster requires a **staged upgrade approach** that protects active training runs while maintaining GPUDirect-TCPXO functionality. The key is using maintenance exclusions to pause auto-upgrades during training campaigns, then upgrading during scheduled gaps.

## Current Environment Analysis

- **Cluster**: 512 H100 nodes (A3 Mega, 4,096 GPUs total)
- **Interconnect**: GPUDirect-TCPXO (requires specific GKE versions)
- **Training duration**: 2-3 weeks per campaign
- **Current**: GKE 1.31 → **Target**: GKE 1.32
- **Risk factors**: GPU driver changes, network config, training job interruption

## Critical Considerations for GPU Interconnect

### GPUDirect-TCPXO Version Requirements
- **Current 1.31**: Verify your exact patch version supports TCPXO
- **Target 1.32**: Confirm TCPXO compatibility before proceeding
- **Driver coupling**: GKE auto-installs GPU drivers matching the node image version — this may change CUDA versions and break training framework compatibility

**⚠️ Pre-upgrade validation required**: Test 1.32 in a small staging cluster (8-16 nodes) to verify:
- GPU driver version and CUDA compatibility
- GPUDirect-TCPXO functionality
- Your training framework compatibility

## Recommended Upgrade Strategy

### Phase 1: Control Plane First (Safe)
The control plane can be upgraded independently without affecting running training jobs.

```bash
# Upgrade control plane to 1.32 (does not affect nodes/workloads)
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.32.X-gke.XXXXX

# Verify control plane upgrade
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="value(currentMasterVersion)"
```

### Phase 2: Node Pool Protection During Training
Use maintenance exclusions to prevent node pool auto-upgrades during active training.

```bash
# Block all node upgrades until training campaign completes
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "training-protection-$(date +%Y%m%d)" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time "YYYY-MM-DDTHH:MM:SSZ" \  # Set to training completion + buffer
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### Phase 3: Node Pool Upgrade During Training Gap
Execute node upgrade only during scheduled downtime between training campaigns.

**Recommended strategy for GPU nodes**: `maxSurge=0, maxUnavailable=1`
- H100 nodes likely have fixed reservation capacity
- No surge capacity available for blue-green
- Rolling upgrade with careful batch size control

```bash
# Configure conservative upgrade strategy for GPU pool
gcloud container node-pools update GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

# Execute upgrade during training gap
gcloud container node-pools upgrade GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.32.X-gke.XXXXX
```

**⚠️ Upgrade duration estimate**: With 512 nodes and `maxUnavailable=1`, expect ~25-30 hours for complete node pool upgrade (GKE upgrades ~20 nodes maximum in parallel, but GPU nodes take longer due to driver installation and validation).

## Alternative: Autoscaled Blue-Green for Faster Completion

If you have sufficient H100 reservation capacity (1,024+ nodes total), consider autoscaled blue-green:

```bash
# Requires 2x GPU capacity but minimizes per-node downtime
gcloud container node-pools update GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --enable-autoscaled-blue-green-upgrade
```

This cordons the old pool and auto-scales replacement nodes, but requires doubling your H100 footprint temporarily.

## Multi-Cluster Strategy (Recommended for Production)

For maximum training continuity, consider a **dedicated training cluster** approach:

1. **Training cluster**: Remains on 1.31 with auto-upgrades disabled during campaigns
2. **Staging cluster**: Upgrade to 1.32 first for validation
3. **Inference clusters**: Upgrade during low-traffic windows

```bash
# Training cluster: disable auto-upgrades entirely
gcloud container clusters update TRAINING_CLUSTER \
  --region REGION \
  --add-maintenance-exclusion-name "training-dedicated" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time "2025-12-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

## Pre-Upgrade Validation Checklist

```markdown
- [ ] Staging cluster upgraded to 1.32 and TCPXO functionality verified
- [ ] GPU driver version compatibility confirmed with training framework
- [ ] CUDA version changes documented and tested
- [ ] Training checkpointing working (verify restore from checkpoint)
- [ ] Compact placement policy preserved through node replacement
- [ ] High-MTU VPC configuration survives upgrade
- [ ] Current training campaign completion date confirmed
- [ ] Maintenance exclusion scheduled to protect active training
- [ ] Alternative compute reserved if blue-green approach chosen
```

## Training Job Protection Commands

```bash
# Before upgrade: ensure training jobs have checkpointing enabled
kubectl get pods -l app=training -o jsonpath='{range .items[*]}{.metadata.name}{": "}{.spec.containers[0].env[?(@.name=="CHECKPOINT_ENABLED")]}{"\n"}{end}'

# Create PDB to protect training pods during upgrade
cat <<EOF | kubectl apply -f -
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
spec:
  minAvailable: 100%  # Prevents ANY eviction during upgrade
  selector:
    matchLabels:
      app: training
EOF
```

## Post-Upgrade Validation

```bash
# Verify all nodes upgraded
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool

# Check GPU driver version
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{": "}{.status.nodeInfo.kernelVersion}{"\n"}{end}'

# Verify TCPXO functionality (run small test job)
# Test inter-node GPU communication before launching full training

# Validate compact placement maintained
kubectl describe nodes | grep -A 5 "topology.gke.io/compact-placement-group"
```

## Rollback Plan

If the upgrade breaks TCPXO or training compatibility:

1. **Control plane rollback**: Contact GKE support (minor version downgrades require support)
2. **Node pool rollback**: Create new pool at 1.31, migrate workloads, delete upgraded pool
3. **Training resumption**: Restore from latest checkpoint on stable nodes

## Timeline Recommendation

1. **Week 1**: Control plane upgrade + staging validation
2. **Week 2**: Training campaign completion
3. **Week 3**: Node pool upgrade during training gap
4. **Week 4**: New training campaign on 1.32

This approach protects your current training investment while ensuring a validated path to 1.32 for future campaigns.