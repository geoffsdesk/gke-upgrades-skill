# GKE Upgrade Plan for Large-Scale LLM Training Cluster

## Executive Summary

**Challenge**: 512-node H100 cluster running 2-3 week training campaigns with GPUDirect-TCPXO interconnect
**Current**: GKE 1.31 → **Target**: GKE 1.32
**Strategy**: Maintenance exclusions + dedicated training pool isolation + checkpoint-based approach

## Critical Constraints Analysis

### GPU Interconnect Compatibility
- **GPUDirect-TCPXO**: Requires GKE 1.27.7+ (✅ supported in both 1.31 and 1.32)
- **Risk**: Upgrade may break RDMA topology if nodes don't land in same compact placement group
- **Mitigation**: Test in staging cluster first to verify interconnect survives upgrade

### Training Job Protection
- **Multi-week duration**: Far exceeds GKE's 1-hour PDB timeout during surge upgrades
- **No live migration**: GPU VMs require pod restart for any upgrade
- **Checkpoint dependency**: Jobs MUST have checkpointing enabled for any upgrade strategy

### Scale Limitations
- **512 nodes**: Will take days/weeks to upgrade with GKE's ~20 node parallelism limit
- **Fixed GPU reservation**: Likely no surge capacity available for blue-green approach
- **A3 Mega specifics**: 8x H100 per node, custom networking stack

## Recommended Upgrade Strategy

### Phase 1: Immediate Protection (Do This Now)
```bash
# Block all node upgrades during active training
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-until-end-of-support \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

This allows control plane security patches but blocks disruptive node upgrades.

### Phase 2: Control Plane Upgrade (Safe During Training)
```bash
# Upgrade control plane only - no node disruption
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.32.X-gke.LATEST

# Verify CP upgrade successful
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="value(currentMasterVersion)"
```

**Why this is safe**: Control plane upgrades don't affect running GPU workloads. Regional clusters maintain availability throughout.

### Phase 3: Node Pool Strategy (Between Training Runs)

**Option A: Checkpoint and Upgrade (Recommended)**
```bash
# 1. Checkpoint current training run
kubectl exec -it TRAINING_POD -- python checkpoint.py

# 2. Scale training workload to zero
kubectl scale deployment llm-training --replicas=0

# 3. Configure for GPU pool upgrade (no surge capacity)
gcloud container node-pools update gpu-training-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4

# 4. Remove maintenance exclusion temporarily
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --remove-maintenance-exclusion "training-protection"

# 5. Trigger node pool upgrade
gcloud container node-pools upgrade gpu-training-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.32.X-gke.LATEST

# 6. Monitor progress (will take days for 512 nodes)
watch 'kubectl get nodes -o wide -l cloud.google.com/gke-nodepool=gpu-training-pool'
```

**Option B: Parallel Host Maintenance (Alternative)**
```bash
# Apply maintenance label to all nodes simultaneously
kubectl label nodes -l cloud.google.com/gke-nodepool=gpu-training-pool \
  cloud.google.com/perform-maintenance=true

# Host maintenance takes ~4 hours, all nodes updated in parallel
# Training job must be checkpointed and stopped first
```

## Pre-Upgrade Validation Checklist

### Staging Environment Test
```markdown
- [ ] Create identical staging cluster with A3 Mega nodes
- [ ] Deploy representative training workload
- [ ] Upgrade staging cluster 1.31 → 1.32
- [ ] Verify GPUDirect-TCPXO connectivity post-upgrade:
  - [ ] RDMA topology preserved
  - [ ] Inter-node bandwidth unchanged
  - [ ] Training convergence unaffected
- [ ] Test checkpoint/resume workflow
```

### Production Readiness
```markdown
- [ ] Training checkpointing confirmed working
- [ ] Compact placement policy documented
- [ ] Network topology mapped and verified
- [ ] Rollback plan documented
- [ ] Maintenance window scheduled between training campaigns
```

## Timing Strategy

### Current Training Run
- **Do NOT upgrade nodes** while training is active
- **Upgrade control plane now** (safe, no workload impact)
- **Apply maintenance exclusions** to prevent auto-upgrades

### Between Training Runs
- **Schedule 3-5 day maintenance window** for 512-node upgrade
- **Complete node upgrades** before starting next training campaign
- **Verify GPU interconnect** before resuming training

## Risk Mitigation

### GPUDirect-TCPXO Validation
```bash
# Post-upgrade interconnect test
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: nccl-test
spec:
  containers:
  - name: nccl-test
    image: nvcr.io/nvidia/pytorch:23.10-py3
    command: ["python", "-c", "import torch; print(torch.distributed.is_nccl_available())"]
    resources:
      limits:
        nvidia.com/gpu: 1
EOF

# Verify RDMA devices visible
kubectl exec nccl-test -- ls -la /dev/infiniband/
```

### Checkpoint Validation
```bash
# Test checkpoint/resume before upgrade
kubectl exec -it TRAINING_POD -- python -c "
import torch
torch.save({'step': 1000, 'loss': 0.5}, '/checkpoints/test.pt')
loaded = torch.load('/checkpoints/test.pt')
print(f'Checkpoint test: {loaded}')
"
```

## Alternative: Extended Channel Migration

For maximum upgrade control in the future:
```bash
# Migrate to Extended channel for 24-month support
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel extended

# Extended channel blocks auto-minor-upgrades by default
# Only patches are auto-applied
```

## Troubleshooting GPU Upgrades

### If Surge Nodes Fail to Provision
```bash
# Check GPU quota and reservations
gcloud compute reservations describe GPU_RESERVATION \
  --zone ZONE

# Fall back to drain-first approach
gcloud container node-pools update gpu-training-pool \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

### If RDMA Topology Breaks
```bash
# Verify compact placement
kubectl get nodes -o json | \
  jq '.items[] | {name: .metadata.name, zone: .metadata.labels["topology.kubernetes.io/zone"]}'

# Check RDMA device availability
kubectl debug node/NODE_NAME -it --image=ubuntu -- \
  ls -la /host/dev/infiniband/
```

## Key Takeaways

1. **Control plane upgrades are safe** during active training
2. **Node upgrades require checkpointing** - no way around pod restarts
3. **Use maintenance exclusions** to prevent auto-upgrades during training
4. **Test GPU interconnect thoroughly** in staging before production
5. **Plan for days/weeks** for 512-node upgrade completion
6. **maxUnavailable is your primary lever** for GPU pools (not maxSurge)

The safest approach is upgrading the control plane immediately, then scheduling node upgrades between training campaigns with proper checkpointing.