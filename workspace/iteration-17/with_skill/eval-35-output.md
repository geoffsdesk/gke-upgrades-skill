# GKE Configuration for Foundation Model Training with H100 GPUs

## Recommended Cluster Configuration

### Core Cluster Settings
```bash
# Create regional cluster for control plane HA
gcloud container clusters create foundation-training \
  --region us-central1 \
  --release-channel extended \
  --enable-network-policy \
  --enable-ip-alias \
  --num-nodes 0 \
  --enable-autoscaling \
  --cluster-version 1.31.3-gke.1146000 \
  --enable-autorepair \
  --enable-autoupgrade \
  --maintenance-window-start "2024-12-15T03:00:00Z" \
  --maintenance-window-duration 6h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU" \
  --maintenance-minor-version-disruption-interval 90d \
  --maintenance-patch-version-disruption-interval 90d \
  --send-scheduled-upgrade-notifications
```

**Key decisions:**
- **Extended channel**: Maximum flexibility around EoS enforcement (24 months support vs 14 months), ideal for long training campaigns
- **Regional cluster**: Control plane remains available during CP upgrades
- **90-day disruption intervals**: Limits upgrade frequency to quarterly for both patches and minor versions
- **Sunday 3-9 AM maintenance window**: Aligns with typical low-activity periods
- **Scheduled notifications**: 72-hour advance warning of auto-upgrades

### Training Node Pool (H100s)
```bash
# Dedicated training pool with upgrade protection
gcloud container node-pools create h100-training \
  --cluster foundation-training \
  --region us-central1 \
  --machine-type a3-highgpu-8g \
  --accelerator type=nvidia-h100-80gb,count=8,gpu-driver-version=latest \
  --num-nodes 0 \
  --enable-autoscaling \
  --min-nodes 0 \
  --max-nodes 64 \
  --node-locations us-central1-a,us-central1-c \
  --disk-type pd-ssd \
  --disk-size 2048GB \
  --enable-autorepair \
  --placement-policy-type COMPACT \
  --reservation-affinity consume \
  --reservation TRAINING_RESERVATION_NAME \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Training pool strategy:**
- **Compact placement**: Preserves RDMA topology for multi-node training
- **Reservation affinity**: Uses your H100 reservation efficiently
- **Per-nodepool "no minor or node upgrades" exclusion**: Blocks ALL node upgrades while allowing control plane security patches
- **Persistent exclusion**: Automatically renews when versions change

### Inference/Support Node Pool
```bash
# Separate pool for inference, monitoring, checkpointing
gcloud container node-pools create cpu-inference \
  --cluster foundation-training \
  --region us-central1 \
  --machine-type c3-standard-44 \
  --num-nodes 3 \
  --enable-autoscaling \
  --min-nodes 3 \
  --max-nodes 20 \
  --disk-type pd-standard \
  --disk-size 100GB \
  --preemptible
```

**Support pool strategy:**
- **Auto-upgrades enabled**: Gets security patches and upgrades normally
- **Preemptible**: Cost-effective for non-training workloads
- **No maintenance exclusions**: Stays current with patches

## Maintenance Exclusion Strategy

The **"no minor or node upgrades"** exclusion is perfect for your use case:

| What it blocks | What it allows | Duration |
|---------------|----------------|----------|
| ❌ Minor version upgrades (1.31→1.32) | ✅ Control plane security patches | Up to End of Support |
| ❌ Node pool upgrades | ✅ New cluster creation at current version | Auto-renews with version |
| ❌ Forced node recreation | ✅ Node auto-repair (same version) | Persistent |

```bash
# Apply training protection (already included in node pool creation above)
gcloud container clusters update foundation-training \
  --region us-central1 \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## GPU-Specific Upgrade Considerations

### H100 Node Pool Upgrade Settings (for eventual upgrades)
```bash
# Configure for when you DO need to upgrade training nodes
gcloud container node-pools update h100-training \
  --cluster foundation-training \
  --region us-central1 \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2
```

**Why these settings:**
- **maxSurge=0**: H100 reservations typically have no surge capacity
- **maxUnavailable=2**: Allows 2 nodes to drain simultaneously for faster upgrades during training gaps
- **Drain-first strategy**: Ensures no extra H100s needed during upgrade

### Training Job Protection
```yaml
# Example training workload with protection
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: llm-training
spec:
  serviceName: training
  replicas: 8
  template:
    spec:
      terminationGracePeriodSeconds: 7200  # 2 hours for checkpoint save
      containers:
      - name: trainer
        image: your-training-image
        resources:
          requests:
            nvidia.com/gpu: 8
        volumeMounts:
        - name: checkpoints
          mountPath: /checkpoints
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
spec:
  selector:
    matchLabels:
      app: llm-training
  minAvailable: 6  # Allows 2 pods to be evicted max
```

## Planned Upgrade Strategy

### Between Training Campaigns
```bash
# 1. Wait for training run completion
kubectl scale statefulset llm-training --replicas=0

# 2. Remove maintenance exclusion temporarily
gcloud container clusters update foundation-training \
  --region us-central1 \
  --remove-maintenance-exclusion-name "training-protection"

# 3. Trigger immediate upgrade during the gap
gcloud container node-pools upgrade h100-training \
  --cluster foundation-training \
  --region us-central1 \
  --cluster-version TARGET_VERSION

# 4. Validate and restore protection
gcloud container clusters update foundation-training \
  --region us-central1 \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

### Emergency Security Patches
Control plane patches apply automatically even with exclusions - no action needed. For critical node-level patches:

```bash
# Option A: Emergency upgrade with checkpointing
kubectl exec -it llm-training-0 -- /save_checkpoint.sh
gcloud container clusters update foundation-training \
  --remove-maintenance-exclusion-name "training-protection"

# Option B: Cordon nodes and wait for natural completion
kubectl cordon -l cloud.google.com/gke-nodepool=h100-training
# Training completes naturally, then upgrade empty nodes
```

## Monitoring and Notifications

### Setup upgrade monitoring
```bash
# Create log-based metric for upgrade events
gcloud logging metrics create gke_upgrade_events \
  --description="GKE upgrade operations" \
  --log-filter='resource.type="gke_cluster" 
    protoPayload.methodName="google.container.v1.ClusterManager.UpdateCluster"'

# Create alerting policy
gcloud alpha monitoring policies create \
  --policy-from-file=upgrade_alert_policy.yaml
```

### Track training job health
```yaml
# upgrade_alert_policy.yaml
displayName: "GKE Training Cluster Upgrade Alert"
conditions:
- displayName: "Upgrade starting"
  conditionThreshold:
    filter: 'metric.type="logging.googleapis.com/user/gke_upgrade_events"'
    comparison: COMPARISON_GT
    thresholdValue: 0
alertStrategy:
  notificationChannels:
  - projects/PROJECT_ID/notificationChannels/EMAIL_CHANNEL
```

## Cost Optimization During Upgrades

Since H100s are expensive, minimize upgrade costs:

1. **Use autoscaled blue-green for inference pools** - scales down old nodes as new ones come up
2. **Coordinate with reservation usage** - upgrade during off-peak reservation periods  
3. **Batch training campaigns** - align upgrade windows with natural training gaps
4. **Pre-emptible support nodes** - cheap infrastructure for monitoring, data loading

## Security vs. Stability Balance

This configuration gives you:

✅ **Maximum training protection**: No unexpected node disruptions for months  
✅ **Control plane security**: Auto-applied patches without node impact  
✅ **Predictable upgrade windows**: Sunday mornings, 90-day minimum intervals  
✅ **Emergency flexibility**: Can remove exclusions for critical patches  
✅ **Cost efficiency**: No 2x resource requirement during upgrades  

The Extended channel + persistent exclusions approach is specifically designed for workloads like yours where stability trumps staying on the latest version. You get up to 24 months per minor version, giving you multiple natural upgrade opportunities during your training cycles.