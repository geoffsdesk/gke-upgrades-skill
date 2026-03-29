# GKE Cluster Configuration for Foundation Model Training

## Executive Summary
For multi-week H100 training runs, you need **Extended release channel** with aggressive maintenance exclusions, dedicated training node pools, and custom upgrade orchestration. The key is separating training infrastructure from other workloads to prevent any automated disruption during training campaigns.

## Recommended Cluster Configuration

### Release Channel & Auto-upgrade Controls
```bash
# Create cluster on Extended channel with maximum upgrade control
gcloud container clusters create foundation-training \
    --zone us-central1-a \
    --release-channel extended \
    --maintenance-window-start "2024-03-01T03:00:00Z" \
    --maintenance-window-duration 6h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA" \
    --maintenance-minor-version-disruption-interval=7776000s \
    --maintenance-patch-version-disruption-interval=2592000s \
    --send-scheduled-upgrade-notifications \
    --enable-ip-alias \
    --enable-shielded-nodes \
    --logging=SYSTEM,WORKLOAD \
    --monitoring=SYSTEM
```

**Why Extended channel:**
- Up to 24 months version support (no forced minor upgrades except at end of extended support)  
- Minor version upgrades are NOT automated - you control when they happen
- Only patches are auto-applied (security fixes)
- Additional cost only during extended support period (months 15-24)

### Training-Specific Maintenance Exclusions
```bash
# Block ALL upgrades on training pools during campaigns
gcloud container clusters update foundation-training \
    --zone us-central1-a \
    --add-maintenance-exclusion-name "training-freeze-q1" \
    --add-maintenance-exclusion-start-time "2024-03-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-03-31T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades

# For ongoing protection: persistent exclusion that tracks EoS
gcloud container clusters update foundation-training \
    --zone us-central1-a \
    --add-maintenance-exclusion-name "training-protection" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

## Node Pool Architecture

### Dedicated Training Pool (H100)
```bash
# H100 training pool - maximum isolation
gcloud container node-pools create h100-training \
    --cluster foundation-training \
    --zone us-central1-a \
    --machine-type a3-highgpu-8g \
    --accelerator type=nvidia-h100-80gb,count=8 \
    --num-nodes 8 \
    --enable-autoscaling \
    --min-nodes 0 \
    --max-nodes 64 \
    --disk-type pd-ssd \
    --disk-size 200GB \
    --placement-type COMPACT \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 1 \
    --node-taints training=true:NoSchedule \
    --node-labels workload-type=training,gpu-type=h100 \
    --enable-gvnic
```

**Key H100 training considerations:**
- **Fixed reservation required** - H100s have no surge capacity, so `maxSurge=0` is mandatory
- **`maxUnavailable=1`** - only lever for GPU pools with fixed reservations  
- **Compact placement** - preserves RDMA topology across upgrades
- **Node taints** - prevents non-training workloads from landing here
- **GVNIC enabled** - required for GPUDirect-TCPX performance

### Support Infrastructure Pool
```bash
# Separate pool for monitoring, logging, checkpointing services
gcloud container node-pools create infrastructure \
    --cluster foundation-training \
    --zone us-central1-a \
    --machine-type c2-standard-16 \
    --num-nodes 2 \
    --enable-autoscaling \
    --min-nodes 1 \
    --max-nodes 10 \
    --max-surge-upgrade 1 \
    --max-unavailable-upgrade 0 \
    --node-labels workload-type=infrastructure
```

## Training Workload Protection Strategy

### PDB Configuration
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
  namespace: training
spec:
  selector:
    matchLabels:
      app: foundation-model-training
  minAvailable: 100%  # Prevent ANY pod eviction during training
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: foundation-model-training
spec:
  replicas: 8
  template:
    spec:
      terminationGracePeriodSeconds: 86400  # 24 hours for checkpointing
      tolerations:
      - key: training
        operator: Equal
        value: "true"
        effect: NoSchedule
      nodeSelector:
        workload-type: training
```

### Checkpointing Integration
```yaml
# Environment variables for training container
env:
- name: CHECKPOINT_INTERVAL
  value: "3600"  # Checkpoint every hour
- name: CHECKPOINT_PATH
  value: "/gcs-fuse/checkpoints"
- name: PREEMPTION_HANDLER
  value: "true"
```

## AI Host Maintenance Strategy

For H100 clusters, use **parallel host maintenance** during planned gaps:

### Scheduled Maintenance (between training runs)
```bash
# Cordon all training nodes
kubectl cordon -l workload-type=training

# Wait for current training job to complete or checkpoint
# Then trigger host maintenance on all H100 nodes simultaneously
kubectl label nodes -l workload-type=training \
    cloud.google.com/perform-maintenance=true

# Monitor maintenance progress (~4 hours)
kubectl get nodes -l workload-type=training \
    -o custom-columns=NAME:.metadata.name,STATUS:.status.conditions[-1].type,READY:.status.conditions[-1].status
```

### Emergency Maintenance (mid-training)
```bash
# Scale training deployment to 0 (triggers checkpoint save)
kubectl scale deployment foundation-model-training --replicas=0 -n training

# Wait for checkpoint completion, then proceed with maintenance
# Training will resume from checkpoint after maintenance
```

## Multi-Environment Strategy

### Development/Staging Clusters
```bash
# Dev cluster on Regular channel for faster iteration
gcloud container clusters create foundation-dev \
    --zone us-central1-b \
    --release-channel regular \
    --machine-type a2-highgpu-1g \  # Smaller GPU instances for dev
    --accelerator type=nvidia-a100-80gb,count=1
```

### Channel Progression Pattern
- **Dev**: Regular channel (faster access to new features)
- **Staging**: Regular channel with "no minor" exclusion  
- **Production**: Extended channel with comprehensive exclusions

## Security & Compliance

### Patch Management Balance
```bash
# Allow control plane security patches while blocking disruptive upgrades
gcloud container clusters update foundation-training \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support

# Enable accelerated patch updates for faster security fixes
gcloud container clusters update foundation-training \
    --patch-update accelerated
```

### Monitoring & Alerting
```yaml
# Alert on upgrade notifications
resource.type="gke_cluster"
protoPayload.methodName="google.container.v1.ClusterManager.SetMaintenancePolicy"
resource.labels.cluster_name="foundation-training"
```

## Operational Runbook

### Pre-Training Checklist
```
Training Campaign Start
- [ ] Apply "no upgrades" maintenance exclusion for campaign duration
- [ ] Verify H100 node pool has no pending upgrades
- [ ] Confirm checkpoint storage (GCS) is accessible
- [ ] Scale infrastructure monitoring services
- [ ] Alert on-call team of training start
```

### Training-Safe Upgrade Windows
```
Safe Upgrade Schedule
- Between training campaigns (2-3 day gaps)  
- During model evaluation phases (1-2 days)
- Planned maintenance windows (weekends)
- Never during active training (multi-week periods)
```

### Version Planning Timeline
```
Quarterly Upgrade Cycle
Month 1: Plan & test upgrades in dev/staging
Month 2: Execute production upgrades during training gaps  
Month 3: Extended training campaigns with upgrade freeze
```

## Cost Optimization Notes

- **Extended channel cost**: Additional cost only during months 15-24 of version lifecycle
- **Reserved H100 capacity**: Required for training predictability, no surge overhead
- **Preemptible infrastructure nodes**: Use for non-critical services to reduce costs
- **Auto-scaling to zero**: Scale training pools to 0 between campaigns

This configuration gives you maximum control over disruptions while maintaining security patches on the control plane. The Extended channel + maintenance exclusions + dedicated node pools pattern is specifically designed for disruption-intolerant AI workloads.