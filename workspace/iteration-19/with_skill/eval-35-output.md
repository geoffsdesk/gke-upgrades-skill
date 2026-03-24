# GKE Cluster Configuration for Foundation Model Training

Here's a comprehensive setup plan for your H100 GPU training cluster that protects multi-week training runs while maintaining security posture.

## Cluster Configuration

### Base Cluster Setup
```bash
# Create regional cluster with Extended channel for maximum control
gcloud container clusters create llm-training-cluster \
  --zone us-central1-a \
  --machine-type e2-standard-4 \
  --num-nodes 1 \
  --release-channel extended \
  --enable-autoscaling \
  --min-nodes 1 \
  --max-nodes 3 \
  --disk-size 100GB \
  --enable-autorepair \
  --enable-autoupgrade \
  --maintenance-window-start "2024-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA" \
  --maintenance-patch-version-disruption-interval=7776000s \
  --maintenance-minor-version-disruption-interval=7776000s
```

### Training Node Pool (H100 GPUs)
```bash
# Create dedicated H100 training pool with upgrade protection
gcloud container node-pools create h100-training-pool \
  --cluster llm-training-cluster \
  --zone us-central1-a \
  --machine-type a3-highgpu-8g \
  --accelerator type=nvidia-h100-80gb,count=8 \
  --num-nodes 4 \
  --enable-autoscaling \
  --min-nodes 0 \
  --max-nodes 16 \
  --disk-size 1000GB \
  --disk-type pd-ssd \
  --enable-autorepair \
  --node-taints=training=true:NoSchedule \
  --node-labels=workload-type=training,gpu-type=h100 \
  --reservation-affinity consume-reservation \
  --reservation H100_RESERVATION_NAME \
  --compact-placement \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

## Release Channel Strategy: Extended

**Why Extended channel for training clusters:**
- Up to 24 months of support per version (cost only during extended period)
- **Minor version auto-upgrades are disabled** except at end of extended support
- Only security patches auto-apply to control plane
- Maximum flexibility around End of Support enforcement
- Full SLA coverage throughout standard + extended support periods

## Maintenance Controls Configuration

### Maximum Upgrade Protection Setup
```bash
# Apply persistent "no minor or node upgrades" exclusion
gcloud container clusters update llm-training-cluster \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**This exclusion provides:**
- ✅ Control plane security patches continue (critical for security compliance)
- ❌ Minor version upgrades blocked (prevents disruptive K8s version changes)
- ❌ Node pool upgrades blocked (prevents GPU driver changes, pod evictions)
- ✅ Automatically tracks End of Support dates (no manual renewal needed)
- ✅ No 30-day time limit (unlike "no upgrades" exclusion)

### Disruption Budget (90-day intervals)
The 90-day disruption intervals ensure patches are applied at most once every 90 days, giving you predictable upgrade timing aligned with training campaign schedules.

## Node Pool Strategy: GPU-Specific Approach

### For H100 Training Pools
```bash
# GPU pools require special surge settings due to fixed reservations
--max-surge-upgrade 0 \
--max-unavailable-upgrade 1
```

**Why these settings:**
- **maxSurge=0**: H100 reservations typically have no surge capacity. Attempting surge upgrades will fail when no extra GPUs are available.
- **maxUnavailable=1**: This is your PRIMARY upgrade lever for GPU pools. Drains one node at a time, no extra GPUs needed.
- **Capacity dip trade-off**: This causes temporary capacity loss during upgrades, but it's the only viable option with fixed reservations.

### Scaling maxUnavailable for Faster Upgrades
If your training workloads can tolerate larger capacity dips:
```bash
# For faster upgrades on large pools (if workload permits)
gcloud container node-pools update h100-training-pool \
  --cluster llm-training-cluster \
  --zone us-central1-a \
  --max-unavailable-upgrade 2  # or 3, 4 depending on tolerance
```

## Training Workload Protection

### Essential PDB Configuration
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
spec:
  minAvailable: 75%  # Adjust based on your distributed training requirements
  selector:
    matchLabels:
      app: foundation-model-training
---
# For single-node training jobs that cannot be interrupted
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: single-job-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels:
      training-type: single-node
```

### Training Job Configuration
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: foundation-model-training
spec:
  template:
    spec:
      nodeSelector:
        workload-type: training
        gpu-type: h100
      tolerations:
      - key: training
        operator: Equal
        value: "true"
        effect: NoSchedule
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule
      terminationGracePeriodSeconds: 3600  # 1 hour for checkpoint saving
      containers:
      - name: training
        image: your-training-image
        resources:
          requests:
            nvidia.com/gpu: 8
          limits:
            nvidia.com/gpu: 8
        # Critical: Enable checkpointing
        env:
        - name: CHECKPOINT_INTERVAL
          value: "3600"  # Checkpoint every hour
        - name: CHECKPOINT_PATH
          value: "/persistent/checkpoints"
```

## Upgrade Workflow for Training Clusters

### During Active Training (Emergency Only)
```bash
# 1. If emergency patch needed during training, apply temporary "no upgrades" freeze
gcloud container clusters update llm-training-cluster \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "emergency-freeze" \
  --add-maintenance-exclusion-start-time "2024-01-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-02-14T00:00:00Z" \
  --add-maintenance-exclusion-scope no_upgrades

# 2. Coordinate with training team for planned checkpoint and resume
```

### Between Training Campaigns (Recommended Window)
```bash
# 1. Verify no active training jobs
kubectl get jobs -n training-namespace

# 2. Check for pending upgrades
gcloud container clusters get-upgrade-info llm-training-cluster --zone us-central1-a

# 3. Manual upgrade when safe (bypasses maintenance exclusions)
gcloud container clusters upgrade llm-training-cluster \
  --zone us-central1-a \
  --master \
  --cluster-version TARGET_VERSION

# 4. Upgrade training nodes after control plane
gcloud container node-pools upgrade h100-training-pool \
  --cluster llm-training-cluster \
  --zone us-central1-a \
  --cluster-version TARGET_VERSION
```

## Multi-Environment Strategy

### Staging Cluster (Regular Channel)
```bash
# Create staging cluster on Regular channel for validation
gcloud container clusters create llm-training-staging \
  --zone us-central1-b \
  --release-channel regular \
  --machine-type e2-standard-4 \
  --num-nodes 1
  
# Add small GPU pool for testing
gcloud container node-pools create gpu-staging-pool \
  --cluster llm-training-staging \
  --zone us-central1-b \
  --machine-type a3-highgpu-8g \
  --accelerator type=nvidia-h100-80gb,count=8 \
  --num-nodes 1 \
  --max-nodes 2
```

**Validation workflow:**
1. New GKE versions reach Regular channel first
2. Test your training workloads on staging
3. Validate GPU driver compatibility, CUDA versions, training throughput
4. Only upgrade production after successful staging validation

## Monitoring and Alerting

### Critical Monitoring Setup
```yaml
# Monitor for upgrade events that might affect training
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: gke-upgrade-alerts
spec:
  groups:
  - name: gke-upgrades
    rules:
    - alert: UnplannedGKEUpgrade
      expr: increase(gke_cluster_upgrade_events_total[5m]) > 0
      for: 1m
      labels:
        severity: critical
      annotations:
        summary: "GKE cluster upgrade detected during training"
    
    - alert: TrainingJobEvicted
      expr: increase(kube_pod_container_status_restarts_total{container=~".*training.*"}[5m]) > 0
      for: 1m
      labels:
        severity: critical
      annotations:
        summary: "Training job pod restarted unexpectedly"
```

### Cloud Logging Alerts
```bash
# Set up log-based alert for forced upgrades
gcloud logging sinks create gke-upgrade-alerts \
  logging.googleapis.com/projects/PROJECT_ID/topics/gke-alerts \
  --log-filter='resource.type="gke_cluster" 
    protoPayload.operationType="UPGRADE_MASTER" 
    protoPayload.metadata.operationType="FORCED_UPGRADE"'
```

## Cost Optimization Notes

1. **Extended channel cost**: Additional cost applies ONLY during extended support period (months 15-24), not during standard support (months 1-14)
2. **H100 reservation**: Use committed use discounts for predictable long-term training workloads
3. **Node auto-scaling**: Scale training pools to zero between campaigns to minimize costs
4. **Preemptible staging**: Use preemptible instances for staging validation to reduce costs

## Security Compliance

This configuration maintains security while protecting training:
- ✅ Control plane security patches auto-applied within 90-day intervals
- ✅ Security monitoring via GKE security bulletins
- ✅ Extended support SLA coverage
- ✅ Audit logging enabled for compliance requirements
- ❌ Node-level security patches deferred during training campaigns (acceptable trade-off for ML workloads)

## Summary: Key Protections

1. **Extended release channel** - Maximum control over minor versions
2. **"No minor or node upgrades" exclusion** - Blocks disruptive changes, allows CP patches
3. **90-day disruption intervals** - Predictable patch timing
4. **GPU-specific surge settings** - Works with fixed reservations
5. **Training-aware PDBs** - Protects multi-week jobs
6. **Staging validation pipeline** - Test before production upgrades

This setup gives you enterprise-grade upgrade control while maintaining the security posture required for production ML infrastructure.