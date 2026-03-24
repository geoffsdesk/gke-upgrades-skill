# Large-Scale LLM Training Cluster Upgrade Plan

## Current Environment Analysis
- **Cluster**: GKE Standard, 512 H100 nodes (A3 Mega), 4,096 total GPUs
- **Current Version**: 1.31 → **Target**: 1.32
- **Training Duration**: 2-3 weeks (critical constraint)
- **Interconnect**: GPUDirect-TCPXO (version-sensitive)
- **Scale**: Frontier AI workload requiring specialized upgrade approach

## Critical Constraint: Active Training Protection

Your 2-3 week training runs are fundamentally incompatible with GKE's standard upgrade mechanisms:
- **Surge upgrades**: 1-hour pod eviction timeout will terminate training
- **Blue-green upgrades**: Full cluster recreation will terminate training
- **Standard auto-upgrades**: Will trigger during training window

## Recommended Upgrade Strategy

### Phase 1: Immediate Protection (Do This First)

```bash
# Block all auto-upgrades during active training
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

This gives you 30 days to plan the upgrade without auto-upgrade interference.

### Phase 2: Training Gap Coordination

**Option A - Natural Training Cycle (Recommended)**
1. **Wait for current training completion** (2-3 weeks max remaining)
2. **During model checkpointing/evaluation gap**: Execute full cluster upgrade
3. **Resume next training run** on upgraded cluster

**Option B - Forced Checkpoint (If Urgent)**
1. **Force checkpoint current training** at next natural milestone
2. **Scale training workload to zero**: `kubectl scale deployment llm-training --replicas=0`
3. **Execute immediate upgrade**
4. **Resume from checkpoint** on upgraded cluster

### Phase 3: GPU-Optimized Upgrade Execution

Given your scale (512 nodes), expect **upgrade duration: 1-3 days**

#### GPU Node Pool Strategy
```bash
# Configure for GPU pools (NO surge capacity assumed)
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4
```

**Rationale**: H100 reservations typically have zero surge capacity. `maxUnavailable=4` provides reasonable parallelism while maintaining most cluster capacity.

#### Control Plane Upgrade (Safe During Training)
```bash
# Upgrade control plane first - no workload disruption
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.32.latest-gke.XXXX
```

**Impact**: Regional control plane upgrade has no training workload impact.

### Phase 4: Node Pool Upgrade (Training Gap Required)

#### Pre-Upgrade Verification
```bash
# Verify GPUDirect-TCPXO compatibility with target version
# Check GKE release notes for A3 Mega + TCPXO requirements

# Confirm training checkpoints saved
kubectl exec -it training-pod -- ls -la /checkpoint/

# Scale training to zero
kubectl scale deployment llm-training --replicas=0
```

#### Execute Node Upgrade
```bash
# Upgrade GPU node pool
gcloud container node-pools upgrade gpu-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.32.latest-gke.XXXX
```

**Duration Estimate**: 512 nodes ÷ 4 concurrent ÷ ~20 batch limit = ~6-8 hours minimum

### Phase 5: Post-Upgrade Validation

#### Critical Validation Checklist
```bash
# Verify all nodes upgraded
kubectl get nodes -o wide | grep -v 1.32

# Verify GPU driver version
kubectl describe nodes | grep -A 5 "nvidia.com/gpu"

# Test GPUDirect-TCPXO connectivity
# Deploy test multi-node GPU job to verify RDMA/interconnect

# Verify compact placement maintained
kubectl get nodes --show-labels | grep topology.gke.io/zone
```

#### Interconnect-Specific Checks
- **GPUDirect-TCPXO**: Requires GKE 1.27.7-gke.1121000+ (✓ covered by 1.32)
- **RDMA topology**: Verify replacement nodes land in same placement groups
- **High-MTU networking**: Confirm custom VPC config survives upgrade

### Phase 6: Training Resumption

```bash
# Scale training back up
kubectl scale deployment llm-training --replicas=ORIGINAL_COUNT

# Monitor GPU utilization and interconnect performance
kubectl top nodes | grep -A 512 gpu-
```

## Alternative: Cluster Recreation Strategy

For maximum safety with frontier workloads:

```bash
# Create parallel cluster at 1.32
gcloud container clusters create training-cluster-v2 \
  --release-channel regular \
  --cluster-version 1.32.latest-gke.XXXX \
  --enable-network-policy \
  --placement-type COMPACT \
  --num-nodes 512 \
  --machine-type a3-megagpu-8g

# Migrate training during natural gap
# Destroy old cluster after validation
```

## Release Channel Recommendation

```bash
# If not already enrolled, migrate to Regular channel for predictable upgrades
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel regular
```

## Ongoing Training Protection Strategy

### Dedicated Training Node Pool
```bash
# Create training-only pool with tight maintenance control
gcloud container node-pools create training-nodes \
  --cluster CLUSTER_NAME \
  --region REGION \
  --enable-autoscaling=false \
  --num-nodes 512 \
  --machine-type a3-megagpu-8g \
  --node-labels=workload-type=training
```

### Persistent Exclusion During Training Seasons
```bash
# Use persistent exclusion that auto-renews
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "training-season" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Risk Assessment

**HIGH RISK**: Upgrading during active 3-week training
- Training data loss, 2-3 weeks compute waste
- Estimated cost: $500K+ in wasted compute

**MEDIUM RISK**: Forced checkpoint approach  
- Training interruption, some progress loss
- Resume complexity, potential model convergence issues

**LOW RISK**: Natural training gap upgrade
- Clean checkpoint/resume cycle
- No training data loss
- Recommended approach

## Timeline
- **Week 1-3**: Current training completion under maintenance exclusion
- **Week 3**: Execute upgrade during training gap (1-3 days)
- **Week 4**: Resume training on 1.32 cluster

This approach protects your multi-million dollar training investment while achieving the necessary upgrade.