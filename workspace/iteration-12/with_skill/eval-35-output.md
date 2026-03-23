# GKE Cluster Configuration for H100 Foundation Model Training

## Executive Summary

For H100-based foundation model training with multi-week runs, your primary concern is **preventing any node-level disruption during active training campaigns**. This requires careful configuration of release channels, maintenance exclusions, and dedicated node pool isolation.

## Core Configuration Strategy

### 1. Release Channel Selection

**Recommendation: Regular or Stable channel** (NOT Rapid or Extended)

```bash
gcloud container clusters create training-cluster \
    --release-channel regular \
    --location us-central1-a
```

**Why Regular/Stable:**
- **Regular**: Full SLA, balanced security patching without bleeding-edge instability
- **Stable**: Maximum stability if you can tolerate slightly delayed patches
- **Avoid Rapid**: No SLA for upgrade stability - versions may have issues
- **Avoid Extended**: Minor upgrades are NOT automated, requiring manual intervention

### 2. Maintenance Exclusions for Training Protection

**Configure "no minor or node upgrades" exclusion** - this allows critical control plane security patches while blocking all disruptive changes:

```bash
gcloud container clusters update training-cluster \
    --location us-central1-a \
    --add-maintenance-exclusion-name "training-campaign-protection" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

**Key benefits:**
- Blocks node pool upgrades (the main disruption source)
- Blocks minor version upgrades
- Still allows control plane security patches
- Automatically tracks End of Support dates - no manual renewal needed

### 3. Node Pool Architecture

**Dedicated Training Pool Strategy:**

```bash
# Training node pool - H100 GPUs with upgrade protection
gcloud container node-pools create h100-training-pool \
    --cluster training-cluster \
    --location us-central1-a \
    --machine-type a3-highgpu-8g \
    --accelerator type=nvidia-h100-80gb,count=8 \
    --num-nodes 4 \
    --enable-autoscaling \
    --min-nodes 0 \
    --max-nodes 16 \
    --spot \
    --reservation-affinity any \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 1

# System/management node pool - separate from training workloads
gcloud container node-pools create system-pool \
    --cluster training-cluster \
    --location us-central1-a \
    --machine-type n2-standard-4 \
    --num-nodes 2 \
    --enable-autoscaling \
    --min-nodes 1 \
    --max-nodes 4
```

**Critical H100-specific settings:**
- `--max-surge-upgrade 0, --max-unavailable-upgrade 1`: H100 reservations typically have no surge capacity
- `--spot`: Significantly reduces costs for training workloads
- `--reservation-affinity any`: Uses your H100 reservation efficiently

### 4. Maintenance Windows

**Configure maintenance windows during planned training gaps:**

```bash
gcloud container clusters update training-cluster \
    --location us-central1-a \
    --maintenance-window-start "2024-01-15T02:00:00Z" \
    --maintenance-window-end "2024-01-15T06:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```

### 5. Training Campaign Workflow

**Before starting a multi-week training run:**

```bash
# 1. Verify no pending upgrades
gcloud container clusters get-upgrade-info training-cluster \
    --location us-central1-a

# 2. Ensure maintenance exclusion is active
gcloud container clusters describe training-cluster \
    --location us-central1-a \
    --format="value(maintenancePolicy.exclusions)"

# 3. Add temporary "no upgrades" exclusion if EoS is approaching
gcloud container clusters update training-cluster \
    --location us-central1-a \
    --add-maintenance-exclusion-name "active-training-freeze" \
    --add-maintenance-exclusion-start-time "2024-01-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-02-14T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
```

## Security and Compliance Balance

### Control Plane Patches (Still Allowed)

Your configuration allows control plane security patches while blocking node disruption:
- CVE fixes apply automatically to the control plane
- API server security updates don't affect running training jobs
- No pod restarts from control plane patches

### Monitoring for Security Updates

```bash
# Set up alerting for available upgrades
gcloud container clusters get-upgrade-info training-cluster \
    --location us-central1-a \
    --format="table(autoUpgradeStatus, minorTargetVersion, patchTargetVersion)"
```

### Planned Upgrade Windows

**Between training campaigns, perform comprehensive upgrades:**

```bash
# Remove training protection temporarily
gcloud container clusters update training-cluster \
    --location us-central1-a \
    --remove-maintenance-exclusion-name "training-campaign-protection"

# Upgrade node pool during training gap
gcloud container node-pools upgrade h100-training-pool \
    --cluster training-cluster \
    --location us-central1-a

# Restore protection before next training run
gcloud container clusters update training-cluster \
    --location us-central1-a \
    --add-maintenance-exclusion-name "training-campaign-protection" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

## Training Workload Configuration

### Pod Disruption Budget

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-job-pdb
spec:
  minAvailable: "100%"  # Prevent ANY eviction during training
  selector:
    matchLabels:
      app: foundation-model-training
```

### StatefulSet with Anti-Affinity

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: llm-training
spec:
  replicas: 4
  template:
    spec:
      nodeSelector:
        cloud.google.com/gke-nodepool: h100-training-pool
      tolerations:
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
          - labelSelector:
              matchLabels:
                app: foundation-model-training
            topologyKey: kubernetes.io/hostname
      containers:
      - name: training
        resources:
          requests:
            nvidia.com/gpu: 8
          limits:
            nvidia.com/gpu: 8
        terminationGracePeriodSeconds: 300  # Allow graceful checkpoint saving
```

## Monitoring and Alerting

### Key Metrics to Track

```bash
# Check for forced upgrades due to EoS
gcloud logging read 'resource.type="gke_cluster" 
protoPayload.methodName="google.container.v1.ClusterManager.UpdateCluster"
protoPayload.request.update.desiredMasterVersion!=""' \
--limit=10 --format=json

# Monitor training job stability
kubectl top pods -n training --containers | grep training
```

### Upgrade Notifications

Enable 72-hour advance notifications (preview feature):

```bash
gcloud container clusters update training-cluster \
    --location us-central1-a \
    --enable-scheduled-upgrade-notifications
```

## Summary Configuration Checklist

- [x] **Release channel**: Regular or Stable (full SLA, predictable timing)
- [x] **Maintenance exclusion**: "no minor or node upgrades" scope with end-of-support tracking
- [x] **Node pools**: Dedicated H100 training pool isolated from system workloads  
- [x] **Upgrade settings**: `maxSurge=0, maxUnavailable=1` (no surge capacity assumption)
- [x] **Maintenance windows**: Aligned with planned training gaps
- [x] **PDB protection**: 100% availability requirement for active training jobs
- [x] **Monitoring**: Upgrade notifications and EoS tracking enabled

This configuration provides maximum protection for multi-week training runs while maintaining essential security patches and a clear upgrade path during planned maintenance windows.