# GKE AI Training Cluster: Upgrade Strategy & Configuration

## Recommended Configuration

### Release Channel Strategy
**Extended release channel** — Critical for AI workloads
- 24-month support lifecycle vs 14 months on other channels
- Same auto-upgrade behavior as Regular/Stable during standard support period
- Extended support phase: only patches auto-applied, minor upgrades are manual
- Balances security (automatic patches) with stability (controlled minor upgrades)
- Additional cost only applies during extended support period (months 15-24)

### Maintenance Configuration

```bash
# Primary cluster configuration
gcloud container clusters create ai-training-cluster \
  --zone us-central1-a \
  --release-channel extended \
  --machine-type n1-standard-4 \
  --num-nodes 3 \
  --enable-autoscaling --min-nodes 1 --max-nodes 5 \
  --maintenance-window-start "2024-01-13T10:00:00Z" \
  --maintenance-window-end "2024-01-13T14:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA" \
  --maintenance-patch-version-disruption-interval 30 \
  --maintenance-minor-version-disruption-interval 60

# Persistent maintenance exclusion (tracks EoS automatically)
gcloud container clusters update ai-training-cluster \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "protect-training-workloads" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Key maintenance settings:**
- **"No minor or node upgrades" exclusion**: Blocks disruptive upgrades while allowing security patches on control plane
- **Persistent exclusion**: Auto-renews at EoS, no 6-month limit
- **Extended disruption intervals**: 30-day patch interval, 60-day minor interval to reduce upgrade frequency
- **Weekend maintenance window**: Aligns with training gaps

### Node Pool Architecture

**Dual node pool strategy** — Separate training and system workloads:

```bash
# H100 training pool (upgrade protection)
gcloud container node-pools create training-pool \
  --cluster ai-training-cluster \
  --zone us-central1-a \
  --machine-type a3-highgpu-8g \
  --accelerator type=nvidia-h100-80gb,count=8 \
  --num-nodes 8 \
  --node-locations us-central1-a \
  --placement-type COMPACT \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1 \
  --enable-autoupgrade=false

# System/inference pool (normal upgrade behavior)
gcloud container node-pools create system-pool \
  --cluster ai-training-cluster \
  --zone us-central1-a \
  --machine-type n1-standard-8 \
  --num-nodes 2 \
  --enable-autoscaling --min-nodes 1 --max-nodes 10 \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

**Training pool key settings:**
- **Auto-upgrade disabled**: Manual control over when GPU nodes upgrade
- **maxUnavailable=1, maxSurge=0**: GPU reservations typically have no surge capacity
- **Compact placement**: Preserves RDMA topology for multi-node training
- **Fixed size**: No autoscaling to maintain consistent training environment

### Network Configuration for High-Performance Training

```bash
# VPC with high MTU for RDMA traffic
gcloud compute networks create ai-training-vpc --subnet-mode custom --mtu 8896

gcloud compute networks subnets create ai-training-subnet \
  --network ai-training-vpc \
  --range 10.0.0.0/16 \
  --region us-central1 \
  --enable-ip-alias \
  --secondary-range pods=10.1.0.0/16,services=10.2.0.0/16

# Cluster with GPUDirect support
gcloud container clusters create ai-training-cluster \
  --zone us-central1-a \
  --network ai-training-vpc \
  --subnetwork ai-training-subnet \
  --enable-ip-alias \
  --cluster-secondary-range-name pods \
  --services-secondary-range-name services \
  --enable-network-policy \
  --cluster-version 1.31.2-gke.1503000  # GPUDirect requires 1.27.7-gke.1121000+
```

## Training Workload Protection Strategy

### 1. Maintenance Exclusions During Active Training

```bash
# Before starting a multi-week training run
gcloud container clusters update ai-training-cluster \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "llm-pretraining-campaign-q1" \
  --add-maintenance-exclusion-start-time "2024-02-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-02-28T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**30-day rotation pattern**: Chain exclusions for longer campaigns, plan 2-day gaps for emergency patching.

### 2. Dedicated Training Pod Configuration

```yaml
# training-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: llm-pretraining
  namespace: training
spec:
  template:
    spec:
      nodeSelector:
        cloud.google.com/gke-nodepool: training-pool
      tolerations:
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule
      containers:
      - name: trainer
        image: gcr.io/project/llm-trainer:latest
        resources:
          requests:
            nvidia.com/gpu: 8
            cpu: 100
            memory: 1400Gi
          limits:
            nvidia.com/gpu: 8
            cpu: 100
            memory: 1400Gi
        terminationGracePeriodSeconds: 3600  # Allow checkpoint save
      restartPolicy: Never
      # Critical: PDB protection
      podDisruptionBudget:
        minAvailable: 100%  # Prevent any eviction during training
```

### 3. Checkpoint Strategy Integration

```bash
# Training script integration
#!/bin/bash
# Handle SIGTERM gracefully - save checkpoint and exit
trap 'echo "Received SIGTERM, saving checkpoint..."; save_checkpoint(); exit 0' SIGTERM

# Run training with periodic checkpointing
python train.py \
  --checkpoint-frequency 3600 \  # Every hour
  --checkpoint-path /mnt/gcs-bucket/checkpoints \
  --resume-from-checkpoint /mnt/gcs-bucket/checkpoints/latest
```

## Scheduled Upgrade Windows

### Quarterly Maintenance Planning

```bash
# Q1 maintenance window (between training campaigns)
gcloud container clusters update ai-training-cluster \
  --zone us-central1-a \
  --remove-maintenance-exclusion-name "llm-pretraining-campaign-q1"

# Manually trigger node pool upgrade during gap
gcloud container node-pools upgrade training-pool \
  --cluster ai-training-cluster \
  --zone us-central1-a \
  --cluster-version 1.31.3-gke.1506000  # Target version

# Verify GPU driver compatibility
kubectl create job gpu-test --image=tensorflow/tensorflow:latest-gpu \
  -- python -c "import tensorflow as tf; print(tf.config.list_physical_devices('GPU'))"
```

**Maintenance calendar approach:**
- **Week 1**: Update system pool, validate non-training workloads
- **Week 2**: Update training pool during scheduled gap
- **Week 3**: Full system validation, driver testing
- **Week 4**: Buffer week, rollback window if issues

### GPU Driver Version Management

```bash
# Check current driver version
kubectl get nodes -o jsonpath='{.items[*].status.nodeInfo.kubeletVersion}' | xargs -n1 gcloud container get-server-config --zone us-central1-a --format="yaml(channels.EXTENDED.validMasterVersions)"

# Verify CUDA compatibility in staging
gcloud container clusters create gpu-test-staging \
  --zone us-central1-b \
  --cluster-version TARGET_VERSION \
  --machine-type a3-highgpu-8g \
  --num-nodes 1

kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: cuda-test
spec:
  containers:
  - name: cuda-test
    image: nvidia/cuda:12.3-runtime-ubuntu22.04
    command: ["nvidia-smi"]
    resources:
      limits:
        nvidia.com/gpu: 1
EOF
```

## Monitoring & Alerting

### Upgrade-Aware Monitoring

```yaml
# upgrade-monitoring.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-alerts
data:
  rules.yaml: |
    groups:
    - name: gke-upgrade-protection
      rules:
      - alert: UnplannedNodeDrain
        expr: increase(kube_node_spec_unschedulable[5m]) > 0
        labels:
          severity: critical
          team: ml-platform
        annotations:
          summary: "Node drain detected - potential unplanned upgrade"
          
      - alert: TrainingJobEvicted
        expr: increase(kube_pod_container_status_restarts_total{namespace="training"}[5m]) > 0
        labels:
          severity: critical
        annotations:
          summary: "Training pod restarted - check for upgrade interference"
          
      - alert: GPUNodeVersionDrift
        expr: count(kube_node_info{node=~".*training-pool.*"}) by (kubelet_version) > 1
        labels:
          severity: warning
        annotations:
          summary: "GPU nodes running different versions - upgrade in progress"
```

### Training Job Integration

```python
# training_monitor.py - Integration with GKE upgrade awareness
import kubernetes.client as k8s

def check_upgrade_risk():
    """Check if cluster upgrade might interrupt training"""
    v1 = k8s.CoreV1Api()
    
    # Check for cordoned nodes in training pool
    nodes = v1.list_node(label_selector="cloud.google.com/gke-nodepool=training-pool")
    cordoned_nodes = [n for n in nodes.items if n.spec.unschedulable]
    
    if cordoned_nodes:
        print("WARNING: Training nodes cordoned - possible upgrade in progress")
        return True
    
    # Check maintenance exclusions
    # (Would integrate with GKE API to check current exclusions)
    return False

def training_loop():
    while True:
        if check_upgrade_risk():
            save_checkpoint()
            print("Checkpoint saved due to upgrade risk")
        
        # Continue training...
```

## Security & Compliance Balance

### Automated Security Patching

The Extended channel + "no minor or node upgrades" exclusion strategy provides:
- ✅ **Control plane security patches**: Auto-applied within maintenance windows
- ✅ **Node security patches**: Available but controlled (applied during training gaps)
- ✅ **EoS protection**: Extended support prevents forced upgrades
- ✅ **Compliance**: 24-month support lifecycle meets most enterprise requirements

### Emergency Patch Process

```bash
# For critical security patches during training campaigns
# 1. Evaluate patch criticality
gcloud container get-server-config --zone us-central1-a --format="yaml(channels.EXTENDED.validMasterVersions)"

# 2. Apply to control plane only (if training-sensitive)
gcloud container clusters upgrade ai-training-cluster \
  --zone us-central1-a \
  --master \
  --cluster-version PATCH_VERSION

# 3. Schedule node patch during next training gap
# (Manual process, not auto-applied due to exclusion)
```

## Summary Configuration Checklist

```
✅ Extended release channel for 24-month support lifecycle
✅ "No minor or node upgrades" persistent exclusion (allows CP patches)
✅ Dedicated training node pool with auto-upgrade disabled
✅ System node pool with normal upgrade behavior
✅ Compact placement policy for RDMA topology preservation
✅ maxUnavailable=1 for GPU nodes (assumes no surge capacity)
✅ High-MTU VPC for GPUDirect traffic (8896 MTU)
✅ 30-day patch disruption interval, 60-day minor disruption interval
✅ Weekend maintenance windows aligned with training schedules
✅ PDB protection on training workloads (minAvailable: 100%)
✅ Checkpoint integration with SIGTERM handling
✅ Upgrade-aware monitoring and alerting
✅ Quarterly maintenance planning between training campaigns
```

This configuration maximizes training stability while maintaining security posture. The Extended channel provides the longest runway before forced upgrades, while the exclusion + dual-pool strategy gives you surgical control over when disruptive changes occur.