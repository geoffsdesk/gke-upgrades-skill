# GKE Configuration for Foundation Model Training

## Core Configuration Strategy

For foundation model training with multi-week runs, use **Extended release channel with comprehensive upgrade controls**. This provides maximum flexibility around version lifecycle while maintaining security patches.

## Cluster Configuration

```bash
# Create cluster optimized for training workloads
gcloud container clusters create foundation-training \
    --location us-central1 \
    --release-channel extended \
    --enable-ip-alias \
    --enable-network-policy \
    --num-nodes 0 \
    --enable-autoscaling \
    --enable-autorepair \
    --enable-autoupgrade \
    --maintenance-window-start "2024-01-01T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support \
    --maintenance-patch-version-disruption-interval 7776000s \
    --enable-scheduled-upgrades
```

## GPU Node Pool Strategy

Create **separate node pools for training vs inference** to enable independent upgrade control:

```bash
# Training node pool - maximum control
gcloud container node-pools create training-h100 \
    --cluster foundation-training \
    --location us-central1 \
    --machine-type a3-highgpu-8g \
    --accelerator type=nvidia-h100-80gb,count=8 \
    --num-nodes 8 \
    --enable-autoscaling \
    --min-nodes 0 \
    --max-nodes 32 \
    --node-taints=workload=training:NoSchedule \
    --node-labels=workload=training,node-type=h100 \
    --disk-type pd-ssd \
    --disk-size 200GB \
    --enable-autorepair \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 1 \
    --reservation-affinity consume \
    --reservation TRAINING_RESERVATION_NAME

# Inference node pool - more flexible
gcloud container node-pools create inference-h100 \
    --cluster foundation-training \
    --location us-central1 \
    --machine-type a3-highgpu-8g \
    --accelerator type=nvidia-h100-80gb,count=8 \
    --num-nodes 2 \
    --enable-autoscaling \
    --min-nodes 1 \
    --max-nodes 8 \
    --node-taints=workload=inference:NoSchedule \
    --node-labels=workload=inference,node-type=h100 \
    --enable-autorepair \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 1 \
    --strategy AUTOSCALED_BLUE_GREEN \
    --autoscaled-rollout-policy blue-green-initial-node-percentage=0.25
```

## Upgrade Protection Strategy

### 1. Extended Channel Benefits
- **24-month support period** vs 14-month standard
- **No automatic minor version upgrades** on control plane (except at EoS)
- **Manual control over when minor upgrades happen**
- **Patches arrive at same timing as Regular channel** (no delay)

### 2. Maintenance Exclusion Configuration
```bash
# "No minor or node upgrades" exclusion provides maximum control:
# ✅ Control plane security patches auto-applied
# ❌ Control plane minor upgrades blocked (manual only)  
# ❌ Node pool upgrades blocked (manual only)
# ✅ Tracks End of Support automatically
```

### 3. Patch Disruption Control
- **90-day patch interval**: Only allows CP patches every 90 days max
- **Sunday 2-6 AM maintenance window**: Predictable timing for any patches
- **72-hour advance notifications**: Via scheduled upgrade notifications

## GPU-Specific Upgrade Settings

### Training Pool Strategy
```bash
# GPU training pools: maxUnavailable is the ONLY effective lever
# Fixed reservations have NO surge capacity available
--max-surge-upgrade 0 \
--max-unavailable-upgrade 1

# For faster upgrades during planned maintenance windows:
--max-unavailable-upgrade 2  # Only if workload tolerates 2-node capacity loss
```

### Why Autoscaled Blue-Green for Inference
- **No force-eviction after 1 hour** (unlike surge)
- **Respects longer terminationGracePeriodSeconds**
- **Cost-efficient** - scales down old pool as new scales up
- **Better for serving workloads** that need graceful transitions

## Training Job Protection

### 1. Checkpointing Requirements
```yaml
# Training job manifest requirements
apiVersion: batch/v1
kind: Job
metadata:
  name: foundation-training
spec:
  template:
    metadata:
      annotations:
        cluster-autoscaler.kubernetes.io/safe-to-evict: "false"
    spec:
      terminationGracePeriodSeconds: 3600  # 1 hour for checkpoint
      tolerations:
      - key: "workload"
        operator: "Equal"
        value: "training"
        effect: "NoSchedule"
      containers:
      - name: trainer
        env:
        - name: CHECKPOINT_INTERVAL
          value: "3600"  # Checkpoint every hour
        - name: CHECKPOINT_PATH
          value: "/checkpoints"
```

### 2. PDB for Training Jobs
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
spec:
  minAvailable: 7  # Allow 1 node down for maintenance in 8-node training
  selector:
    matchLabels:
      workload: training
```

## Operational Procedures

### Pre-Training Campaign Checklist
```markdown
- [ ] Verify cluster on Extended channel
- [ ] Confirm "no minor or node upgrades" exclusion active
- [ ] Check upcoming maintenance windows don't conflict with training schedule
- [ ] Validate checkpoint/resume functionality in staging
- [ ] Apply temporary "no upgrades" exclusion for training duration if needed:

```bash
# For critical training campaigns, block ALL upgrades temporarily
gcloud container clusters update foundation-training \
    --add-maintenance-exclusion-name "training-campaign-dec" \
    --add-maintenance-exclusion-start "2024-12-01T00:00:00Z" \
    --add-maintenance-exclusion-end "2024-12-31T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
```

### Manual Upgrade Workflow (Between Training Campaigns)
```bash
# 1. Wait for training gap
# 2. Trigger control plane upgrade manually
gcloud container clusters upgrade foundation-training \
    --master \
    --cluster-version TARGET_VERSION

# 3. Stage node pool upgrades (inference first, training last)
gcloud container node-pools upgrade inference-h100 \
    --cluster foundation-training \
    --cluster-version TARGET_VERSION

# 4. Training pool upgrade during planned maintenance window
gcloud container node-pools upgrade training-h100 \
    --cluster foundation-training \
    --cluster-version TARGET_VERSION
```

## GPU Driver Compatibility Validation

**Critical**: Always test GPU driver compatibility before production upgrades:

```bash
# Create staging training pool with target version
gcloud container node-pools create training-h100-staging \
    --cluster foundation-training \
    --machine-type a3-highgpu-8g \
    --accelerator type=nvidia-h100-80gb,count=8 \
    --cluster-version TARGET_VERSION \
    --num-nodes 1

# Test training workload on staging pool
kubectl run gpu-test --image=nvidia/cuda:12.0-devel-ubuntu20.04 \
    --limits=nvidia.com/gpu=1 \
    --node-selector=cloud.google.com/gke-nodepool=training-h100-staging \
    -- nvidia-smi

# Validate CUDA version compatibility with your training framework
```

## Monitoring and Alerting

```bash
# Set up upgrade notification monitoring
gcloud logging sinks create gke-upgrade-notifications \
    bigquery.googleapis.com/projects/PROJECT_ID/datasets/gke_events \
    --log-filter='resource.type="gke_cluster" 
                 protoPayload.methodName="google.container.v1.ClusterManager.UpdateCluster"'

# Monitor training job health during any maintenance
kubectl create -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: training-health-check
data:
  check.sh: |
    #!/bin/bash
    # Monitor training job pod count and GPU utilization
    kubectl get pods -l workload=training --field-selector=status.phase=Running
    kubectl exec -it $(kubectl get pods -l workload=training -o name | head -1) -- nvidia-smi
EOF
```

## Key Benefits of This Configuration

1. **Maximum upgrade control**: Extended channel + "no minor or node upgrades" exclusion gives you complete control over when disruptive changes happen

2. **Security maintained**: Control plane patches auto-apply (with 90-day max frequency) but won't disrupt training jobs

3. **Cost optimization**: Separate pools allow scaling training to zero during gaps while maintaining inference capacity

4. **GPU-optimized**: maxUnavailable strategy works within fixed GPU reservations; autoscaled blue-green for serving workloads

5. **Training protection**: PDBs, checkpointing, safe-to-evict annotations, and maintenance exclusions protect multi-week runs

6. **Predictable timing**: Sunday maintenance windows + 72h notifications provide advance warning

This configuration prioritizes training continuity while maintaining security posture through automated control plane patching. Manual minor upgrades happen only during planned training gaps.