# LLM Training Cluster Upgrade Plan: GKE 1.31 → 1.32

## Executive Summary

For your 512-node H100 cluster with active 2-3 week training runs, this upgrade requires **careful timing and specialized handling** due to GPUDirect-TCPXO requirements and training job protection. The key is using maintenance exclusions to protect active training, then upgrading during natural gaps between runs.

## Cluster Profile Analysis

- **Scale**: 512 H100 GPU nodes (A3 Mega) = 4,096 GPUs total
- **Workload**: Multi-week LLM training (disruption-intolerant)
- **Network**: GPUDirect-TCPXO (requires GKE 1.27.7-gke.1121000+ ✓)
- **Constraint**: No surge capacity available (fixed GPU reservations)
- **Upgrade duration estimate**: 3-5 days for full cluster (512 nodes ÷ 20 max concurrent = ~26 batches minimum)

## Pre-Upgrade Validation Checklist

```
Pre-Upgrade Checklist - LLM Training Cluster
- [ ] Cluster: ___ | Current: 1.31 | Target: 1.32 | Channel: ___
- [ ] Active training status: RUNNING / CHECKPOINTING / IDLE

GPUDirect-TCPXO Compatibility
- [ ] GKE 1.32 supports GPUDirect-TCPXO for A3 Mega (verify in staging)
- [ ] Custom high-MTU VPC configuration documented
- [ ] Compact placement policy verified in staging cluster
- [ ] RDMA topology test completed on 1.32 staging environment

Training Job Protection
- [ ] Current training run completion ETA: ___
- [ ] Checkpoint frequency confirmed: every ___ hours
- [ ] Latest checkpoint location and restore tested
- [ ] "No minor or node upgrades" exclusion applied during active training

Infrastructure Readiness
- [ ] GPU reservation headroom checked (expect 0 surge capacity)
- [ ] Node pool upgrade strategy: maxSurge=0, maxUnavailable=1-4
- [ ] Maintenance window: 48+ hour block during training gap
- [ ] Staging cluster at 1.32 validated with representative workload
```

## Upgrade Strategy: Training-Aware Timing

### Phase 1: Protect Active Training (Immediate)

```bash
# Apply maintenance exclusion to block ALL upgrades during active training
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "protect-training-run" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time "YYYY-MM-DDTHH:MM:SSZ" \  # Set to training completion + buffer
  --add-maintenance-exclusion-scope no_upgrades
```

**Critical**: This 30-day exclusion prevents auto-upgrades from interrupting your training. Chain multiple exclusions if needed, but monitor security patch accumulation.

### Phase 2: Staging Validation (Parallel)

Create a smaller A3 Mega staging cluster to validate:

```bash
# Create staging cluster with same network config
gcloud container clusters create staging-h100-132 \
  --region REGION \
  --cluster-version 1.32.x-gke.xxxx \
  --machine-type a3-megagpu-8g \
  --num-nodes 8 \
  --enable-gvnic \
  --enable-ip-alias \
  --network NETWORK_NAME \
  --subnetwork SUBNET_NAME \
  --placement-type COMPACT \
  --placement-policy-name PLACEMENT_POLICY_NAME
```

**Validation tests**:
1. Deploy representative training workload (smaller model)
2. Verify GPUDirect-TCPXO connectivity between nodes
3. Confirm RDMA topology and bandwidth
4. Test checkpoint/restore cycle
5. Monitor for any GPU driver compatibility issues

### Phase 3: Upgrade During Training Gap (Planned Window)

**Timing**: Schedule during natural gap between training runs (post-checkpoint, pre-next-run).

**Pre-upgrade steps**:
```bash
# 1. Ensure training job is cleanly stopped and checkpointed
kubectl delete job TRAINING_JOB_NAME  # Graceful termination

# 2. Verify no training pods remain
kubectl get pods -A | grep -v Running | grep -v Completed

# 3. Remove maintenance exclusion to allow upgrade
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --remove-maintenance-exclusion-name "protect-training-run"

# 4. Configure GPU-specific upgrade settings
gcloud container node-pools update gpu-nodepool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2
```

**Upgrade execution**:
```bash
# Control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.32.x-gke.xxxx

# Wait for control plane (~15 minutes)
# Then node pools
gcloud container node-pools upgrade gpu-nodepool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.32.x-gke.xxxx
```

**Monitor progress** (expect 3-5 days total):
```bash
# Track upgrade batches
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "1.31|1.32"'

# Monitor for GPU driver issues
kubectl get events -A --field-selector type=Warning | grep -i gpu
```

### Phase 4: Post-Upgrade Validation

```bash
# Verify all nodes upgraded
kubectl get nodes -o wide | grep -v 1.32

# Check GPU driver status
kubectl get nodes -o json | jq '.items[] | {name: .metadata.name, gpu_driver: .status.nodeInfo.kubeletVersion}'

# Test GPUDirect-TCPXO connectivity
# Deploy test multi-node GPU communication workload
kubectl apply -f gpu-interconnect-test.yaml

# Verify RDMA topology preserved
kubectl exec -it test-pod -- nvidia-smi topo -m
```

## GPU-Specific Upgrade Considerations

### Node Pool Settings for H100 Fixed Reservations

```bash
# Configure for zero surge capacity scenario
gcloud container node-pools update gpu-nodepool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2  # Adjust based on training sensitivity
```

**Key settings**:
- `maxSurge=0`: No extra GPU nodes needed (fixed reservation)
- `maxUnavailable=1-4`: Primary speed lever for GPU pools
- **Trade-off**: Higher `maxUnavailable` = faster upgrade but more capacity loss during drain

### GPUDirect-TCPXO Preservation

**Critical checks**:
1. **Custom VPC MTU**: Verify high-MTU network config survives upgrade
2. **Compact placement**: Ensure replacement nodes land in same placement group
3. **RDMA topology**: Test inter-node GPU communication post-upgrade

**If RDMA breaks post-upgrade**:
```bash
# Check placement group status
gcloud compute resource-policies describe PLACEMENT_POLICY_NAME --region REGION

# Verify node placement
kubectl get nodes -o json | jq '.items[] | {name: .metadata.name, zone: .metadata.labels["topology.kubernetes.io/zone"]}'
```

## Training Job Protection Strategy

### Checkpoint Before Upgrade

```bash
# Trigger immediate checkpoint (if training framework supports)
kubectl exec -it training-pod -- python save_checkpoint.py --path /checkpoints/pre-upgrade

# Verify checkpoint integrity
kubectl exec -it training-pod -- python validate_checkpoint.py --path /checkpoints/pre-upgrade
```

### Extended Maintenance Exclusion (if needed)

For consecutive training campaigns, use persistent exclusions:

```bash
# "No minor or node upgrades" exclusion (tracks EoS automatically)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

This blocks disruptive upgrades while allowing control plane security patches.

## Timeline & Risk Mitigation

### Recommended Timeline

- **Week 1**: Apply maintenance exclusion, create staging cluster
- **Week 2**: Validate 1.32 in staging with GPUDirect-TCPXO tests
- **Week 3-4**: Monitor current training run completion
- **Training gap** (48-72h window): Execute upgrade
- **Week 5**: Resume training on upgraded cluster

### Rollback Plan (if upgrade fails)

**Node pool rollback** (if nodes don't come up correctly):
```bash
# Create replacement pool at 1.31
gcloud container node-pools create gpu-nodepool-rollback \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.31.x-gke.xxxx \
  --machine-type a3-megagpu-8g \
  --num-nodes 512 \
  --placement-type COMPACT

# Migrate training workload to rollback pool
# Delete failed upgrade pool after validation
```

### Emergency Procedures

**If upgrade breaks active training**:
1. **Don't panic** - training can resume from checkpoint
2. Identify which nodes are problematic
3. Cordon broken nodes: `kubectl cordon NODE_NAME`
4. Reschedule training pods to healthy nodes
5. Contact GKE support with cluster details

## Alternative: Staged Cluster Migration

**If in-place upgrade risk is too high**, consider blue-green at cluster level:

1. **Create new 1.32 cluster** with identical A3 Mega configuration
2. **Finish current training** on existing 1.31 cluster
3. **Migrate workloads** to new cluster during natural gap
4. **Validate** new cluster with short training run
5. **Decommission** old cluster after validation

This eliminates upgrade risk but requires 2x GPU reservation temporarily.

## Monitoring & Alerts

Set up specific alerts for this upgrade:

```bash
# GPU node readiness
kubectl get nodes -l accelerator=nvidia-h100-mega-80gb

# Training pod restarts (should be minimal)
kubectl get pods -l app=llm-training -o json | jq '.items[] | select(.status.restartCount > 0)'

# GPUDirect connectivity health
# (Deploy monitoring pod that tests inter-node GPU communication)
```

---

**Key Success Factors**:
1. ✅ **Timing is everything** - upgrade only during training gaps
2. ✅ **Staging validation** - test GPUDirect-TCPXO on 1.32 first  
3. ✅ **No surge capacity** - use `maxUnavailable` as speed lever
4. ✅ **Checkpoint safety** - always have recent checkpoint before upgrade
5. ✅ **Monitor duration** - 512 nodes = 3-5 days upgrade time

This plan prioritizes **training continuity** over upgrade speed. The 3-5 day upgrade window is acceptable given the 2-3 week training duration and checkpoint protection.