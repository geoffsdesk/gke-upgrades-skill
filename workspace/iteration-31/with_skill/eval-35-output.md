# GKE Foundation Model Training Cluster Configuration

## Cluster Architecture for AI Training

### Base Configuration
```bash
# Create Extended channel cluster for maximum control
gcloud container clusters create training-cluster \
  --zone us-central1-a \
  --release-channel extended \
  --cluster-version 1.31.3-gke.1146000 \
  --machine-type c2d-standard-16 \
  --num-nodes 3 \
  --enable-ip-alias \
  --enable-network-policy \
  --enable-shielded-nodes \
  --disk-size 100GB \
  --disk-type pd-ssd \
  --workload-pool PROJECT_ID.svc.id.goog \
  --enable-autoscaling \
  --max-nodes 5 \
  --min-nodes 3
```

### Dedicated H100 Training Node Pool
```bash
# Create H100 training pool with upgrade protection
gcloud container node-pools create h100-training \
  --cluster training-cluster \
  --zone us-central1-a \
  --machine-type a3-highgpu-8g \
  --accelerator type=nvidia-h100-80gb,count=8 \
  --num-nodes 4 \
  --disk-size 375GB \
  --disk-type pd-ssd \
  --placement-type COMPACT \
  --placement-policy-name training-placement \
  --enable-autorepair \
  --enable-autoupgrade=false \
  --node-taints nvidia.com/gpu=present:NoSchedule \
  --node-labels workload-type=training,gpu=h100 \
  --reservation-affinity=specific \
  --reservation TRAINING_RESERVATION_NAME
```

## Release Channel Strategy: Extended

**Why Extended Channel for AI Training:**
- **24-month support period** (vs 14 months for other channels) - longer runway between forced upgrades
- **Manual control plane minor upgrades** - auto-upgrades are disabled except at end of extended support
- **Same patch timing as Regular** - security patches arrive promptly, no delay
- **Cost only during extended period** - no extra charge during standard 14-month support
- **Best migration path from "No channel"** - if you're currently freezing versions manually

## Maintenance Configuration for Multi-Week Training Protection

### Core Protection Strategy
```bash
# Configure Extended channel with training-optimized maintenance controls
gcloud container clusters update training-cluster \
  --zone us-central1-a \
  --release-channel extended \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --maintenance-window-start "2024-12-01T04:00:00Z" \
  --maintenance-window-duration 6h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU" \
  --maintenance-patch-version-disruption-interval=7776000s
```

**This configuration provides:**
- ✅ **Control plane security patches** continue automatically (critical for compliance)
- ❌ **No control plane minor upgrades** until you trigger them manually
- ❌ **No node pool upgrades** until you trigger them manually
- ⏰ **Patches limited to once every 90 days** maximum, only during Sunday 4-10 AM window
- 🔒 **Exclusion automatically renews** when new minor versions are adopted

### Training Campaign Freeze (Ultimate Protection)
```bash
# For active multi-week training runs, add complete freeze
gcloud container clusters update training-cluster \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "training-campaign-q1" \
  --add-maintenance-exclusion-start-time "2024-12-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-01-15T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

This blocks **everything** (including patches) for 30 days during critical training. Chain up to 3 exclusions if needed for longer campaigns.

## Node Pool Upgrade Strategy for H100 Clusters

### GPU-Specific Constraints
- **H100 VMs don't support live migration** - every upgrade requires pod restart
- **Fixed reservations have NO surge capacity** - assume maxSurge=0 always
- **maxUnavailable is your ONLY upgrade lever** for GPU pools

### Recommended Strategy: Autoscaled Blue-Green
```bash
# Configure autoscaled blue-green for training pools
gcloud container node-pools update h100-training \
  --cluster training-cluster \
  --zone us-central1-a \
  --strategy=AUTOSCALED_BLUE_GREEN \
  --enable-autoscaling \
  --total-min-nodes 0 \
  --total-max-nodes 8 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=14400s
```

**Why autoscaled blue-green for training:**
- ✅ **No 1-hour eviction timeout** - respects extended terminationGracePeriodSeconds
- ✅ **Cost-efficient** - scales down blue pool as green scales up (no 2x cost)
- ✅ **Training job protection** - jobs can checkpoint gracefully before eviction
- ✅ **GPU reservation friendly** - doesn't require surge capacity

### Alternative: Drain-First Strategy
If autoscaled blue-green isn't available, use:
```bash
gcloud container node-pools update h100-training \
  --cluster training-cluster \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```
This drains nodes completely before creating replacements - zero extra GPU quota needed.

## Training Workload Protection

### Pod-Level Configuration
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: foundation-model-training
  annotations:
    cluster-autoscaler.kubernetes.io/safe-to-evict: "false"
spec:
  terminationGracePeriodSeconds: 3600  # 1 hour for checkpointing
  tolerations:
  - key: nvidia.com/gpu
    operator: Exists
    effect: NoSchedule
  nodeSelector:
    workload-type: training
    gpu: h100
  containers:
  - name: training
    image: gcr.io/PROJECT_ID/training:latest
    resources:
      limits:
        nvidia.com/gpu: 8
        memory: 1000Gi
      requests:
        nvidia.com/gpu: 8
        memory: 1000Gi
        cpu: 96
```

### PDB for Training Jobs
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
spec:
  selector:
    matchLabels:
      workload-type: training
  minAvailable: 1  # Prevents ALL training pods from draining simultaneously
```

## Version and Security Management

### Upgrade Timing Strategy
1. **Quarterly minor upgrades** during scheduled training gaps
2. **Security patches automatically** but rate-limited to 90-day intervals
3. **Test new GKE versions** on a staging H100 cluster first

### Pre-Upgrade Testing Protocol
```bash
# Create staging pool with target version
gcloud container node-pools create h100-staging \
  --cluster training-cluster \
  --zone us-central1-a \
  --machine-type a3-highgpu-8g \
  --accelerator type=nvidia-h100-80gb,count=8 \
  --cluster-version TARGET_VERSION \
  --num-nodes 1

# Test model loading, CUDA compatibility, driver versions
kubectl run test-training \
  --image gcr.io/PROJECT_ID/training:latest \
  --overrides='{"spec":{"nodeSelector":{"cloud.google.com/gke-nodepool":"h100-staging"}}}' \
  --rm -it --restart=Never -- python test_model_loading.py
```

## Monitoring and Alerting

### Upgrade-Related Alerts
```bash
# Monitor for unexpected upgrade operations
gcloud logging sinks create upgrade-alerts \
  bigquery.googleapis.com/projects/PROJECT_ID/datasets/gke_logs \
  --log-filter='resource.type="gke_cluster" 
               protoPayload.metadata.operationType=~"(UPDATE_CLUSTER|UPGRADE_MASTER|UPGRADE_NODES)"'

# Enable scheduled upgrade notifications (72h advance warning)
gcloud container clusters update training-cluster \
  --zone us-central1-a \
  --enable-scheduled-upgrades
```

### Training Job Health Monitoring
- **Checkpoint frequency alerts** - ensure jobs save progress regularly
- **GPU utilization monitoring** - detect stuck or inefficient training
- **Node eviction events** - alert on unexpected pod terminations

## Complete Configuration Summary

```bash
# Final cluster state verification
gcloud container clusters describe training-cluster \
  --zone us-central1-a \
  --format="table(
    name,
    releaseChannel.channel,
    currentMasterVersion,
    maintenancePolicy.window.recurringWindow.window.startTime,
    maintenancePolicy.resourceVersion,
    nodePools[].name,
    nodePools[].version,
    nodePools[].management.autoUpgrade
  )"
```

**Expected output:**
- **Release channel:** Extended
- **Auto-upgrade:** Disabled for H100 pools, controlled via exclusions
- **Maintenance window:** Sunday 4-10 AM
- **Patch disruption interval:** 90 days maximum
- **Node pool strategy:** Autoscaled blue-green for graceful transitions

This configuration protects multi-week training runs while maintaining security posture through automated control plane patches. Manual upgrades happen only during planned training gaps, giving you complete control over disruption timing.