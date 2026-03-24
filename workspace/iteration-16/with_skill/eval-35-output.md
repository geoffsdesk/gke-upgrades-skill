# GKE Cluster Configuration for Foundation Model Training

## Cluster Architecture

### Base Configuration
```bash
# Regional cluster for HA control plane (prevents upgrade downtime)
gcloud container clusters create foundation-training-cluster \
  --region us-central1 \
  --release-channel stable \
  --enable-autoscaling \
  --enable-autorepair \
  --enable-autoupgrade \
  --maintenance-window-start 2024-01-06T06:00:00Z \
  --maintenance-window-end 2024-01-06T10:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA" \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --maintenance-minor-version-disruption-interval=90d \
  --maintenance-patch-version-disruption-interval=30d
```

### Multi-Pool Strategy (Critical for Training)
Create separate node pools for different workload types:

**1. Training Pool (H100s) - Maximum Protection**
```bash
gcloud container node-pools create training-h100 \
  --cluster foundation-training-cluster \
  --region us-central1 \
  --machine-type a3-highgpu-8g \
  --accelerator type=nvidia-h100-80gb,count=8 \
  --num-nodes 8 \
  --enable-autoscaling=false \
  --enable-autorepair=false \
  --enable-autoupgrade=false \
  --reservation-affinity consume-any-reservation \
  --placement-type COMPACT \
  --node-labels=workload=training,pool=h100-training \
  --node-taints=nvidia.com/gpu=present:NoSchedule
```

**2. Inference/Serving Pool (Smaller GPUs) - Moderate Protection**
```bash
gcloud container node-pools create inference-a100 \
  --cluster foundation-training-cluster \
  --region us-central1 \
  --machine-type a2-highgpu-4g \
  --accelerator type=nvidia-tesla-a100,count=4 \
  --enable-autoscaling \
  --min-nodes 2 \
  --max-nodes 10 \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1 \
  --node-labels=workload=inference,pool=a100-inference
```

**3. System/Utility Pool (CPU-only) - Standard Updates**
```bash
gcloud container node-pools create system-cpu \
  --cluster foundation-training-cluster \
  --region us-central1 \
  --machine-type c2-standard-16 \
  --enable-autoscaling \
  --min-nodes 3 \
  --max-nodes 20 \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0 \
  --node-labels=workload=system,pool=cpu-system
```

## Release Channel & Maintenance Strategy

### Channel Selection: **Stable**
- **Why Stable:** Slowest upgrade cadence with maximum validation
- Versions are battle-tested through Rapid→Regular→Stable promotion
- Full SLA coverage for upgrade stability
- Best balance of security patches + stability for production training

### Maintenance Exclusion Strategy
The cluster-level configuration above uses `no_minor_or_node_upgrades` with `until-end-of-support`:

**Benefits:**
- Control plane gets security patches automatically (maintains security posture)
- Node pools are protected from all upgrades during training campaigns
- Automatically renews when versions reach EoS (no manual exclusion management)
- Maximum control over both minor version timing and node disruption

**Per-Pool Granular Control:**
```bash
# Training pool: Additional per-pool protection
gcloud container node-pools update training-h100 \
  --cluster foundation-training-cluster \
  --region us-central1 \
  --add-maintenance-exclusion-name "training-freeze" \
  --add-maintenance-exclusion-scope no_upgrades \
  --add-maintenance-exclusion-start-time $(date -d "+1 day" -Iseconds) \
  --add-maintenance-exclusion-end-time $(date -d "+30 days" -Iseconds)

# Inference pool: Allow patches, block node upgrades
gcloud container node-pools update inference-a100 \
  --cluster foundation-training-cluster \
  --region us-central1 \
  --add-maintenance-exclusion-name "inference-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## GPU-Specific Upgrade Configuration

### H100 Training Pool Settings
```bash
# Configure upgrade strategy for GPU constraints
gcloud container node-pools update training-h100 \
  --cluster foundation-training-cluster \
  --region us-central1 \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

**Why maxSurge=0, maxUnavailable=1:**
- H100 reservations typically have no surge capacity
- `maxUnavailable=1` is the primary upgrade lever for GPU pools
- Drains one node at a time without needing extra GPUs
- For 8-node training, this means ~8 sequential upgrades (plan 2-4 hours total)

### GPU Driver Compatibility Verification
```bash
# Check GKE version → GPU driver mapping before any upgrade
gcloud container get-server-config --region us-central1 \
  --format="yaml(validNodeVersions)" | grep -A5 -B5 "1.30"

# Test target version in staging cluster first
# Verify CUDA compatibility with your training frameworks
```

## Training Workload Protection

### PodDisruptionBudgets
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
  namespace: training
spec:
  minAvailable: 7  # Allow max 1 pod disruption in 8-pod training job
  selector:
    matchLabels:
      app: foundation-training
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: inference-pdb
  namespace: inference
spec:
  minAvailable: "50%"  # Allow half of inference replicas to drain
  selector:
    matchLabels:
      app: model-serving
```

### StatefulSet Configuration for Training
```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: foundation-training
  namespace: training
spec:
  replicas: 8
  template:
    spec:
      terminationGracePeriodSeconds: 3600  # 1 hour for checkpoint save
      nodeSelector:
        workload: training
        pool: h100-training
      tolerations:
      - key: "nvidia.com/gpu"
        operator: "Equal"
        value: "present"
        effect: "NoSchedule"
      containers:
      - name: training
        image: gcr.io/PROJECT/training:latest
        resources:
          limits:
            nvidia.com/gpu: 8
            memory: "800Gi"
            cpu: "96"
          requests:
            nvidia.com/gpu: 8
            memory: "800Gi" 
            cpu: "96"
```

## Operational Procedures

### Pre-Training Setup
```bash
# 1. Verify cluster is in training-safe state
gcloud container clusters describe foundation-training-cluster \
  --region us-central1 \
  --format="value(currentMasterVersion)"

gcloud container node-pools list \
  --cluster foundation-training-cluster \
  --region us-central1

# 2. Activate training exclusions if not permanent
gcloud container node-pools update training-h100 \
  --cluster foundation-training-cluster \
  --region us-central1 \
  --add-maintenance-exclusion-name "training-run-$(date +%Y%m%d)" \
  --add-maintenance-exclusion-scope no_upgrades \
  --add-maintenance-exclusion-start-time $(date -Iseconds) \
  --add-maintenance-exclusion-end-time $(date -d "+21 days" -Iseconds)

# 3. Verify no pending upgrade operations
gcloud container operations list \
  --cluster foundation-training-cluster \
  --region us-central1 \
  --filter="operationType:UPGRADE"
```

### Planned Upgrade Windows (Between Training Campaigns)
```bash
# 1. Remove training exclusions during planned gaps
gcloud container node-pools update training-h100 \
  --cluster foundation-training-cluster \
  --region us-central1 \
  --remove-maintenance-exclusion-name "training-run-YYYYMMDD"

# 2. Manually trigger urgent upgrades if needed
gcloud container node-pools upgrade training-h100 \
  --cluster foundation-training-cluster \
  --region us-central1 \
  --cluster-version TARGET_VERSION

# 3. Validate upgrade before next training campaign
kubectl get nodes -l workload=training
kubectl get pods -n training
```

## Security & Compliance Balance

### Automated Security Patches
- **Control plane:** Always receives patches automatically (even with node exclusions)
- **System pools:** Regular patching via standard maintenance windows
- **Inference pools:** Patches allowed, controlled node upgrade timing
- **Training pools:** Patches blocked during active training, applied during gaps

### Monitoring & Alerting
```bash
# Configure upgrade notifications
gcloud container clusters update foundation-training-cluster \
  --region us-central1 \
  --send-scheduled-upgrade-notifications

# Monitor exclusion status
gcloud container clusters describe foundation-training-cluster \
  --region us-central1 \
  --format="yaml(maintenancePolicy)"
```

## Cost Optimization Notes

**Reservation Strategy:**
- Purchase committed use/reserved instances for H100 training pool (predictable 24/7 usage)
- Use on-demand for inference pools (variable load, can tolerate brief interruption)
- Consider Spot instances for development/testing node pools

**Upgrade Cost Impact:**
- Training pool: `maxUnavailable=1` avoids 2x GPU cost during upgrades
- System pool: Small surge (`maxSurge=2`) minimizes upgrade time
- No blue-green needed due to careful PDB + exclusion strategy

This configuration provides maximum protection for multi-week training runs while maintaining security through automated control plane patches and planned upgrade windows between training campaigns.