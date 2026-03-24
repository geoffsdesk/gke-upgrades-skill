# GKE Foundation Model Training Cluster Setup Guide

For multi-week H100 GPU training, your cluster needs carefully tuned upgrade controls from day one. Here's the complete configuration strategy:

## Core Cluster Configuration

### Release Channel Selection
**Recommendation: Regular Channel**
- Stable has too slow security patch delivery for GPU clusters
- Regular provides good balance: security patches within ~2 weeks, validated stability
- Extended channel would delay security fixes too long for high-value GPU infrastructure

```bash
gcloud container clusters create foundation-training \
  --zone us-central1-a \
  --release-channel regular \
  --cluster-version 1.31.3-gke.1146000 \
  --enable-network-policy \
  --enable-ip-alias \
  --num-nodes 0 \
  --enable-autoscaling \
  --max-nodes-per-pool 1000
```

### Maintenance Windows & Exclusions Strategy

**Primary Control: "No minor or node upgrades" exclusion**
This is your main protection - allows security patches on control plane while blocking all node disruptions:

```bash
# Set maintenance window during planned downtime
gcloud container clusters update foundation-training \
  --zone us-central1-a \
  --maintenance-window-start 2024-12-15T06:00:00Z \
  --maintenance-window-end 2024-12-15T10:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"

# Add persistent "no minor or node upgrades" exclusion
gcloud container clusters update foundation-training \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Additional 30-day freeze for critical periods:**
```bash
# Before major training runs, add 30-day complete freeze
gcloud container clusters update foundation-training \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "q4-training-freeze" \
  --add-maintenance-exclusion-start-time 2024-12-01T00:00:00Z \
  --add-maintenance-exclusion-end-time 2024-12-31T23:59:59Z \
  --add-maintenance-exclusion-scope no_upgrades
```

### Cluster Disruption Budget
Extend disruption intervals to prevent back-to-back upgrades:

```bash
gcloud container clusters update foundation-training \
  --zone us-central1-a \
  --maintenance-minor-version-disruption-interval=90d \
  --maintenance-patch-version-disruption-interval=14d
```

## H100 Node Pool Configuration

### GPU Node Pool with Upgrade Protection
```bash
gcloud container node-pools create h100-training \
  --cluster foundation-training \
  --zone us-central1-a \
  --machine-type a3-highgpu-8g \
  --accelerator type=nvidia-h100-80gb,count=8 \
  --num-nodes 8 \
  --enable-autoscaling \
  --min-nodes 0 \
  --max-nodes 64 \
  --node-locations us-central1-a \
  --disk-size 200GB \
  --disk-type pd-ssd \
  --enable-autorepair \
  --enable-autoupgrade=false \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1 \
  --placement-type COMPACT \
  --placement-policy training-placement \
  --reservation-affinity=specific \
  --reservation h100-training-reservation
```

**Critical GPU upgrade settings:**
- `--max-surge-upgrade 0`: H100 reservations have no surge capacity
- `--max-unavailable-upgrade 1`: Only drain one node at a time
- `--enable-autoupgrade=false`: Deprecated flag, use maintenance exclusions instead

### Per-Node-Pool Maintenance Exclusion
Apply additional protection directly to the GPU node pool:

```bash
gcloud container node-pools update h100-training \
  --cluster foundation-training \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "h100-training-freeze" \
  --add-maintenance-exclusion-scope no_upgrades \
  --add-maintenance-exclusion-start-time 2024-12-01T00:00:00Z \
  --add-maintenance-exclusion-end-time 2025-03-01T00:00:00Z
```

## Training Workload Protection

### Pod Disruption Budget for Training Jobs
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
  namespace: ml-training
spec:
  maxUnavailable: 0  # Prevent any pod eviction during training
  selector:
    matchLabels:
      workload-type: foundation-training
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: llm-training
  namespace: ml-training
spec:
  replicas: 8
  selector:
    matchLabels:
      workload-type: foundation-training
  template:
    metadata:
      labels:
        workload-type: foundation-training
    spec:
      terminationGracePeriodSeconds: 3600  # 1 hour for checkpoint completion
      nodeSelector:
        cloud.google.com/gke-nodepool: h100-training
      containers:
      - name: training-container
        image: gcr.io/project/training:latest
        resources:
          requests:
            nvidia.com/gpu: 8
          limits:
            nvidia.com/gpu: 8
```

### Training Job Checkpointing Strategy
```yaml
# ConfigMap for checkpoint configuration
apiVersion: v1
kind: ConfigMap
metadata:
  name: training-config
data:
  checkpoint_interval: "1800"  # Checkpoint every 30 minutes
  checkpoint_path: "/gcs/training-checkpoints"
  graceful_shutdown: "true"
  max_checkpoint_time: "900"   # Max 15 min for checkpoint save
```

## Upgrade Execution Strategy

### Manual Upgrade Process (Recommended)
Since you're using maintenance exclusions, plan manual upgrades during training gaps:

```bash
# 1. Check for training job completion
kubectl get pods -n ml-training -l workload-type=foundation-training

# 2. Temporarily remove the maintenance exclusion
gcloud container clusters update foundation-training \
  --zone us-central1-a \
  --remove-maintenance-exclusion "training-protection"

# 3. Upgrade control plane during maintenance window
gcloud container clusters upgrade foundation-training \
  --zone us-central1-a \
  --master \
  --cluster-version 1.32.1-gke.1234000

# 4. Upgrade H100 node pool (one node at a time due to maxUnavailable=1)
gcloud container node-pools upgrade h100-training \
  --cluster foundation-training \
  --zone us-central1-a \
  --cluster-version 1.32.1-gke.1234000

# 5. Restore maintenance exclusion
gcloud container clusters update foundation-training \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

### AI Host Maintenance Strategy
For large H100 upgrades, use parallel host maintenance:

```bash
# For training workloads - parallel strategy (all nodes at once)
# 1. Scale training jobs to zero (or checkpoint and pause)
kubectl scale deployment llm-training --replicas=0 -n ml-training

# 2. Apply maintenance label to all H100 nodes simultaneously
kubectl label nodes -l cloud.google.com/gke-nodepool=h100-training \
  cloud.google.com/perform-maintenance=true

# 3. Wait for host maintenance (~4 hours)
# 4. Restart training workloads
kubectl scale deployment llm-training --replicas=8 -n ml-training
```

## Monitoring & Alerting

### Upgrade Notification Setup
```bash
# Enable scheduled upgrade notifications (72h advance notice)
gcloud logging sinks create gke-upgrade-alerts \
  bigquery.googleapis.com/projects/PROJECT_ID/datasets/gke_logs \
  --log-filter='resource.type="gke_cluster" 
               protoPayload.metadata.operationType="UPGRADE_MASTER"
               OR protoPayload.metadata.operationType="UPGRADE_NODES"'

# Set up Pub/Sub for real-time alerts
gcloud pubsub topics create gke-upgrades
gcloud logging sinks create gke-upgrade-pubsub \
  pubsub.googleapis.com/projects/PROJECT_ID/topics/gke-upgrades \
  --log-filter='resource.type="gke_cluster"'
```

### Training Job Monitoring
```yaml
apiVersion: v1
kind: ServiceMonitor
metadata:
  name: training-metrics
spec:
  selector:
    matchLabels:
      workload-type: foundation-training
  endpoints:
  - port: metrics
    interval: 30s
    path: /metrics
```

## Security Considerations

### Rapid Security Patching When Needed
For critical CVEs, you can temporarily lift exclusions:

```bash
# Emergency security patch process
# 1. Remove exclusion temporarily
gcloud container clusters update foundation-training \
  --zone us-central1-a \
  --remove-maintenance-exclusion "training-protection"

# 2. Force immediate upgrade
gcloud container clusters upgrade foundation-training \
  --zone us-central1-a \
  --master \
  --cluster-version TARGET_SECURITY_VERSION

# 3. Restore protection
# (Re-add exclusion as shown above)
```

### Regular Security Assessment
```bash
# Check for deprecated APIs (blocks auto-upgrades)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Review GKE security insights
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location us-central1-a \
  --project PROJECT_ID
```

## Operational Runbook

### Pre-Training Checklist
```markdown
- [ ] Maintenance exclusions active and verified
- [ ] PDBs configured with maxUnavailable: 0
- [ ] Checkpoint system tested and validated
- [ ] Training job graceful shutdown tested
- [ ] H100 node pool at stable version (no pending upgrades)
- [ ] Monitoring alerts configured for upgrade notifications
- [ ] Emergency contact list updated for upgrade issues
```

### Training Window Management
1. **Start of training campaign**: Apply 30-day "no upgrades" exclusion
2. **During training**: Monitor via Cloud Logging for any upgrade attempts
3. **End of training**: Plan upgrade window within 48 hours to apply security patches
4. **Between campaigns**: Allow patches and minor upgrades as needed

This configuration gives you maximum protection for multi-week training runs while maintaining security patch currency during training gaps. The key is the layered exclusion approach: persistent "no minor or node upgrades" for baseline protection, plus temporary "no upgrades" exclusions during active training periods.