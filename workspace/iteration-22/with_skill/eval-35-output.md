# GKE Foundation Model Training Cluster Configuration

## Executive Summary

For foundation model training with H100 GPUs and multi-week runs, prioritize **Extended release channel** with **"no minor or node upgrades" maintenance exclusions** and **dedicated training node pools**. This provides maximum upgrade control while maintaining security patches on the control plane.

## Cluster Configuration

### Release Channel Strategy
```bash
gcloud container clusters create fm-training-cluster \
    --release-channel extended \
    --zone us-central1-a \
    --enable-autorepair \
    --enable-autoupgrade \
    --node-locations us-central1-a,us-central1-b,us-central1-c
```

**Why Extended Channel:**
- Up to 24 months of support (cost only during extended period)
- **Minor version auto-upgrades are NOT applied** (except at end of extended support)
- Only patches are auto-applied to control plane
- Maximum flexibility around EoS enforcement
- Full SLA coverage

### Maintenance Controls Configuration
```bash
# Set maintenance window during training gaps (adjust to your schedule)
gcloud container clusters update fm-training-cluster \
    --zone us-central1-a \
    --maintenance-window-start "2026-01-04T06:00:00Z" \
    --maintenance-window-duration 6h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"

# Add persistent "no minor or node" exclusion (tracks EoS automatically)
gcloud container clusters update fm-training-cluster \
    --zone us-central1-a \
    --add-maintenance-exclusion-name "training-protection" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support

# Set disruption intervals for patch frequency control (90 days max)
gcloud container clusters update fm-training-cluster \
    --zone us-central1-a \
    --maintenance-patch-version-disruption-interval=7776000s \
    --maintenance-minor-version-disruption-interval=7776000s
```

**What this provides:**
- **Control plane security patches flow automatically** during Sunday 6-12 AM window
- **Node pools and minor versions require manual approval** 
- **No forced upgrades** during training runs (exclusion tracks EoS)
- **Patches limited to once per 90 days** maximum

## Node Pool Architecture

### Training Pool (H100 GPUs)
```bash
gcloud container node-pools create h100-training \
    --cluster fm-training-cluster \
    --zone us-central1-a \
    --machine-type a3-highgpu-8g \
    --accelerator type=nvidia-h100-80gb,count=8 \
    --num-nodes 16 \
    --enable-autorepair \
    --enable-autoupgrade \
    --node-locations us-central1-a \
    --placement-type COMPACT \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 1 \
    --disk-size 2000GB \
    --disk-type pd-ssd
```

**Key H100 Training Pool Settings:**
- **`--max-surge-upgrade 0`** - No surge capacity needed (H100 reservations are typically fixed)
- **`--max-unavailable-upgrade 1`** - Primary lever for GPU pools; conservative drain-first approach
- **`--placement-type COMPACT`** - Maintains RDMA topology for multi-node training
- **Single zone** - Reduces cross-zone network latency for distributed training

### Inference/Support Pool (Optional)
```bash
gcloud container node-pools create cpu-support \
    --cluster fm-training-cluster \
    --zone us-central1-a \
    --machine-type n1-standard-4 \
    --num-nodes 3 \
    --enable-autorepair \
    --enable-autoupgrade \
    --max-surge-upgrade 1 \
    --max-unavailable-upgrade 0
```

## Training Workload Protection Strategy

### 1. Checkpoint Configuration
Ensure training jobs have robust checkpointing:
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: llm-training
spec:
  template:
    spec:
      restartPolicy: OnFailure
      terminationGracePeriodSeconds: 3600  # 1 hour for checkpoint save
      containers:
      - name: trainer
        image: your-training-image
        env:
        - name: CHECKPOINT_INTERVAL
          value: "1800"  # Checkpoint every 30 minutes
        - name: CHECKPOINT_PATH
          value: "/gcs/checkpoints/"
      nodeSelector:
        cloud.google.com/gke-nodepool: h100-training
```

### 2. Pod Disruption Budget
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
spec:
  minAvailable: 15  # For 16-node training job, allow only 1 disruption
  selector:
    matchLabels:
      job-name: llm-training
```

### 3. During Active Training Campaigns
When starting a multi-week training run:
```bash
# Add temporary "no upgrades" freeze for critical periods
gcloud container clusters update fm-training-cluster \
    --zone us-central1-a \
    --add-maintenance-exclusion-name "training-campaign-dec" \
    --add-maintenance-exclusion-start-time "2024-12-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-12-31T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
```

**Note:** "No upgrades" exclusions are limited to 30 days maximum. For longer campaigns, chain multiple exclusions or rely on the persistent "no minor or node" exclusion.

## Upgrade Execution Strategy

### When Manual Upgrades Are Needed

**Quarterly minor version upgrades** (during training gaps):
```bash
# 1. Verify no active training jobs
kubectl get jobs -A --field-selector status.active=1

# 2. Two-step control plane upgrade with rollback safety
gcloud beta container clusters upgrade fm-training-cluster \
    --zone us-central1-a \
    --master \
    --cluster-version 1.33.1-gke.100 \
    --control-plane-soak-duration 168h  # 7-day soak period

# 3. After CP validation, complete the upgrade
gcloud beta container clusters upgrade fm-training-cluster \
    --zone us-central1-a \
    --complete-control-plane-upgrade

# 4. Node pool upgrade (GPU-specific strategy)
gcloud container node-pools upgrade h100-training \
    --cluster fm-training-cluster \
    --zone us-central1-a \
    --cluster-version 1.33.1-gke.100
```

### Emergency Patch Upgrades
For critical security patches during training:
```bash
# Patches bypass maintenance exclusions when manually triggered
gcloud container clusters upgrade fm-training-cluster \
    --zone us-central1-a \
    --master \
    --cluster-version 1.32.3-gke.200  # Latest patch
```

## Monitoring & Alerting Setup

### Training Run Protection Alerts
```yaml
# Cloud Monitoring alert for node cordoning
displayName: "H100 Training Nodes Cordoned"
conditions:
  - displayName: "Node cordoned during training"
    conditionThreshold:
      filter: 'resource.type="k8s_node" AND resource.labels.cluster_name="fm-training-cluster"'
      comparison: COMPARISON_GT
      thresholdValue: 0
```

### Pre-upgrade Health Checks
```bash
#!/bin/bash
# Pre-upgrade validation script
echo "=== Training Run Status ==="
kubectl get jobs -A --field-selector status.active=1

echo "=== H100 Node Health ==="
kubectl get nodes -l cloud.google.com/gke-nodepool=h100-training

echo "=== GPU Driver Status ==="
kubectl get daemonset -n kube-system nvidia-gpu-device-plugin

echo "=== Checkpoint Status ==="
# Verify latest checkpoints are accessible
gsutil ls gs://your-checkpoint-bucket/latest/
```

## Cost & Compliance Considerations

**Extended Channel Cost:** Additional cost applies only during the extended support period (months 15-24). First 14 months are free. For H100 training clusters, this cost is negligible compared to compute costs.

**FedRAMP/SOC2 Compliance:** This configuration meets strict regulatory requirements:
- Control plane receives security patches automatically
- No uncontrolled upgrades during production training
- Audit trail via maintenance exclusions and windows
- Manual approval required for disruptive changes

## Multi-Environment Strategy

**Recommended topology:**
- **Dev/Staging:** Regular channel with smaller GPU pools (A100 or T4)
- **Production:** Extended channel with H100s using this configuration
- **Validation:** Create staging jobs that run for 24-48 hours to test upgrade impacts

```bash
# Staging cluster for validation
gcloud container clusters create fm-training-staging \
    --release-channel regular \
    --zone us-central1-a \
    --machine-type a2-highgpu-1g \
    --accelerator type=nvidia-tesla-a100,count=1
```

## Key Benefits of This Configuration

1. **Maximum Control:** Extended channel + maintenance exclusions provide the most granular upgrade control available in GKE
2. **Security Maintained:** Control plane patches flow automatically; no security debt accumulation
3. **Training Protection:** Multi-week runs protected from forced interruption
4. **Cost Efficient:** No unnecessary 2x resource requirements during upgrades
5. **Compliance Ready:** Meets regulatory requirements for controlled environments
6. **Future Proof:** Scales to upcoming 100-node upgrade parallelism improvements

**Remember:** Never use "No channel" for new clusters. This Extended channel + exclusions approach provides superior control with better long-term supportability.