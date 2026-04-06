# GKE Configuration for Foundation Model Training

## Recommended Cluster Configuration

### Release Channel & Version Strategy
```bash
# Use Extended channel for maximum control over minor upgrades
gcloud container clusters create fm-training-cluster \
  --release-channel extended \
  --cluster-version 1.33.1-gke.2055000 \
  --location us-central1-a
```

**Why Extended channel:**
- Minor version upgrades are NOT automated (except at end of extended support)
- You control WHEN minor upgrades happen between training campaigns
- Patches still auto-apply at Regular channel timing for security
- Up to 24 months support (cost only during extended period)
- Full SLA unlike Rapid channel

### Maintenance Controls for Training Protection

```bash
# Configure maintenance window during planned gaps
gcloud container clusters update fm-training-cluster \
  --location us-central1-a \
  --maintenance-window-start "2024-12-01T06:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"

# Set aggressive patch disruption interval (patches monthly max)
gcloud container clusters update fm-training-cluster \
  --location us-central1-a \
  --maintenance-patch-version-disruption-interval=2592000s

# Add persistent "no minor or node upgrades" exclusion
gcloud container clusters update fm-training-cluster \
  --location us-central1-a \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Critical insight:** The "no minor or node upgrades" exclusion allows security patches on the control plane while blocking ALL disruptive upgrades. This is the maximum protection setting while maintaining security posture.

### Dedicated Training Node Pool Strategy

```bash
# Create dedicated H100 training pool with upgrade protection
gcloud container node-pools create h100-training-pool \
  --cluster fm-training-cluster \
  --location us-central1-a \
  --machine-type a3-highgpu-8g \
  --accelerator type=nvidia-h100-80gb,count=8 \
  --num-nodes 16 \
  --enable-autoscaling \
  --min-nodes 0 \
  --max-nodes 64 \
  --reservation-affinity specific \
  --reservation h100-training-reservation \
  --node-taints training-dedicated=true:NoSchedule \
  --node-labels workload=foundation-model-training \
  --placement-type COMPACT \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

**Key settings explained:**
- **maxSurge=0, maxUnavailable=1:** GPU reservations typically have no surge capacity
- **Compact placement:** Preserves RDMA topology for multi-node training
- **Dedicated taints:** Prevents non-training workloads from landing on expensive H100s
- **Reservation affinity:** Guarantees H100 capacity

### Separate Inference/Serving Pool

```bash
# Create separate pool for inference workloads (can upgrade independently)
gcloud container node-pools create inference-pool \
  --cluster fm-training-cluster \
  --location us-central1-a \
  --machine-type a2-ultragpu-1g \
  --accelerator type=nvidia-a100-80gb,count=1 \
  --num-nodes 4 \
  --enable-autoscaling \
  --min-nodes 0 \
  --max-nodes 20 \
  --strategy=BLUE_GREEN \
  --node-pool-soak-duration=1800s \
  --standard-rollout-policy=batch-node-count=1,batch-soak-duration=300s
```

**Strategy rationale:** Blue-green for inference minimizes serving disruption. Training pool uses surge with maxUnavailable mode due to reservation constraints.

## Training Workload Protection Setup

### PodDisruptionBudget for Training Jobs
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-job-pdb
spec:
  minAvailable: "100%"  # Never allow disruption during active training
  selector:
    matchLabels:
      job-type: foundation-model-training
```

### Training Job Template with Protection
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: llm-pretraining-run-001
spec:
  backoffLimit: 0  # Don't restart failed training
  template:
    metadata:
      labels:
        job-type: foundation-model-training
      annotations:
        cluster-autoscaler.kubernetes.io/safe-to-evict: "false"
    spec:
      tolerations:
      - key: training-dedicated
        operator: Equal
        value: "true"
        effect: NoSchedule
      nodeSelector:
        workload: foundation-model-training
      terminationGracePeriodSeconds: 3600  # 1 hour for checkpointing
      containers:
      - name: training
        image: nvcr.io/nvidia/pytorch:24.03-py3
        resources:
          requests:
            nvidia.com/gpu: 8
          limits:
            nvidia.com/gpu: 8
```

## Operational Procedures

### Before Starting Multi-Week Training
```bash
# 1. Apply immediate upgrade freeze
gcloud container clusters update fm-training-cluster \
  --location us-central1-a \
  --add-maintenance-exclusion-name "training-campaign-q1" \
  --add-maintenance-exclusion-start-time "2024-12-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# 2. Verify no pending upgrades
gcloud container clusters get-upgrade-info fm-training-cluster \
  --location us-central1-a

# 3. Scale training pool to required size
gcloud container clusters resize fm-training-cluster \
  --node-pool h100-training-pool \
  --location us-central1-a \
  --num-nodes 32
```

### Between Training Campaigns (Upgrade Window)
```bash
# 1. Remove training freeze
gcloud container clusters update fm-training-cluster \
  --location us-central1-a \
  --remove-maintenance-exclusion "training-campaign-q1"

# 2. Check for available upgrades
gcloud container clusters get-upgrade-info fm-training-cluster \
  --location us-central1-a

# 3. Manually trigger upgrades if needed (bypasses maintenance windows)
gcloud container clusters upgrade fm-training-cluster \
  --location us-central1-a \
  --master \
  --cluster-version 1.33.2-gke.2078000

# 4. Scale down training pool to save costs
gcloud container clusters resize fm-training-cluster \
  --node-pool h100-training-pool \
  --location us-central1-a \
  --num-nodes 0
```

## Monitoring and Alerting Setup

### Upgrade Notification Monitoring
```bash
# Enable scheduled upgrade notifications (72h advance warning)
gcloud container clusters update fm-training-cluster \
  --location us-central1-a \
  --enable-scheduled-upgrades

# Query for upgrade notifications in Cloud Logging
gcloud logging read '
resource.type="gke_cluster"
resource.labels.cluster_name="fm-training-cluster"
protoPayload.metadata.operationType=~"(UPDATE_CLUSTER|UPGRADE_MASTER)"
' --limit 10
```

### Training Job Health Monitoring
```yaml
apiVersion: v1
kind: Service
metadata:
  name: training-metrics
spec:
  selector:
    job-type: foundation-model-training
  ports:
  - port: 8080
    name: metrics
---
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: training-job-monitor
spec:
  selector:
    matchLabels:
      job-type: foundation-model-training
  endpoints:
  - port: metrics
    interval: 30s
```

## Cost Optimization Strategy

### Scheduled Scaling for Training Campaigns
```bash
# Create a cron job to scale up training pool before campaigns
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: CronJob
metadata:
  name: training-pool-scaleup
spec:
  schedule: "0 6 1 * *"  # First day of month at 6 AM
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: cluster-admin
          containers:
          - name: scaler
            image: google/cloud-sdk:slim
            command:
            - /bin/bash
            - -c
            - |
              gcloud container clusters resize fm-training-cluster \
                --node-pool h100-training-pool \
                --location us-central1-a \
                --num-nodes 32
          restartPolicy: OnFailure
EOF
```

## Security Considerations

**Patch management balance:** The configuration allows control plane security patches while blocking node disruption. This maintains security posture without interrupting training.

**Version drift monitoring:**
```bash
# Check version skew monthly
gcloud container clusters describe fm-training-cluster \
  --location us-central1-a \
  --format="table(currentMasterVersion, nodePools[].version, nodePools[].name)"
```

## Key Benefits of This Configuration

1. **Training protection:** "No minor or node upgrades" exclusion + 30-day freeze capability
2. **Security maintained:** Control plane patches still auto-apply
3. **Cost efficiency:** Extended channel avoids unnecessary Extended support costs during standard support period
4. **Operational flexibility:** Manual control over when disruptive upgrades happen
5. **Multi-pool isolation:** Training and inference pools can upgrade independently

**Critical timeline:** Plan upgrade windows between training campaigns. H100 upgrades can take days for large pools due to the ~20-node parallelism limit and maxUnavailable=1 setting for reservation constraints.

This configuration gives you maximum control while maintaining Google's security SLA. The Extended channel + persistent exclusion combination is specifically designed for exactly this use case: customers who need to control disruption timing while staying secure and supported.