# LLM Training Cluster Upgrade Plan: GKE 1.31→1.32

## Executive Summary

**Critical considerations for your environment:**
- 512 H100 nodes (A3 Mega) with GPUDirect-TCPXO interconnect
- Active 2-3 week training runs that cannot tolerate mid-job eviction
- GKE's default 1-hour pod eviction timeout is incompatible with multi-week training
- A3 Mega + GPUDirect-TCPXO has specific GKE version requirements

**Recommended approach:** Use maintenance exclusions to block node upgrades during active training, upgrade control plane only during training gaps, then coordinate node pool upgrades with training campaign schedules.

---

## Version Compatibility Check

### GPUDirect-TCPXO Requirements
- **Current (1.31):** ✅ Supported for A3 Mega
- **Target (1.32):** ✅ Supported - no breaking changes for A3 Mega GPUDirect-TCPXO
- **Network config:** Verify custom high-MTU VPC settings survive upgrade
- **Driver compatibility:** GKE 1.32 will auto-install compatible GPU drivers - test in staging first

### Pre-flight Commands
```bash
# Verify current cluster state
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Check available versions in your release channel
gcloud container get-server-config --region REGION \
  --format="yaml(channels)"

# Verify no deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```

---

## Upgrade Strategy: Phased Approach with Training Protection

### Phase 1: Control Plane Upgrade (Training-Safe)
**When:** During training runs - control plane upgrades don't affect running workloads

```bash
# Add node pool maintenance exclusion BEFORE CP upgrade
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Upgrade control plane only
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.32.x-gke.LATEST
```

**Impact:** Zero disruption to training jobs. Regional cluster control plane remains highly available during upgrade.

### Phase 2: Node Pool Upgrade (Training Gap Required)
**When:** Only during scheduled gaps between training campaigns

#### Option A: Parallel Host Maintenance (Recommended for Training)
Best for when you can checkpoint and restart training:

```bash
# Before starting upgrade:
# 1. Checkpoint current training state
# 2. Scale training workload to 0 replicas
# 3. Wait for all training pods to terminate cleanly

# Apply maintenance label to ALL nodes simultaneously
kubectl label nodes -l cloud.google.com/gke-nodepool=TRAINING_POOL_NAME \
  cloud.google.com/perform-maintenance=true

# Monitor host maintenance progress (~4 hours)
kubectl get nodes -l cloud.google.com/gke-nodepool=TRAINING_POOL_NAME \
  -o custom-columns="NAME:.metadata.name,STATUS:.status.conditions[?(@.type=='Ready')].status,VERSION:.status.nodeInfo.kubeletVersion"
```

**Advantages:**
- All 512 nodes updated simultaneously in ~4 hours
- Minimizes total training downtime
- No risk of partial cluster state

#### Option B: Rolling with Extended Grace Period (If Checkpointing Unavailable)
If training cannot be stopped but can tolerate extended drain periods:

```bash
# Configure autoscaled blue-green with extended termination grace
gcloud container node-pools update TRAINING_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --strategy AUTOSCALED_BLUE_GREEN \
  --enable-autoscaling \
  --total-max-nodes 1024 \
  --autoscaled-rollout-policy blue-green-initial-node-percentage=0.25

# Ensure training pods have extended termination grace
# In training job spec:
# terminationGracePeriodSeconds: 86400  # 24 hours
```

**Important:** This still carries risk of training interruption. Parallel approach is strongly preferred.

---

## GPU-Specific Upgrade Configuration

### Node Pool Strategy
```bash
# For your GPU training pool - DO NOT use maxSurge (no surge capacity available)
gcloud container node-pools update TRAINING_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4  # Adjust based on training sensitivity
```

### Compact Placement Verification
```bash
# Verify placement policy survives upgrade
gcloud compute instances describe NODE_NAME \
  --zone ZONE \
  --format="value(resourcePolicies)"

# After upgrade, confirm nodes remain in same placement group
kubectl get nodes -l cloud.google.com/gke-nodepool=TRAINING_POOL_NAME \
  -o custom-columns="NAME:.metadata.name,ZONE:.metadata.labels.topology\.kubernetes\.io/zone"
```

---

## Training Job Protection Checklist

### Before Any Node Upgrade
```bash
# Verify maintenance exclusion is active
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="value(maintenancePolicy.window.maintenanceExclusions)"

# Ensure training pods have checkpointing enabled
kubectl describe pods -l app=training -n NAMESPACE | grep -A5 "Volumes:"

# Verify PDBs protect training workloads
kubectl get pdb -n NAMESPACE
```

### Training Job Configuration
Your training workloads should have:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: llm-training
spec:
  replicas: 64  # Adjust for your training setup
  template:
    spec:
      terminationGracePeriodSeconds: 86400  # 24 hours
      containers:
      - name: training
        resources:
          requests:
            nvidia.com/gpu: 8
          limits:
            nvidia.com/gpu: 8
      nodeSelector:
        cloud.google.com/gke-nodepool: "training-pool"
      tolerations:
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
spec:
  selector:
    matchLabels:
      app: training
  minAvailable: 90%  # Prevent more than ~6 nodes draining simultaneously
```

---

## Upgrade Timeline & Coordination

### Phase 1: Control Plane (0 downtime)
- **Duration:** 10-15 minutes
- **When:** Anytime during training
- **Command:** `gcloud container clusters upgrade --master`

### Phase 2: Node Pool Upgrade Planning
```bash
# Estimate upgrade duration for 512 nodes
# GKE upgrades ~20 nodes simultaneously max
# 512 nodes ÷ 20 = ~26 batches
# At ~10 minutes per batch = ~4.5 hours minimum

# For parallel host maintenance (recommended):
# All 512 nodes updated in ~4 hours total
```

### Recommended Schedule
1. **Week 1:** Upgrade control plane during active training
2. **Week 2-3:** Continue training with exclusion protecting nodes
3. **Training Gap:** Execute node pool upgrade using parallel host maintenance
4. **Week 4+:** Resume training on upgraded cluster

---

## Rollback Plan

### Control Plane Rollback
- Minor version rollback requires GKE support involvement
- Consider two-step upgrade for rollback-safe path if available in 1.32

### Node Pool Rollback
```bash
# If upgrade fails partway through:
# 1. Fix root cause
# 2. Resume upgrade (preferred):
gcloud container node-pools upgrade TRAINING_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.32.x-gke.LATEST

# 3. Or create new pool at old version (last resort):
gcloud container node-pools create training-pool-rollback \
  --cluster CLUSTER_NAME \
  --region REGION \
  --machine-type a3-megagpu-8g \
  --accelerator type=nvidia-h100-mega-80gb,count=8 \
  --cluster-version 1.31.x-gke.CURRENT
```

---

## Post-Upgrade Validation

### GPU Interconnect Verification
```bash
# Verify GPUDirect-TCPXO connectivity
kubectl exec -it TRAINING_POD -- nvidia-smi topo -m

# Check high-MTU network configuration
ip link show | grep mtu

# Validate NCCL communication (from training pod)
kubectl exec -it TRAINING_POD -- \
  /opt/nccl-tests/build/all_reduce_perf -b 8 -e 128M -f 2 -g 8
```

### Training Workload Health
```bash
# Verify all GPU nodes ready
kubectl get nodes -l accelerator=nvidia-h100-mega-80gb

# Check GPU allocation
kubectl get nodes -o json | jq '.items[] | {name: .metadata.name, allocatable: .status.allocatable}'

# Validate placement policy intact
kubectl get pods -l app=training -o wide | head -20
```

---

## Key Reminders

1. **Never upgrade nodes during active training** - use maintenance exclusions
2. **Control plane upgrades are safe** during training runs
3. **Test GPU driver compatibility** in staging before production
4. **Parallel host maintenance minimizes downtime** for training workloads
5. **GPUDirect-TCPXO requirements are met** in both 1.31→1.32
6. **Coordinate with training team** for upgrade windows between campaigns

This approach protects your multi-week training investments while keeping your cluster current on security patches and features.