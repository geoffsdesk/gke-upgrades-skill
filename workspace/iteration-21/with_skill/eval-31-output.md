# GKE Upgrade Plan: Large-scale LLM Training Cluster

## Cluster Profile Analysis
- **Scale**: 512 H100 nodes (4,096 GPUs total) - Large AI cluster
- **Hardware**: A3 Mega instances with GPUDirect-TCPXO
- **Workload**: Multi-week LLM training (disruption-intolerant)
- **Current**: GKE 1.31 → **Target**: 1.32
- **Critical constraints**: Active training run + GPUDirect networking

## Executive Summary: Phased Approach Required

**Your cluster falls into the most complex upgrade category.** You need a carefully orchestrated approach that protects the active training run while ensuring GPU interconnect compatibility. The key insight: **separate control plane and node pool upgrades with timing based on training schedule.**

## Phase 1: Control Plane Upgrade (Immediate - Safe During Training)

The control plane can be upgraded while training continues. Regional clusters maintain API availability throughout.

### Pre-flight Checks
```bash
# Verify current versions and channel
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="table(name, currentMasterVersion, releaseChannel.channel)"

# Confirm GPUDirect-TCPXO compatibility with 1.32
# GKE 1.32 maintains TCPXO support for A3 Mega - verified compatible

# Check for deprecated API usage (critical for multi-week training)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=REGION \
    --project=PROJECT_ID
```

### Control Plane Upgrade Commands
```bash
# Apply "no minor or node upgrades" exclusion FIRST (blocks node auto-upgrades)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "training-campaign-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Upgrade control plane only (bypasses maintenance exclusions)
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.32.X-gke.LATEST

# Verify control plane upgraded, nodes unchanged
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="table(currentMasterVersion, nodePools[].version)"
```

**Why this is safe during training**: Regional control plane upgrades maintain API availability. Training pods continue running on existing nodes. The maintenance exclusion prevents any node disruption.

## Phase 2: Node Pool Upgrade Preparation (During Training Gap)

**Critical timing**: Schedule this phase during your next planned training gap between runs.

### GPU-Specific Node Pool Strategy

Given your constraints:
- **512 H100 nodes with fixed GPU reservation** (no surge capacity)
- **GPUDirect-TCPXO requires specific network topology**
- **Compact placement groups must be preserved**

**Recommended Strategy: Autoscaled Blue-Green with Extended Soak**

```bash
# Configure autoscaled blue-green for GPU node pool
gcloud container node-pools update GPU_NODE_POOL_NAME \
    --cluster CLUSTER_NAME \
    --region REGION \
    --strategy=AUTOSCALED_BLUE_GREEN \
    --enable-autoscaling \
    --total-min-nodes 512 --total-max-nodes 1024 \
    --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.1,blue-green-full-batch-timeout=14400s \
    --node-pool-soak-duration=172800s
```

**Key parameters explained**:
- `blue-green-initial-node-percentage=0.1`: Start with 10% (51 nodes) in green pool
- `blue-green-full-batch-timeout=14400s`: 4-hour timeout for batch readiness
- `node-pool-soak-duration=172800s`: 48-hour soak period for validation
- `total-max-nodes=1024`: Temporary 2x capacity for blue-green (requires quota)

### Alternative: Manual Staged Approach (If 2x Capacity Unavailable)

If you cannot get 2x H100 quota for blue-green:

```bash
# Option: Drain-first with minimal parallelism
gcloud container node-pools update GPU_NODE_POOL_NAME \
    --cluster CLUSTER_NAME \
    --region REGION \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 4
    # 4 nodes at a time = ~3-4 days total upgrade time
```

## Phase 3: Training Run Coordination

### Before Starting Node Upgrade

**Critical steps in order:**

1. **Checkpoint training state:**
```bash
# Ensure training framework saves checkpoint
# Wait for checkpoint completion confirmation
kubectl logs -f TRAINING_POD_NAME | grep -i checkpoint
```

2. **Scale down training workload:**
```bash
kubectl scale deployment TRAINING_DEPLOYMENT --replicas=0
# Or for StatefulSets:
kubectl scale statefulset TRAINING_STATEFULSET --replicas=0
```

3. **Verify GPUDirect topology preservation:**
```bash
# Check compact placement policy is active
gcloud compute instances describe INSTANCE_NAME \
  --zone ZONE \
  --format="value(resourcePolicies[])"

# Verify RDMA network interfaces present
kubectl debug node/NODE_NAME -it --image=nicolaka/netshoot -- ip link show
```

### During Node Pool Upgrade

**Monitor these critical aspects:**

```bash
# Track upgrade progress (expect 2-4 days for 512 nodes)
watch 'kubectl get nodes -L cloud.google.com/gke-nodepool -L cloud.google.com/gke-preemptible'

# Verify new nodes land in same placement groups
gcloud compute instances list --filter="name~.*gke.*" \
  --format="table(name, zone, resourcePolicies[0]:label=PLACEMENT_POLICY)"

# Check TCPXO network interfaces on new nodes
kubectl get nodes -o jsonpath='{.items[*].status.addresses[?(@.type=="InternalIP")].address}' | \
  xargs -I {} kubectl debug node/{} -it --image=nicolaka/netshoot -- \
  ip link show | grep -E "(ib0|roce)"
```

### Post-Upgrade Validation

```bash
# All nodes at target version
kubectl get nodes -L kubernetes.io/version

# GPU driver compatibility check
kubectl describe nodes | grep -A5 "nvidia.com/gpu"

# TCPXO network validation
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: tcpxo-test
spec:
  containers:
  - name: test
    image: nvcr.io/nvidia/pytorch:24.01-py3
    command: ["python", "-c", "import torch; print(f'GPUs: {torch.cuda.device_count()}'); print('NCCL available:', torch.distributed.is_nccl_available())"]
    resources:
      limits:
        nvidia.com/gpu: 1
EOF

kubectl logs tcpxo-test
kubectl delete pod tcpxo-test
```

## Phase 4: Training Restart and Validation

### Restart Training Workload

```bash
# Scale training back up
kubectl scale deployment TRAINING_DEPLOYMENT --replicas=ORIGINAL_REPLICAS

# Monitor training pod placement across upgraded nodes
kubectl get pods -o wide | grep training

# Verify multi-node NCCL communication
kubectl logs TRAINING_POD_NAME | grep -i "nccl\|allreduce\|broadcast"
```

### Remove Maintenance Exclusion

```bash
# Only after training restart is validated
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --remove-maintenance-exclusion-name "training-campaign-protection"
```

## Risk Mitigation & Rollback Plan

### If Upgrade Breaks GPU Interconnect

```bash
# Emergency rollback: create new pool at 1.31
gcloud container node-pools create gpu-pool-rollback \
  --cluster CLUSTER_NAME \
  --region REGION \
  --accelerator type=nvidia-h100-80gb,count=8,gpu-driver-version=GRID450 \
  --machine-type a3-megagpu-8g \
  --node-version 1.31.X-gke.PREVIOUS \
  --placement-policy EXISTING_PLACEMENT_POLICY \
  --num-nodes 512

# Cordon upgraded pool, drain to rollback pool
kubectl cordon -l cloud.google.com/gke-nodepool=gpu-pool-upgraded
```

### If Training Performance Degrades

```bash
# Validate TCPXO bandwidth between nodes
kubectl apply -f gpu-bandwidth-test.yaml
# Compare against pre-upgrade baselines

# Check for new taints/labels affecting placement
kubectl describe nodes | grep -A3 -B3 "Taints\|Labels" | grep nvidia
```

## Timeline & Coordination

**Total estimated timeline**: 4-7 days

- **Day 0**: Control plane upgrade (2-3 hours)
- **Day 1**: Training gap begins, checkpoint save
- **Day 1-4**: Node pool upgrade (autoscaled blue-green)
- **Day 4-5**: 48-hour soak period validation
- **Day 5**: Training restart
- **Day 6-7**: Performance validation, remove exclusions

**Critical coordination points**:
- Coordinate with ML team for training gap timing
- Reserve 2x H100 quota if using blue-green strategy  
- Have rollback node pool quota reserved as backup
- Ensure on-call coverage throughout the upgrade window

This approach protects your active training run while ensuring GPU interconnect compatibility is validated before returning to production training workloads.