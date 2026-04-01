# GKE Configuration for H100 Foundation Model Training

## Cluster Configuration

```bash
# Create regional cluster with Extended channel for maximum upgrade control
gcloud container clusters create foundation-training \
  --zone us-central1-a \
  --num-nodes 0 \
  --release-channel extended \
  --enable-network-policy \
  --enable-ip-alias \
  --network training-vpc \
  --subnetwork training-subnet \
  --cluster-version 1.31.1-gke.1678000 \
  --logging=SYSTEM,WORKLOAD \
  --monitoring=SYSTEM \
  --enable-shielded-nodes \
  --shielded-secure-boot \
  --max-nodes-per-pool 1000
```

## Release Channel Strategy: Extended

**Why Extended channel for AI training:**
- Up to 24 months of support (vs 14 months for Regular/Stable)
- **Control plane minor versions are NOT auto-upgraded** (except at end of extended support)
- Only patches are auto-applied at Regular channel timing
- Maximum flexibility around EoS enforcement
- Additional cost applies ONLY during extended support period (months 15-24)

## Training-Optimized Node Pool

```bash
# Dedicated training pool with upgrade protection
gcloud container node-pools create h100-training \
  --cluster foundation-training \
  --zone us-central1-a \
  --machine-type a3-highgpu-8g \
  --accelerator type=nvidia-h100-80gb,count=8 \
  --num-nodes 8 \
  --enable-autoscaling \
  --min-nodes 0 \
  --max-nodes 32 \
  --node-locations us-central1-a \
  --placement-type COMPACT \
  --placement-policy-name training-placement \
  --reservation-affinity consume-reservation \
  --reservation training-h100-reservation \
  --enable-autorepair \
  --enable-autoupgrade=false \
  --disk-type pd-ssd \
  --disk-size 1000GB \
  --local-ssd-count 16 \
  --node-taints training=true:NoSchedule \
  --node-labels workload=training,gpu=h100
```

## Upgrade Protection Configuration

```bash
# Set maintenance window during training gaps (assume weekend downtime)
gcloud container clusters update foundation-training \
  --zone us-central1-a \
  --maintenance-window-start "2024-01-01T02:00:00Z" \
  --maintenance-window-duration 6h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Configure "no minor or node upgrades" exclusion to block disruptive changes
# This allows security patches on control plane but blocks node upgrades
gcloud container clusters update foundation-training \
  --zone us-central1-a \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Set conservative disruption intervals for ultimate control
gcloud container clusters update foundation-training \
  --zone us-central1-a \
  --maintenance-patch-version-disruption-interval=7776000s \
  --maintenance-minor-version-disruption-interval=7776000s
```

**Key insight:** The `--enable-autoupgrade=false` flag on the node pool is deprecated. Instead, the cluster-level "no minor or node upgrades" exclusion provides the same protection while allowing you to manually trigger upgrades when needed.

## Inference Node Pool (Optional)

```bash
# Separate pool for inference workloads with different upgrade tolerance
gcloud container node-pools create h100-inference \
  --cluster foundation-training \
  --zone us-central1-a \
  --machine-type a3-highgpu-8g \
  --accelerator type=nvidia-h100-80gb,count=8 \
  --num-nodes 2 \
  --enable-autoscaling \
  --min-nodes 1 \
  --max-nodes 8 \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1 \
  --node-labels workload=inference,gpu=h100
```

## Training Workload Protection

```yaml
# PDB for training jobs (allows 0 disruptions during active training)
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
  namespace: training
spec:
  minAvailable: 100%
  selector:
    matchLabels:
      workload: foundation-training
---
# Training job with extended termination grace period
apiVersion: batch/v1
kind: Job
metadata:
  name: foundation-model-training
  namespace: training
spec:
  template:
    metadata:
      annotations:
        cluster-autoscaler.kubernetes.io/safe-to-evict: "false"
      labels:
        workload: foundation-training
    spec:
      terminationGracePeriodSeconds: 3600  # 1 hour for checkpointing
      tolerations:
      - key: training
        operator: Equal
        value: "true"
        effect: NoSchedule
      nodeSelector:
        workload: training
        gpu: h100
      containers:
      - name: trainer
        image: nvcr.io/nvidia/pytorch:24.01-py3
        resources:
          requests:
            nvidia.com/gpu: 8
          limits:
            nvidia.com/gpu: 8
```

## Upgrade Strategy for AI Workloads

### During Active Training (Weeks 1-4 of a training run)
- Maintenance exclusion blocks all node upgrades
- Only control plane security patches are applied
- Training continues uninterrupted

### Training Gap Windows (Between training runs)
```bash
# Remove exclusion temporarily to allow manual upgrades
gcloud container clusters update foundation-training \
  --zone us-central1-a \
  --remove-maintenance-exclusion-name "no-minor-or-node-upgrades"

# Manual node pool upgrade with parallel host maintenance strategy
# Scale training workloads to zero first
kubectl scale deployment training-workload --replicas=0 -n training

# Trigger upgrade (will use maxUnavailable=1, draining nodes one at a time)
gcloud container node-pools upgrade h100-training \
  --cluster foundation-training \
  --zone us-central1-a \
  --cluster-version TARGET_VERSION

# Re-apply exclusion after upgrade
gcloud container clusters update foundation-training \
  --zone us-central1-a \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## GPU-Specific Considerations

### H100 Node Pool Upgrade Settings
- **maxSurge=0, maxUnavailable=1**: No surge GPU capacity available with fixed reservations
- **maxUnavailable** is your primary lever for upgrade speed vs. disruption trade-off
- Compact placement policy ensures RDMA topology is preserved during upgrades

### GPU Driver Validation
```bash
# Before any upgrade, validate in staging
gcloud container node-pools create h100-staging \
  --cluster staging-cluster \
  --zone us-central1-a \
  --machine-type a3-highgpu-8g \
  --accelerator type=nvidia-h100-80gb,count=8 \
  --cluster-version TARGET_VERSION \
  --num-nodes 1

# Test driver compatibility
kubectl run gpu-test --image=nvidia/cuda:12.3-runtime-ubuntu22.04 --restart=Never --rm -it \
  -- nvidia-smi
```

### Host Maintenance for H100 Nodes
H100 nodes require periodic host maintenance (~4 hours per update). Use the parallel strategy for training workloads:

1. **Checkpoint training state**
2. **Scale workloads to zero**
3. **Apply maintenance label to all nodes simultaneously**:
   ```bash
   kubectl label nodes -l workload=training cloud.google.com/perform-maintenance=true
   ```
4. **Wait for maintenance completion (~4 hours)**
5. **Restart training from checkpoint**

## Security vs. Training Balance

This configuration provides:
- **Security**: Control plane gets security patches automatically
- **Training protection**: Node upgrades blocked during active training
- **Flexibility**: Manual upgrades during planned gaps
- **Extended support**: 24-month version lifecycle
- **Cost optimization**: Extended channel cost only applies during months 15-24

## Monitoring and Alerting

```bash
# Enable scheduled upgrade notifications (72h advance notice)
gcloud container clusters update foundation-training \
  --zone us-central1-a \
  --enable-scheduled-upgrades

# Monitor for upgrade events via Cloud Logging
gcloud logging read 'resource.type="gke_cluster" 
  protoPayload.metadata.operationType=~"(UPGRADE_MASTER|UPGRADE_NODES)"
  resource.labels.cluster_name="foundation-training"'
```

## Operational Workflow

### Monthly Security Review
- Check for available patches via `gcloud container get-server-config`
- Control plane patches auto-apply during Saturday 2-8 AM window
- Review security bulletins and assess urgency

### Quarterly Training Campaigns
- Apply "no upgrades" exclusion 48 hours before training start
- Run 4-6 week training campaigns with zero disruption
- Remove exclusions during 1-2 week gaps between campaigns
- Manually upgrade nodes during gaps using staging validation

### Annual Major Upgrades
- Extended channel provides 24-month runway
- Plan major version upgrades during extended training breaks (holidays)
- Use the two-step control plane upgrade for rollback safety

This configuration maximizes training stability while maintaining reasonable security posture through automated control plane patching and manual node upgrades during planned windows.