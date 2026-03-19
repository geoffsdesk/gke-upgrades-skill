# GKE Configuration for H100 Foundation Model Training

## Recommended Cluster Configuration

### Release Channel Strategy
**Primary recommendation: Extended channel**
- Provides up to 24 months of support (vs 14 months for other channels)
- Same feature velocity as Regular channel, but longer support window
- Critical for AI workloads where training campaigns can span months
- Extra cost is minimal compared to H100 compute costs
- Available for GKE 1.27+

**Multi-environment approach:**
- Dev/experimental clusters: Regular channel (faster access to new features)
- Production training clusters: Extended channel (maximum stability)

### Cluster Mode
**Standard clusters** (not Autopilot) for the following reasons:
- Full control over node pool upgrade timing
- SSH access for debugging GPU issues
- Custom node configurations (high-memory ratios, local SSDs)
- Support for GPUDirect-TCPX and RDMA networking
- Required for >15,000 node clusters (contact Cloud Customer Care for 65k node limit)

### Node Pool Architecture

```bash
# Training node pool (H100s) - maximum isolation
gcloud container node-pools create h100-training \
  --cluster=foundation-training \
  --zone=us-central1-a \
  --machine-type=a3-highgpu-8g \
  --accelerator=type=nvidia-h100-80gb,count=8 \
  --num-nodes=32 \
  --enable-autoscaling \
  --min-nodes=0 \
  --max-nodes=128 \
  --disk-size=2000 \
  --disk-type=pd-ssd \
  --enable-autorepair=false \
  --enable-autoupgrade=false \
  --node-locations=us-central1-a,us-central1-b,us-central1-c \
  --placement-type=COMPACT \
  --node-taints=training=true:NoSchedule

# System/management node pool (separate from training)
gcloud container node-pools create system-pool \
  --cluster=foundation-training \
  --zone=us-central1-a \
  --machine-type=n2-standard-4 \
  --num-nodes=3 \
  --enable-autoscaling \
  --min-nodes=2 \
  --max-nodes=10 \
  --enable-autorepair \
  --enable-autoupgrade
```

**Key decisions:**
- **Disable auto-upgrade on H100 pool**: `--enable-autoupgrade=false` gives you manual control
- **Disable auto-repair initially**: H100 nodes are expensive; you want control over when they're replaced
- **Compact placement**: Ensures GPUDirect performance within the pool
- **Node taints**: Prevents accidental scheduling of non-training workloads on expensive GPUs
- **Separate system pool**: Keeps cluster services isolated and upgradeable

## Maintenance Configuration

### Maintenance Windows
```bash
# Configure maintenance window during low-activity periods
gcloud container clusters update foundation-training \
  --zone=us-central1-a \
  --maintenance-window-start "2024-12-15T02:00:00Z" \
  --maintenance-window-end "2024-12-15T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```

### Critical Maintenance Exclusion Strategy

**"No minor or node upgrades" exclusion** (recommended for training clusters):
```bash
# Block disruptive upgrades while allowing security patches
gcloud container clusters update foundation-training \
  --zone=us-central1-a \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-start-time "2024-12-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-06-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**This exclusion:**
- Blocks minor version upgrades (1.29 → 1.30) that could break training
- Blocks node pool upgrades that would restart H100s
- **Still allows** control plane security patches
- Can be extended up to the version's End of Support date
- Gives you complete control over when disruptive changes happen

### Emergency Override
For critical security issues or training gaps:
```bash
# 30-day complete freeze (blocks even patches)
gcloud container clusters update foundation-training \
  --zone=us-central1-a \
  --add-maintenance-exclusion-name "emergency-freeze" \
  --add-maintenance-exclusion-start-time "2024-12-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-01-15T00:00:00Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## H100-Specific Considerations

### GPU Driver Compatibility
```bash
# Verify CUDA version before any upgrades
kubectl get nodes -o json | jq -r '.items[] | select(.status.allocatable."nvidia.com/gpu") | {name: .metadata.name, cuda: .status.nodeInfo.kubeletVersion}'

# Test target GKE version in staging first
gcloud container clusters create staging-gpu-test \
  --zone=us-central1-a \
  --cluster-version=TARGET_VERSION \
  --machine-type=a3-highgpu-8g \
  --num-nodes=1
```

**Critical:** GKE auto-installs GPU drivers matching the target version. A minor GKE upgrade can change CUDA from 12.2 to 12.4, breaking your training framework. Always test the full stack (GKE + CUDA + PyTorch/JAX) in staging before production upgrades.

### Node Pool Upgrade Strategy (when needed)
```bash
# For H100 pools, use minimal disruption settings
gcloud container node-pools update h100-training \
  --cluster=foundation-training \
  --zone=us-central1-a \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=0
```

**Strategy selection:**
- **If H100 quota available**: Surge upgrade with `maxSurge=1, maxUnavailable=0`
- **If quota is tight**: `maxSurge=0, maxUnavailable=1` (drains first, no extra GPUs needed)
- **For instant rollback needs**: Blue-green (requires 2x quota but enables fast rollback)

### Training Job Protection

**PDB Configuration:**
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
spec:
  maxUnavailable: 0  # Prevent any training pod eviction
  selector:
    matchLabels:
      app: foundation-training
```

**Checkpoint Strategy:**
```yaml
# Add to training job spec
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 3600  # 1 hour for checkpoint save
      containers:
      - name: trainer
        # Ensure SIGTERM handler saves checkpoint
        # GKE waits up to 1 hour before force-kill
```

## Monitoring & Alerting Setup

```bash
# Enable GKE usage metering for cost tracking
gcloud container clusters update foundation-training \
  --zone=us-central1-a \
  --enable-network-policy \
  --enable-usage-metering

# Configure cluster notifications
gcloud logging sinks create gke-upgrade-alerts \
  bigquery.googleapis.com/projects/PROJECT_ID/datasets/gke_logs \
  --log-filter='resource.type="gke_cluster" AND severity>=WARNING'
```

**Key metrics to monitor:**
- GPU utilization per node (`nvidia-smi` via DaemonSet)
- Training throughput (tokens/second, samples/second)
- Checkpoint frequency and duration
- Node availability and replacement events
- Auto-upgrade target changes (indicates incoming forced upgrades)

## Operational Workflow

### Planned Upgrade Process
1. **Training campaign planning**: Schedule upgrade windows between training runs
2. **Staging validation**: Test target GKE version with your training stack
3. **Remove maintenance exclusion**: Enable upgrades during the planned window
4. **Upgrade system pool first**: Validate cluster services still work
5. **Cordon training pool**: `kubectl cordon -l cloud.google.com/gke-nodepool=h100-training`
6. **Wait for training jobs to complete naturally** (don't force-evict)
7. **Upgrade empty H100 pool**: Run upgrade on idle nodes
8. **Restore maintenance exclusions**: Re-enable training protection

### End of Support Management
With Extended channel, you have ~24 months per version. When approaching EoS:
1. **6 months before EoS**: Begin upgrade planning and testing
2. **3 months before EoS**: Execute upgrade during training gap
3. **Never let it reach EoS**: Forced upgrades will restart all GPUs simultaneously

## Cost Optimization Notes

- **Preemptible H100s**: Not recommended for multi-week training (24-hour max lifetime)
- **Reservations**: Consider committed use discounts for predictable training schedules
- **Auto-scaling**: Set `min-nodes=0` to scale down during idle periods
- **Regional persistent disks**: For checkpoint storage that survives node replacement

This configuration provides maximum protection for long-running training while maintaining security through control plane patches. The key is using maintenance exclusions proactively rather than reactively.