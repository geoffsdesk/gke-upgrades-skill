# GKE Configuration for Foundation Model Training with H100 GPUs

## Executive Summary

For multi-week training runs on H100s, you need **maximum upgrade control** while maintaining security. The key is using Extended channel + persistent maintenance exclusions + dedicated training node pools to prevent disruptive upgrades during active training campaigns.

## Recommended Cluster Configuration

### Release Channel Strategy
```bash
# Use Extended channel for maximum control and 24-month support
gcloud container clusters create foundation-training-cluster \
    --release-channel extended \
    --region us-central1 \
    --enable-ip-alias \
    --cluster-version 1.31.3-gke.1146000  # Latest stable version with Extended support
```

**Why Extended channel:**
- Up to 24 months of support (cost only during extended period)
- Minor version auto-upgrades are **disabled** (except at end of extended support)
- Only patches are auto-applied — critical for training workload stability
- Gives you complete control over when minor upgrades happen

### Maintenance Control Configuration

```bash
# Set up maintenance exclusions for maximum control
gcloud container clusters update foundation-training-cluster \
    --region us-central1 \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support \
    --maintenance-patch-version-disruption-interval=7776000s \
    --maintenance-window-start "2025-01-11T06:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Configuration breakdown:**
- **"No minor or node upgrades" exclusion:** Blocks all disruptive upgrades while allowing critical security patches on the control plane
- **Until end of support:** Persistent exclusion that automatically tracks EoS dates
- **90-day patch interval:** Control plane patches limited to once every 90 days maximum
- **Saturday 6-10 AM maintenance window:** Predictable timing for any allowed maintenance

### Node Pool Architecture

Create **separate node pools** for training vs inference/support workloads:

#### 1. Training Node Pool (H100s)
```bash
# Training pool - maximum protection
gcloud container node-pools create h100-training \
    --cluster foundation-training-cluster \
    --region us-central1 \
    --machine-type a3-highgpu-8g \
    --accelerator type=nvidia-h100-80gb,count=8 \
    --num-nodes 16 \
    --enable-autoscaling=false \
    --disk-size 2000GB \
    --disk-type pd-ssd \
    --node-taints training=true:NoSchedule \
    --node-labels workload-type=training \
    --placement-type COMPACT \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 1
```

#### 2. Inference/Support Node Pool
```bash
# Support workloads - can tolerate more frequent updates
gcloud container node-pools create general-compute \
    --cluster foundation-training-cluster \
    --region us-central1 \
    --machine-type c3-standard-22 \
    --num-nodes 3 \
    --enable-autoscaling \
    --min-nodes 3 \
    --max-nodes 10 \
    --max-surge-upgrade 1 \
    --max-unavailable-upgrade 0
```

### GPU-Specific Upgrade Strategy

**For H100 training pools:**
- **`maxSurge=0, maxUnavailable=1`** — H100 reservations typically have no surge capacity
- **Compact placement** — Ensures RDMA topology is preserved
- **No autoscaling** — Fixed capacity for predictable training performance
- **Node taints** — Isolates training workloads from other pods

**Key constraint:** GPU VMs don't support live migration. Every upgrade requires pod restart and training checkpoint recovery.

## Workload Protection Strategy

### 1. Training Job Configuration
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
      tolerations:
      - key: training
        operator: Equal
        value: "true"
        effect: NoSchedule
      containers:
      - name: training
        image: your-training-image
        resources:
          requests:
            nvidia.com/gpu: 8
          limits:
            nvidia.com/gpu: 8
        env:
        - name: CHECKPOINT_INTERVAL
          value: "3600"  # Checkpoint hourly
        terminationGracePeriodSeconds: 7200  # 2 hours for graceful shutdown
```

### 2. Pod Disruption Budget
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
spec:
  minAvailable: 100%  # Prevent any disruption during training
  selector:
    matchLabels:
      app: foundation-training
```

## Operational Workflow

### During Active Training Campaigns

1. **Before starting a multi-week training run:**
```bash
# Verify no pending upgrades
gcloud container clusters get-upgrade-info foundation-training-cluster --region us-central1

# Confirm maintenance exclusions are active
gcloud container clusters describe foundation-training-cluster \
    --region us-central1 \
    --format="value(maintenancePolicy)"
```

2. **Training job lifecycle:**
   - Deploy training job with checkpointing every 1-2 hours
   - Monitor job progress and GPU utilization
   - Training runs protected by PDB and maintenance exclusions

### During Training Gaps (Monthly/Quarterly)

1. **Planned upgrade windows between training runs:**
```bash
# Check for available updates
gcloud container clusters get-upgrade-info foundation-training-cluster --region us-central1

# If updates needed, temporarily allow them
gcloud container clusters update foundation-training-cluster \
    --region us-central1 \
    --remove-maintenance-exclusion-name "no-minor-or-node-upgrades"

# Manually trigger specific upgrades if needed
gcloud container clusters upgrade foundation-training-cluster \
    --region us-central1 \
    --cluster-version TARGET_VERSION

# Re-apply protection before next training campaign
gcloud container clusters update foundation-training-cluster \
    --region us-central1 \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

## Security Posture

This configuration maintains security while protecting training:

✅ **Control plane security patches** — Auto-applied (limited to every 90 days max)
✅ **Critical vulnerability fixes** — Can be applied during training gaps
✅ **Extended support** — 24 months of support for major versions
❌ **Minor version changes** — Blocked during training (applied during gaps)
❌ **Node upgrades** — Blocked during training (applied during gaps)

## Monitoring and Alerting

Set up alerts for:
```bash
# Schedule upgrade notifications (72h advance notice)
gcloud container clusters update foundation-training-cluster \
    --region us-central1 \
    --send-scheduled-upgrade-notifications

# Monitor training job health
kubectl top nodes
kubectl get pods -l app=foundation-training -o wide
```

## Cost Considerations

- **Extended channel cost:** Additional charges only during the extended support period (months 14-24)
- **H100 reservation:** Ensure reservation has adequate capacity for training workloads
- **No surge costs:** Using `maxSurge=0` avoids temporary 2x GPU costs during upgrades

## Migration Path from Other Configurations

If you have existing clusters on Regular/Stable channel:
```bash
# Migrate to Extended channel (check version compatibility first)
gcloud container clusters update EXISTING_CLUSTER \
    --region REGION \
    --release-channel extended

# Add training workload protection
gcloud container clusters update EXISTING_CLUSTER \
    --region REGION \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

This configuration gives you **maximum control** over disruptive changes while maintaining security patches — exactly what foundation model training requires for multi-week runs on expensive H100 infrastructure.