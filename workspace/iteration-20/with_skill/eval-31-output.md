# GKE Upgrade Plan: Large-Scale LLM Training Cluster (512 H100 Nodes)

## Cluster Profile
- **Cluster**: Large-scale LLM training | **Mode**: Standard | **Scale**: 512 H100 nodes (A3 Mega)
- **Current version**: 1.31 | **Target version**: 1.32
- **Workload**: 2-3 week training runs with GPUDirect-TCPXO
- **Critical constraints**: Cannot interrupt active training, must preserve GPU interconnect

## Executive Summary

**Recommended approach**: Two-phase upgrade with training campaign coordination:
1. **Phase 1**: Control plane upgrade only (minimal disruption)
2. **Phase 2**: Node pool upgrade during scheduled training gap

**Key insight**: Your GPUDirect-TCPXO interconnect and 2-3 week training runs require special handling that standard GKE upgrade strategies cannot accommodate. We'll use maintenance exclusions to protect the active training while upgrading the control plane for security patches.

## Phase 1: Control plane upgrade (immediate)

The control plane can be upgraded without affecting running training workloads. GKE supports 2 minor version skew between control plane and nodes.

### Pre-flight checks
```bash
# Verify GPUDirect-TCPXO compatibility with 1.32
# (1.32 maintains support for A3 Mega GPUDirect-TCPXO)
gcloud container get-server-config --region REGION --format="yaml(channels)"

# Check current training job status
kubectl get pods -l app=training -o wide
kubectl top nodes | head -20

# Verify cluster health before upgrade
kubectl get nodes | grep -v Ready || echo "All nodes Ready"
kubectl get pods -n kube-system | grep -v Running
```

### Control plane upgrade
```bash
# Apply "no minor or node upgrades" exclusion to protect training nodes
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "protect-training-run" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Upgrade control plane only
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.32.x-gke.xxxx

# Monitor (typically 10-15 minutes for regional clusters)
gcloud container operations list --region REGION --filter="operationType=UPGRADE_MASTER"
```

**Impact**: Control plane upgrade on regional clusters maintains API availability. Training workloads continue unaffected. Version skew (CP 1.32, nodes 1.31) is fully supported.

## Phase 2: Node pool upgrade (during training gap)

**Critical timing**: Schedule this phase during your natural training campaign break — between model runs when nodes are idle.

### Pre-upgrade preparation (1 week before training gap)

```bash
# Verify target GKE 1.32 + driver compatibility in staging
# Create small staging pool with target version
gcloud container node-pools create staging-validation \
  --cluster STAGING_CLUSTER \
  --region REGION \
  --machine-type a3-megagpu-8g \
  --accelerator type=nvidia-h100-mega-80gb,count=8 \
  --node-version 1.32.x-gke.xxxx \
  --num-nodes 1

# Deploy representative training workload to validate:
# - CUDA compatibility with new driver version
# - GPUDirect-TCPXO networking stack
# - Model loading and basic training steps
```

### Upgrade strategy: Custom workflow for AI training

For your scale and sensitivity, use a **custom upgrade approach** rather than GKE's built-in strategies:

**Why custom is needed:**
- **GKE's autoscaled blue-green** has ~20 node concurrency limit (roadmap: 100) — would take days for 512 nodes
- **Standard blue-green** requires 2x resources (1,024 H100s) — likely exceeds reservation
- **Surge upgrades** destroy local SSD data and force-evict after 1 hour
- **Training jobs run 2-3 weeks** — far exceeding any GKE eviction timeout

### Custom upgrade workflow

```bash
# Step 1: Wait for natural training completion
# Monitor training job completion
kubectl logs -f training-job-pod -c main-container

# Step 2: Cordon all training nodes (prevent new scheduling)
kubectl get nodes -l node.kubernetes.io/instance-type=a3-megagpu-8g -o name | \
  xargs -I {} kubectl cordon {}

# Step 3: Verify all training pods have terminated
kubectl get pods -l app=training --field-selector=status.phase=Running
# Should return empty

# Step 4: Parallel host maintenance + node upgrade
# Apply maintenance label to trigger host maintenance (required for firmware/driver updates)
kubectl get nodes -l node.kubernetes.io/instance-type=a3-megagpu-8g -o name | \
  xargs -I {} kubectl label {} cloud.google.com/perform-maintenance=true

# Simultaneously upgrade node pool (will coordinate with host maintenance)
gcloud container node-pools upgrade gpu-training-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --node-version 1.32.x-gke.xxxx
```

**Timeline expectations:**
- **Host maintenance**: ~4 hours per node batch
- **GKE upgrade parallelism**: ~20 nodes simultaneously (increasing to 100)
- **Total duration**: 26-51 batches = ~104-204 hours (4-8 days)

### Validation after upgrade

```bash
# Verify all nodes upgraded and Ready
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,STATUS:.status.conditions[-1].type

# Test GPUDirect-TCPXO networking
# Deploy multi-node NCCL test to verify interconnect
kubectl apply -f nccl-test-multinode.yaml
kubectl logs nccl-test-pod | grep "Avg bus bandwidth"

# Validate GPU driver and CUDA version
kubectl run gpu-test --rm -it --restart=Never \
  --image=nvidia/cuda:12.1-base-ubuntu20.04 \
  --overrides='{"spec":{"nodeSelector":{"cloud.google.com/gke-accelerator":"nvidia-h100-mega-80gb"},"tolerations":[{"operator":"Exists"}]}}' \
  -- nvidia-smi

# Check compact placement (critical for RDMA topology)
kubectl get nodes -l node.kubernetes.io/instance-type=a3-megagpu-8g \
  -o custom-columns=NAME:.metadata.name,ZONE:.metadata.labels.topology\.kubernetes\.io/zone
```

## Risk mitigation

### GPU interconnect protection
- **Compact placement policy**: Verify replacement nodes land in same placement group
- **RDMA topology validation**: Test multi-node NCCL after each upgrade batch
- **Staging validation**: Mandatory test of target GKE version + driver combo before production

### Training job protection
```bash
# Maintenance exclusion prevents auto-upgrades during training
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="value(maintenancePolicy.maintenanceExclusions)"

# Emergency: extend exclusion if training runs longer than expected
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "extend-training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-start-time "2024-XX-XXTXX:XX:XXZ" \
  --add-maintenance-exclusion-end-time "2024-XX-XXTXX:XX:XXZ"
```

### Checkpoint and recovery
- **Checkpoint before Phase 2**: Ensure training has current checkpoint before starting node upgrades
- **Rollback capability**: Keep previous node pool version available via downgrade if interconnect breaks

## Timeline and coordination

```
Week 1: Phase 1 (Control plane upgrade)
├── Day 1: Pre-flight checks, staging validation
├── Day 2: Apply maintenance exclusion, upgrade CP
├── Day 3-7: Monitor training continues on 1.31 nodes, CP at 1.32

Training Campaign Gap (coordinate with ML team):
├── Training completion notification
├── Phase 2: Node pool upgrade (4-8 days)
├── Post-upgrade validation (1 day)
├── New training campaign start

Total: ~2 weeks (1 week running mixed, 1 week upgrade window)
```

## Cost considerations

- **Extended support**: Consider Extended release channel for future upgrades — gives 24 months support and delays auto-upgrade enforcement
- **Reservation planning**: Verify your H100 reservation covers any surge needs (though custom workflow minimizes extra capacity requirements)

## Rollback plan

**Control plane**: Contact GKE support for minor version downgrade assistance.

**Node pool**: 
```bash
# Create emergency rollback pool at 1.31
gcloud container node-pools create gpu-rollback-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --machine-type a3-megagpu-8g \
  --node-version 1.31.x-gke.xxxx \
  --num-nodes 512
```

**This plan protects your active 2-3 week training runs while ensuring you get security patches and maintain GPU interconnect compatibility. The key insight is coordinating the disruptive node upgrade with your natural training campaign schedule rather than forcing it during an active run.**