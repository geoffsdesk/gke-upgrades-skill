# GKE Cluster Configuration for Foundation Model Training

## Recommended Cluster Architecture

### Primary Configuration
```bash
# Control plane on Regular channel with maintenance exclusions for training periods
gcloud container clusters create foundation-training \
  --zone us-central1-a \
  --release-channel regular \
  --enable-autoscaling \
  --min-nodes 0 \
  --max-nodes 1000 \
  --machine-type n2d-standard-32 \
  --disk-size 200GB \
  --enable-autorepair \
  --enable-autoupgrade \
  --maintenance-window-start "2024-01-13T06:00:00Z" \
  --maintenance-window-end "2024-01-13T10:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA" \
  --workload-pool PROJECT_ID.svc.id.goog
```

**Why Regular channel?** Provides a good balance of security patches and stability. Versions arrive ~2-4 weeks after Rapid, giving time for community validation while maintaining SLA coverage.

### Node Pool Strategy: Segregated Training Infrastructure

```bash
# 1. Training node pool - auto-upgrade DISABLED for maximum protection
gcloud container node-pools create training-h100 \
  --cluster foundation-training \
  --zone us-central1-a \
  --machine-type a3-highgpu-8g \
  --accelerator type=nvidia-h100-80gb,count=8 \
  --num-nodes 4 \
  --min-nodes 0 \
  --max-nodes 64 \
  --enable-autorepair \
  --no-enable-autoupgrade \
  --disk-size 2TB \
  --disk-type pd-ssd \
  --placement-type COMPACT \
  --max-pods-per-node 16 \
  --node-labels=workload=training,gpu=h100 \
  --node-taints=training-only=true:NoSchedule

# 2. Infrastructure node pool - auto-upgrade enabled for security
gcloud container node-pools create infrastructure \
  --cluster foundation-training \
  --zone us-central1-a \
  --machine-type n2d-standard-16 \
  --num-nodes 3 \
  --min-nodes 2 \
  --max-nodes 10 \
  --enable-autorepair \
  --enable-autoupgrade \
  --disk-size 200GB \
  --node-labels=workload=infrastructure \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

## Maintenance Strategy

### 1. Control Plane: Automated with Training Protection

```bash
# Primary protection: "No minor or node upgrades" exclusion during training campaigns
# This allows security patches on control plane but blocks all node disruption
gcloud container clusters update foundation-training \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "q1-training-campaign" \
  --add-maintenance-exclusion-start-time "2024-02-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-04-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Maintenance window: Saturday 6-10 AM UTC (Friday night US West Coast)
# Control plane patches will auto-apply during this window when no exclusion is active
```

### 2. Training Nodes: Manual Upgrade Only

Training node pools have auto-upgrade **disabled** and will only be upgraded during planned gaps between training runs. This gives you complete control over timing.

**Upgrade procedure for training pools:**
```bash
# During planned training gaps only
# Step 1: Cordon training nodes to prevent new workload scheduling
kubectl cordon -l workload=training

# Step 2: Wait for current training jobs to complete naturally
# (Use checkpointing to allow graceful completion)

# Step 3: Upgrade empty training pool
gcloud container node-pools upgrade training-h100 \
  --cluster foundation-training \
  --zone us-central1-a \
  --cluster-version TARGET_VERSION

# Step 4: Uncordon after upgrade
kubectl uncordon -l workload=training
```

## GPU-Specific Configuration

### Driver and CUDA Compatibility
```bash
# Enable GPU sharing if needed for smaller jobs
--enable-gpu-partition

# Ensure driver compatibility - GKE auto-installs drivers
# Always test target GKE version in staging first
# H100 requires CUDA 11.8+ and compatible drivers
```

### Network Configuration for Multi-Node Training
```bash
# High-MTU VPC for RDMA/GPUDirect (required for multi-node H100 training)
gcloud compute networks create training-vpc \
  --mtu 8896 \
  --subnet-mode regional

gcloud compute networks subnets create training-subnet \
  --network training-vpc \
  --region us-central1 \
  --range 10.1.0.0/16

# Use this VPC when creating the cluster
--network training-vpc \
--subnetwork training-subnet
```

### Compact Placement for Performance
The training node pool uses `--placement-type COMPACT` to ensure H100 nodes are physically co-located for maximum interconnect performance.

## Workload Configuration

### Training Job PDB Protection
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
  namespace: training
spec:
  maxUnavailable: 0  # Prevent ANY eviction during training
  selector:
    matchLabels:
      job-type: foundation-training
```

### Toleration for Training Nodes
```yaml
# Training workloads must include this toleration
tolerations:
- key: "training-only"
  operator: "Equal"
  value: "true"
  effect: "NoSchedule"
```

### Checkpointing Configuration
```yaml
# Example training job with checkpointing
spec:
  template:
    spec:
      containers:
      - name: trainer
        env:
        - name: CHECKPOINT_INTERVAL
          value: "3600"  # Checkpoint every hour
        - name: RESUME_FROM_CHECKPOINT
          value: "true"
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /checkpoints
      volumes:
      - name: checkpoint-storage
        persistentVolumeClaim:
          claimName: training-checkpoints
```

## Monitoring and Alerting

```bash
# Key metrics to monitor during training
kubectl top nodes --selector=workload=training
kubectl get events --field-selector involvedObject.kind=Pod -w

# GPU utilization monitoring
kubectl apply -f https://raw.githubusercontent.com/GoogleCloudPlatform/container-engine-accelerators/master/nvidia-driver-installer/cos/daemonset-preloaded.yaml
```

## Upgrade Timeline Planning

### Recommended Schedule
1. **Control plane patches**: Auto-apply during Saturday maintenance windows (when no exclusion active)
2. **Infrastructure node pools**: Auto-upgrade during maintenance windows
3. **Training node pools**: Manual upgrade only during planned 2-week gaps between major training campaigns
4. **Major version upgrades**: Plan 1-month gaps for full cluster upgrade (control plane + all node pools)

### Training Campaign Protection Process
```bash
# Before starting multi-week training
gcloud container clusters update foundation-training \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "training-$(date +%Y%m%d)" \
  --add-maintenance-exclusion-start-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-end-time "TRAINING_END_DATE" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# After training completes
gcloud container clusters update foundation-training \
  --zone us-central1-a \
  --remove-maintenance-exclusion-name "training-$(date +%Y%m%d)"
```

## Security Considerations

- **Control plane** stays current with security patches via auto-upgrade + maintenance windows
- **Infrastructure nodes** receive timely security updates via auto-upgrade
- **Training nodes** are manually updated during planned gaps - accept this trade-off for training protection
- **Network security**: Use private cluster with authorized networks for production
- **Workload isolation**: Training workloads run on dedicated tainted nodes

This configuration provides maximum protection for multi-week training runs while maintaining security through automated patching of non-training infrastructure. The segregated node pool strategy lets you upgrade different components on different schedules based on their criticality and disruption tolerance.