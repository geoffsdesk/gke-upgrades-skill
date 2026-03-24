# GKE Foundation Model Training Cluster Configuration

## Cluster Setup for Multi-Week Training Protection

### Core Cluster Configuration

```bash
# Create regional cluster with Extended channel for maximum upgrade control
gcloud container clusters create ai-training-cluster \
    --location us-central1 \
    --release-channel extended \
    --cluster-version 1.32.1-gke.1000 \
    --machine-type e2-standard-4 \
    --num-nodes 1 \
    --enable-ip-alias \
    --enable-shielded-nodes \
    --enable-network-policy \
    --disk-size 100GB \
    --disk-type pd-ssd \
    --logging=SYSTEM,WORKLOAD \
    --monitoring=SYSTEM
```

### Release Channel Strategy: Extended

**Why Extended Channel:**
- **24-month support period** (vs 14 months for other channels)
- **Manual control over minor upgrades** — minor versions are NOT auto-applied (except at end of extended support)
- **Only patches auto-applied** — security updates without disruptive changes
- **Extra cost only during extended period** — no additional charge during standard 14-month period
- **Full SLA** unlike Rapid channel

### Node Pool Architecture: Isolation Strategy

Create separate node pools for different workload types:

#### 1. Training Node Pool (H100 GPUs) — Maximum Protection

```bash
# H100 training pool with upgrade protection
gcloud container node-pools create h100-training \
    --cluster ai-training-cluster \
    --location us-central1 \
    --machine-type a3-highgpu-8g \
    --accelerator type=nvidia-h100-80gb,count=8 \
    --num-nodes 4 \
    --enable-autoscaling \
    --min-nodes 0 \
    --max-nodes 16 \
    --node-locations us-central1-a,us-central1-b \
    --disk-size 1000GB \
    --disk-type pd-ssd \
    --enable-gvnic \
    --placement-type COMPACT \
    --reservation-affinity any
```

#### 2. System Node Pool (Non-GPU workloads)

```bash
# System workloads pool - allows normal upgrades
gcloud container node-pools create system-workloads \
    --cluster ai-training-cluster \
    --location us-central1 \
    --machine-type c2-standard-16 \
    --num-nodes 2 \
    --enable-autoscaling \
    --min-nodes 1 \
    --max-nodes 8 \
    --disk-size 200GB \
    --disk-type pd-ssd
```

### Maintenance Configuration: Maximum Training Protection

```bash
# Configure maintenance window during planned downtime
gcloud container clusters update ai-training-cluster \
    --location us-central1 \
    --maintenance-window-start "2024-01-01T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Add persistent "no minor or node upgrades" exclusion for training pool
# This allows control plane security patches but blocks disruptive upgrades
gcloud container clusters update ai-training-cluster \
    --location us-central1 \
    --add-maintenance-exclusion-name "training-protection" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support

# Set conservative disruption intervals (90-day max)
gcloud container clusters update ai-training-cluster \
    --location us-central1 \
    --maintenance-minor-version-disruption-interval 90d \
    --maintenance-patch-version-disruption-interval 30d
```

### Training Node Pool Upgrade Strategy

For the H100 training pool specifically:

```bash
# Configure training pool for maximum protection during upgrades
gcloud container node-pools update h100-training \
    --cluster ai-training-cluster \
    --location us-central1 \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 1
```

**Why maxSurge=0, maxUnavailable=1:**
- H100 reservations typically have **no surge capacity** available
- `maxUnavailable=1` is the only effective lever for GPU pools with fixed reservations
- Drains one node at a time without requiring extra GPUs
- Causes temporary capacity dip but no additional resource requirements

### Per-Node Pool Maintenance Exclusions

Add training-specific exclusions to the H100 pool:

```bash
# Block ALL upgrades on training pool during training campaigns
gcloud container node-pools update h100-training \
    --cluster ai-training-cluster \
    --location us-central1 \
    --add-maintenance-exclusion-name "training-campaign-freeze" \
    --add-maintenance-exclusion-scope no_upgrades \
    --add-maintenance-exclusion-start-time "2024-03-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-03-30T23:59:59Z"
```

**Chain exclusions for longer training runs** (30-day max per exclusion):
```bash
# Second exclusion for extended training
gcloud container node-pools update h100-training \
    --cluster ai-training-cluster \
    --location us-central1 \
    --add-maintenance-exclusion-name "training-campaign-extend" \
    --add-maintenance-exclusion-scope no_upgrades \
    --add-maintenance-exclusion-start-time "2024-03-31T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-04-29T23:59:59Z"
```

### GPU-Specific Considerations

#### GPU Driver Compatibility
```bash
# Before any upgrade, verify driver compatibility in staging
gcloud container node-pools create h100-staging \
    --cluster ai-training-cluster \
    --location us-central1 \
    --machine-type a3-highgpu-8g \
    --accelerator type=nvidia-h100-80gb,count=8 \
    --num-nodes 1 \
    --cluster-version TARGET_VERSION

# Test CUDA compatibility
kubectl run cuda-test --image=nvidia/cuda:12.3-runtime-ubuntu22.04 \
    --restart=Never --rm -it -- nvidia-smi
```

#### Compact Placement for RDMA
```bash
# Ensure H100 nodes maintain RDMA topology after upgrades
gcloud compute resource-policies create group-placement h100-placement \
    --region us-central1 \
    --collocation COLLOCATED

# Apply to training pool
gcloud container node-pools update h100-training \
    --cluster ai-training-cluster \
    --location us-central1 \
    --placement-type COMPACT
```

### Training Workload Protection

#### Configure PDBs for Training Jobs
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
  namespace: training
spec:
  minAvailable: 7  # Keep 7 out of 8 H100 nodes during upgrades
  selector:
    matchLabels:
      app: foundation-model-training
```

#### Extended Termination Grace Period
```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: llm-training
  namespace: training
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 3600  # 1 hour for checkpointing
      containers:
      - name: training
        image: pytorch/pytorch:2.1-cuda12.1-runtime
        resources:
          limits:
            nvidia.com/gpu: 8
```

### Security and Patch Management

#### Enable Scheduled Upgrade Notifications
```bash
# Get 72-hour advance warning of control plane upgrades
gcloud container clusters update ai-training-cluster \
    --location us-central1 \
    --send-scheduled-upgrade-notifications
```

#### Monitor for Critical Security Patches
```bash
# Check for security-critical patches that may require emergency upgrades
gcloud container clusters get-upgrade-info ai-training-cluster \
    --location us-central1 \
    --format="yaml(autoUpgradeStatus,endOfStandardSupportTimestamp)"
```

### Operational Runbook for Training Campaigns

#### Before Starting Multi-Week Training:
1. **Apply training freeze exclusion:**
```bash
gcloud container node-pools update h100-training \
    --cluster ai-training-cluster \
    --location us-central1 \
    --add-maintenance-exclusion-name "training-run-$(date +%Y%m%d)" \
    --add-maintenance-exclusion-scope no_upgrades \
    --add-maintenance-exclusion-start-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --add-maintenance-exclusion-end-time "$(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ)"
```

2. **Verify cluster health and versions:**
```bash
kubectl get nodes -L cloud.google.com/gke-nodepool
kubectl get pods -n kube-system | grep -v Running
```

3. **Take checkpoint before training:**
```bash
# Enable checkpointing in training script
kubectl exec -n training POD_NAME -- python checkpoint.py --save
```

#### During Training Campaign:
- **Monitor exclusion expiration:** Set calendar reminders 5 days before exclusion expires
- **Chain exclusions if needed:** Add additional 30-day exclusions for longer runs
- **Monitor for emergency patches:** Check GKE release notes weekly

#### After Training Completion:
1. **Remove training exclusions:**
```bash
gcloud container clusters update ai-training-cluster \
    --location us-central1 \
    --remove-maintenance-exclusion-name "training-run-YYYYMMDD"
```

2. **Allow catch-up upgrades:**
```bash
# Check if cluster has fallen behind and needs updates
gcloud container clusters get-upgrade-info ai-training-cluster --location us-central1
```

### Monitoring and Alerting

#### Set up upgrade-related alerts:
```yaml
# Cloud Monitoring alert for stuck upgrades
displayName: "GKE Training Cluster Upgrade Stuck"
conditions:
  - displayName: "Upgrade operation running > 4 hours"
    conditionThreshold:
      filter: 'resource.type="gke_cluster" AND resource.label.cluster_name="ai-training-cluster"'
      comparison: COMPARISON_GREATER_THAN
      thresholdValue: 4
      duration: 3600s
```

### Cost Optimization

The Extended channel incurs additional costs only during the extended support period (months 15-24). During the standard support period (months 1-14), there's no extra charge.

**Expected cost impact:**
- **Months 1-14:** No additional cost vs Regular/Stable
- **Months 15-24:** ~20% additional cost for cluster management
- **Training protection value:** Avoiding forced EoS upgrades mid-training can save weeks of compute

## Summary Configuration

**Best practice setup for foundation model training:**
- ✅ **Extended release channel** — 24-month support, manual minor upgrades
- ✅ **Isolated training node pools** — H100s protected separately from system workloads  
- ✅ **Persistent "no minor or node" exclusion** — allows security patches, blocks disruptive changes
- ✅ **Per-campaign "no upgrades" exclusions** — complete freeze during training runs
- ✅ **maxSurge=0, maxUnavailable=1** — works with fixed GPU reservations
- ✅ **Conservative disruption intervals** — 90-day gaps between upgrades
- ✅ **Saturday 2-6 AM maintenance window** — predictable timing
- ✅ **Compact placement + RDMA preservation** — maintains training performance
- ✅ **Scheduled notifications** — 72h advance warning

This configuration provides maximum protection for multi-week training runs while maintaining security through automated control plane patches. The Extended channel gives you up to 24 months per version, and the exclusion strategy ensures training jobs are never interrupted by unexpected upgrades.