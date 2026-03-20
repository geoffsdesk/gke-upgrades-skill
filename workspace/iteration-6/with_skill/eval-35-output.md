# Foundation Model Training Cluster Configuration

## Recommended cluster architecture

**Base configuration:**
```bash
# Standard cluster (required for GPU control and advanced features)
gcloud container clusters create ml-training-cluster \
  --zone us-central1-a \
  --machine-type e2-standard-4 \
  --num-nodes 3 \
  --enable-autoscaling \
  --max-nodes 100 \
  --release-channel extended \
  --maintenance-window-start "2024-01-07T06:00:00Z" \
  --maintenance-window-end "2024-01-07T10:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU" \
  --enable-network-policy \
  --enable-ip-alias \
  --disk-size 100GB \
  --disk-type pd-ssd
```

## Release channel strategy: Extended

**Why Extended channel is optimal for training workloads:**
- **Up to 24 months** of support per version (vs 14 months for other channels)
- Same release timing as Regular channel, but longer support window
- Flexibility to defer upgrades during training campaigns
- Available for GKE 1.27+ (current versions support this)
- Additional cost (~10% premium) but essential for training stability

**Alternative if Extended not available:** Regular channel with aggressive maintenance exclusion chaining.

## Node pool architecture: Dedicated training isolation

Create separate node pools to isolate training from other workloads:

### 1. System pool (default, stays on auto-upgrade)
```bash
# Already created above - handles system pods, monitoring, etc.
# Keep this on auto-upgrade for security patches
```

### 2. Training pool (auto-upgrade DISABLED)
```bash
gcloud container node-pools create h100-training-pool \
  --cluster ml-training-cluster \
  --zone us-central1-a \
  --machine-type a3-highgpu-8g \
  --accelerator type=nvidia-h100-80gb,count=8 \
  --num-nodes 4 \
  --enable-autoscaling \
  --max-nodes 50 \
  --min-nodes 0 \
  --disk-size 2000GB \
  --disk-type pd-ssd \
  --no-enable-autoupgrade \
  --node-taints=training=true:NoSchedule \
  --node-labels=workload-type=training,gpu-type=h100 \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1 \
  --placement-type COMPACT \
  --reservation-affinity consume-reservation \
  --reservation H100_RESERVATION_NAME
```

**Key settings explained:**
- `--no-enable-autoupgrade`: Manual control over training pool upgrades
- `--max-surge-upgrade 0, --max-unavailable-upgrade 1`: Zero extra GPU capacity needed during upgrades (H100s are scarce)
- `--placement-type COMPACT`: Physical co-location for optimal GPU interconnect
- `--reservation-affinity`: Guaranteed H100 capacity
- Node taints: Prevent non-training pods from landing here

### 3. Inference/serving pool (auto-upgrade enabled)
```bash
gcloud container node-pools create inference-pool \
  --cluster ml-training-cluster \
  --zone us-central1-a \
  --machine-type n1-standard-16 \
  --accelerator type=nvidia-tesla-t4,count=2 \
  --num-nodes 2 \
  --enable-autoscaling \
  --max-nodes 20 \
  --min-nodes 0 \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0 \
  --node-labels=workload-type=inference
```

## Maintenance exclusion strategy

Use **"no minor or node upgrades"** exclusions to protect training while allowing security patches:

```bash
# Block disruptive upgrades during active training (up to version EoS)
gcloud container clusters update ml-training-cluster \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "training-campaign-q1" \
  --add-maintenance-exclusion-start-time "2024-01-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-04-15T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**Chain exclusions** to stay on a minor version until EoS:
```bash
# As Q1 exclusion expires, add Q2 if training continues
gcloud container clusters update ml-training-cluster \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "training-campaign-q2" \
  --add-maintenance-exclusion-start-time "2024-04-14T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-07-15T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

## Training workload protection

### Pod Disruption Budget for training jobs
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-job-pdb
  namespace: training
spec:
  selector:
    matchLabels:
      job-type: foundation-model-training
  maxUnavailable: 0  # Prevent ANY eviction during training
---
apiVersion: batch/v1
kind: Job
metadata:
  name: llm-training-job
  namespace: training
spec:
  template:
    metadata:
      labels:
        job-type: foundation-model-training
    spec:
      nodeSelector:
        workload-type: training
      tolerations:
      - key: training
        operator: Equal
        value: "true"
        effect: NoSchedule
      containers:
      - name: trainer
        image: your-training-image
        resources:
          requests:
            nvidia.com/gpu: 8
            memory: 1000Gi
            cpu: 100
          limits:
            nvidia.com/gpu: 8
            memory: 1000Gi
        env:
        - name: NCCL_DEBUG
          value: "INFO"
        terminationGracePeriodSeconds: 3600  # 1 hour for checkpoint save
```

### Checkpointing strategy
```yaml
# Training job with mandatory checkpointing every N steps
env:
- name: CHECKPOINT_FREQUENCY
  value: "1000"  # Steps between checkpoints
- name: CHECKPOINT_PATH
  value: "/gcs-mount/checkpoints/run-$(RUN_ID)"
volumeMounts:
- name: checkpoint-storage
  mountPath: /gcs-mount
volumes:
- name: checkpoint-storage
  csi:
    driver: gcsfuse.csi.storage.gke.io
    readOnly: false
    volumeAttributes:
      bucketName: ml-training-checkpoints
      mountOptions: "implicit-dirs"
```

## GPU-specific upgrade considerations

### Driver compatibility validation
```bash
# Before any training pool upgrade, test in staging
gcloud container node-pools create staging-h100-pool \
  --cluster staging-cluster \
  --zone us-central1-a \
  --machine-type a3-highgpu-8g \
  --accelerator type=nvidia-h100-80gb,count=8 \
  --num-nodes 1 \
  --cluster-version TARGET_GKE_VERSION

# Validate driver + CUDA + framework compatibility
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: gpu-compatibility-test
spec:
  restartPolicy: Never
  containers:
  - name: test
    image: nvcr.io/nvidia/pytorch:24.01-py3
    command: ["python", "-c", "import torch; print(f'CUDA: {torch.version.cuda}, Torch: {torch.__version__}'); print(f'GPU Count: {torch.cuda.device_count()}'); torch.cuda.is_available()"]
    resources:
      requests:
        nvidia.com/gpu: 1
      limits:
        nvidia.com/gpu: 1
EOF
```

### Network fabric considerations
H100 training relies on high-bandwidth GPU interconnect. Upgrades can break:
- **GPUDirect-TCPX** configuration
- **Compact placement** groups  
- **Custom MTU** settings for RDMA

Validate network performance after any upgrade:
```bash
# NCCL bandwidth test between GPUs
kubectl apply -f nccl-test-job.yaml
kubectl logs -f job/nccl-bandwidth-test
```

## Upgrade execution plan for training environments

### Quarterly maintenance windows
Schedule upgrades only between major training campaigns:

```bash
# Example: Upgrade training pool during model iteration gap
# 1. Complete current training run and save checkpoints
# 2. Cordon training nodes (prevent new scheduling)
kubectl cordon -l workload-type=training

# 3. Wait for graceful job completion (do NOT force-kill)
kubectl get jobs -n training --watch

# 4. Upgrade empty pool
gcloud container node-pools upgrade h100-training-pool \
  --cluster ml-training-cluster \
  --zone us-central1-a \
  --cluster-version TARGET_VERSION

# 5. Uncordon and validate
kubectl uncordon -l workload-type=training
kubectl apply -f gpu-compatibility-test.yaml
```

### Control plane upgrade timing
Control plane can upgrade independently (won't disrupt running training):
```bash
# Allow CP security patches during training campaigns
# Only the node pool upgrade is blocked by exclusions
gcloud container clusters upgrade ml-training-cluster \
  --zone us-central1-a \
  --master \
  --cluster-version PATCH_VERSION
```

## Security posture with upgrade deferrals

Balance training stability with security:

**Control plane**: Always allow patch upgrades (security fixes without workload disruption)
**System pool**: Keep on auto-upgrade (handles non-training workloads)  
**Training pool**: Manual upgrades only during scheduled gaps
**Monitoring**: Set up alerts for CVE tracking when upgrades are deferred

```bash
# Monitor security bulletins
gcloud logging sinks create security-alerts \
  bigquery.googleapis.com/projects/PROJECT/datasets/security_logs \
  --log-filter='resource.type="gke_cluster" AND jsonPayload.eventType="SECURITY_BULLETIN"'
```

## Summary configuration

| Component | Setting | Rationale |
|-----------|---------|-----------|
| **Release channel** | Extended | 24-month support window |
| **Training node pool** | Auto-upgrade disabled | Manual control during campaigns |
| **System/inference pools** | Auto-upgrade enabled | Security without training impact |
| **Maintenance exclusions** | "no minor or node upgrades" | Blocks disruption, allows CP patches |
| **Surge settings (training)** | `maxSurge=0, maxUnavailable=1` | No extra H100 capacity needed |
| **PDB** | `maxUnavailable: 0` | Zero tolerance for training interruption |
| **Maintenance window** | Sunday 6-10 AM | Off-peak, 4-hour window |

This architecture protects multi-week training runs while maintaining security through control plane patches and system pool updates. Plan training campaigns around quarterly maintenance windows for the H100 pool.