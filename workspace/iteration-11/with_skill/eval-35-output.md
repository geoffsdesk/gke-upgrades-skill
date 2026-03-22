# GKE Foundation Model Training Cluster Configuration

## Executive Summary

For multi-week H100 training runs, you need **maximum upgrade control** while maintaining security. The key is using GKE's Extended release channel with "no minor or node upgrades" exclusions, dedicated training node pools with auto-upgrade disabled, and parallel host maintenance strategy.

## Cluster Configuration

### Release Channel Strategy
```bash
# Use Extended channel for maximum control and 24-month support
gcloud container clusters create training-cluster \
  --release-channel extended \
  --zone us-central1-a \
  --machine-type e2-standard-4 \
  --num-nodes 1
```

**Why Extended channel:**
- Up to 24 months of support (vs 14 months for Regular/Stable)
- Minor version upgrades are NOT automated (you control timing)
- Only patches are auto-applied during standard support period
- Full SLA coverage
- Better for compliance and slow upgrade cycles

### Maintenance Exclusions (Critical)
```bash
# Add persistent "no minor or node upgrades" exclusion
gcloud container clusters update training-cluster \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**This exclusion:**
- Blocks ALL node pool upgrades during training campaigns
- Blocks minor version upgrades on control plane
- Still allows critical security patches on control plane
- Automatically tracks End of Support dates
- No 6-month renewal needed

### Maintenance Windows
```bash
# Set maintenance window during planned gaps (Sunday 2-6 AM)
gcloud container clusters update training-cluster \
  --zone us-central1-a \
  --maintenance-window-start "2024-01-07T02:00:00Z" \
  --maintenance-window-duration "4h" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"

# Add disruption interval controls
gcloud container clusters update training-cluster \
  --zone us-central1-a \
  --maintenance-patch-version-disruption-interval 30 \
  --maintenance-minor-version-disruption-interval 90
```

## Node Pool Architecture

### Dedicated Training Pool (H100s)
```bash
# Create H100 training pool with auto-upgrade DISABLED
gcloud container node-pools create h100-training \
  --cluster training-cluster \
  --zone us-central1-a \
  --machine-type a3-highgpu-8g \
  --accelerator type=nvidia-h100-80gb,count=8 \
  --num-nodes 16 \
  --enable-autoupgrade=false \
  --enable-autorepair=true \
  --placement-type COMPACT \
  --placement-policy-name training-placement-policy
```

### Inference/Services Pool (Separate)
```bash
# Create separate pool for inference workloads (can auto-upgrade)
gcloud container node-pools create inference-pool \
  --cluster training-cluster \
  --zone us-central1-a \
  --machine-type n1-standard-16 \
  --num-nodes 4 \
  --enable-autoupgrade \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

**Key separation benefits:**
- Training pool frozen during campaigns
- Inference pool gets security updates
- Different upgrade strategies per workload type
- Cost optimization (training nodes only when needed)

## H100-Specific Upgrade Strategy

### Host Maintenance Strategy
```bash
# For multi-week training: use parallel maintenance during planned gaps
# Scale training to zero, checkpoint, then:
kubectl label nodes -l cloud.google.com/gke-nodepool=h100-training \
  cloud.google.com/perform-maintenance=true

# This triggers ~4 hour host maintenance on ALL H100 nodes simultaneously
# Best for training workloads that can tolerate full restart
```

### GPU-Specific Considerations

**No surge capacity available:**
- H100 reservations are typically fixed-size
- Use `maxUnavailable` mode: `maxSurge=0, maxUnavailable=4`
- This creates capacity dips but requires no extra GPUs

**Driver version coupling:**
```bash
# Before any upgrade, test driver compatibility in staging
gcloud container clusters create staging-training \
  --cluster-version TARGET_VERSION \
  --zone us-central1-b \
  --machine-type a3-highgpu-8g \
  --accelerator type=nvidia-h100-80gb,count=8 \
  --num-nodes 1

# Verify CUDA version and framework compatibility
kubectl run cuda-test --image=nvidia/cuda:12.0-runtime-ubuntu20.04 \
  --restart=Never --rm -it -- nvidia-smi
```

## Training Job Protection

### PodDisruptionBudgets
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-job-pdb
spec:
  minAvailable: 100%  # Block ALL evictions
  selector:
    matchLabels:
      workload-type: foundation-training
```

### Checkpointing Strategy
```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: foundation-training
spec:
  template:
    spec:
      containers:
      - name: trainer
        env:
        - name: CHECKPOINT_INTERVAL
          value: "3600"  # Checkpoint every hour
        - name: CHECKPOINT_PATH
          value: "/mnt/checkpoints"
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /mnt/checkpoints
  volumeClaimTemplates:
  - metadata:
      name: checkpoint-storage
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 1Ti  # Size for model checkpoints
```

### Pre-Upgrade Training Workflow
```bash
# 1. Prepare for maintenance window
kubectl scale statefulset foundation-training --replicas=0

# 2. Verify checkpoint saved
gsutil ls gs://training-checkpoints/latest/

# 3. Apply temporary "no upgrades" exclusion if emergency delay needed
gcloud container clusters update training-cluster \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "emergency-freeze" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades

# 4. Proceed with maintenance
```

## Multi-Cluster Strategy

### Environment Progression
```bash
# Dev cluster: Regular channel (faster patches)
gcloud container clusters create training-dev \
  --release-channel regular \
  --zone us-central1-b

# Staging cluster: Extended channel (matches prod)
gcloud container clusters create training-staging \
  --release-channel extended \
  --zone us-central1-c

# Production cluster: Extended channel with exclusions
# (Already configured above)
```

### Version Testing Pipeline
```bash
# Test new GKE versions in staging before prod
# 1. Check available versions
gcloud container get-server-config --zone us-central1-c \
  --format="value(channels.EXTENDED.validVersions[0])"

# 2. Upgrade staging control plane
gcloud container clusters upgrade training-staging \
  --zone us-central1-c \
  --master \
  --cluster-version NEW_VERSION

# 3. Test H100 driver compatibility
# 4. If successful, plan prod upgrade during next training gap
```

## Monitoring and Alerting

### Upgrade Status Monitoring
```bash
# Check auto-upgrade status programmatically
gcloud container clusters get-upgrade-info training-cluster --zone us-central1-a
```

### Training Job Alerts
```yaml
# Cloud Monitoring alert for training job evictions
alertPolicy:
  displayName: "Training Job Evicted"
  conditions:
  - displayName: "Pod eviction detected"
    conditionThreshold:
      filter: 'resource.type="k8s_pod" AND resource.labels.pod_name=~"foundation-training-.*"'
      comparison: COMPARISON_GREATER_THAN
      thresholdValue: 0
  notificationChannels:
  - "projects/PROJECT/notificationChannels/TRAINING_TEAM"
```

## Timeline and Planning

### Quarterly Upgrade Schedule
```
Q1: Staging upgrade + validation (4 weeks)
Q2: Production upgrade during training campaign gap (2 weeks)
Q3: Staging upgrade + validation (4 weeks)  
Q4: Production upgrade OR delay until Q1 (training-dependent)
```

### Emergency Patch Strategy
```bash
# For critical security issues, use emergency maintenance window
gcloud container clusters update training-cluster \
  --zone us-central1-a \
  --clear-maintenance-policy

# Apply patch immediately, then restore policy
```

## Key Recommendations

1. **Extended release channel** - 24-month support, manual minor upgrades
2. **Persistent maintenance exclusions** - "no minor or node upgrades" scope  
3. **Dedicated training node pool** - auto-upgrade disabled, separate from inference
4. **Parallel host maintenance** - all H100s updated simultaneously during gaps
5. **Aggressive checkpointing** - hourly saves to survive unexpected maintenance
6. **Staging validation** - test every GKE version before production
7. **Emergency exclusions** - 30-day "no upgrades" scope for critical periods

This configuration gives you maximum protection for multi-week training runs while maintaining security through control plane patches. The Extended channel eliminates unexpected minor upgrades, and the dedicated training pool architecture lets you freeze GPU nodes while keeping other workloads current.