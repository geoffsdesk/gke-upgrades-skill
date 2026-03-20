Upgrading a large-scale training cluster with 512 H100 nodes and GPUDirect-TCPXO during active training requires careful planning. Here's a comprehensive approach:

## Pre-Upgrade Assessment

First, verify your current setup:

```bash
# Check current cluster version and node pool details
kubectl get nodes -o wide
gcloud container clusters describe CLUSTER_NAME --zone=ZONE

# Verify GPUDirect-TCPXO status
kubectl get nodes -o jsonpath='{.items[*].status.allocatable}' | grep nvidia.com/gpu
```

## Option 1: Blue-Green Cluster Migration (Recommended)

This is the safest approach for critical training workloads:

```bash
# 1. Create new cluster with GKE 1.30
gcloud container clusters create training-cluster-v130 \
  --zone=us-central1-a \
  --machine-type=a3-megagpu-8g \
  --num-nodes=512 \
  --cluster-version=1.30 \
  --enable-ip-alias \
  --enable-gvnic \
  --placement-type=COMPACT \
  --network=YOUR_NETWORK \
  --subnetwork=YOUR_SUBNET

# 2. Install GPU drivers and GPUDirect-TCPXO
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: nvidia-driver-installer
spec:
  selector:
    matchLabels:
      name: nvidia-driver-installer
  template:
    metadata:
      labels:
        name: nvidia-driver-installer
    spec:
      hostNetwork: true
      hostPID: true
      containers:
      - image: gcr.io/gke-release/nvidia-driver-installer@sha256:...
        name: nvidia-driver-installer
        securityContext:
          privileged: true
        env:
        - name: NVIDIA_INSTALL_DIR_HOST
          value: /home/kubernetes/bin/nvidia
EOF
```

## Option 2: Rolling Node Pool Replacement

For minimal disruption during training gaps:

```bash
# 1. Create new node pool with 1.30
gcloud container node-pools create training-pool-v130 \
  --cluster=training-cluster \
  --zone=us-central1-a \
  --machine-type=a3-megagpu-8g \
  --num-nodes=512 \
  --node-version=1.30 \
  --enable-gvnic \
  --placement-type=COMPACT

# 2. Cordon old nodes to prevent new scheduling
kubectl get nodes -l cloud.google.com/gke-nodepool=old-pool-name \
  -o name | xargs -I {} kubectl cordon {}

# 3. During a training checkpoint/pause, migrate workloads
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data
```

## Critical Configurations for H100 + GPUDirect-TCPXO

Ensure these settings are maintained during upgrade:

```yaml
# Node affinity for compact placement
apiVersion: v1
kind: Pod
spec:
  nodeSelector:
    cloud.google.com/gke-accelerator: nvidia-h100-mega-80gb
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
        - matchExpressions:
          - key: cloud.google.com/gke-placement-group-name
            operator: Exists
```

```bash
# Verify GPUDirect-TCPXO after upgrade
kubectl exec -it TRAINING_POD -- nvidia-smi topo -m
kubectl exec -it TRAINING_POD -- ibv_devinfo
```

## Training Checkpoint Strategy

Implement robust checkpointing before upgrade:

```python
# Example checkpoint script
import torch
import os

def create_upgrade_checkpoint():
    checkpoint = {
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'scheduler_state_dict': scheduler.state_dict(),
        'epoch': current_epoch,
        'step': global_step,
        'loss': current_loss,
        'rng_state': torch.get_rng_state(),
        'cuda_rng_state': torch.cuda.get_rng_state_all()
    }
    
    # Save to persistent storage (GCS)
    torch.save(checkpoint, f'gs://your-bucket/checkpoints/upgrade_checkpoint.pt')
    
    # Verify checkpoint integrity
    verify_checkpoint(checkpoint)
```

## Monitoring During Upgrade

Set up monitoring for the upgrade process:

```bash
# Monitor GPU utilization
kubectl top nodes --use-protocol-buffers
watch -n 5 'nvidia-smi -q -d UTILIZATION'

# Check interconnect status
kubectl exec -it TRAINING_POD -- \
  python -c "import torch; print(torch.cuda.nccl.version())"
```

## Step-by-Step Execution Plan

1. **Week Before Upgrade:**
   - Create comprehensive checkpoint
   - Test restoration on smaller cluster
   - Prepare new cluster configuration

2. **During Planned Maintenance Window:**
   ```bash
   # Pause training gracefully
   kubectl scale deployment training-job --replicas=0
   
   # Create final checkpoint
   kubectl exec TRAINING_POD -- python create_checkpoint.py
   
   # Begin cluster upgrade
   ```

3. **Post-Upgrade Verification:**
   ```bash
   # Verify all GPUs are accessible
   kubectl exec -it NEW_POD -- nvidia-smi -L
   
   # Test GPUDirect-TCPXO connectivity
   kubectl exec -it NEW_POD -- \
     python -c "import torch.distributed as dist; dist.init_process_group('nccl')"
   
   # Resume training from checkpoint
   kubectl apply -f training-job-v130.yaml
   ```

## Risk Mitigation

- **Always maintain persistent storage** for checkpoints outside the cluster
- **Test the upgrade process** on a smaller replica first
- **Have rollback plan** ready with the old cluster configuration
- **Monitor interconnect performance** closely after upgrade to ensure no regression

The blue-green approach is strongly recommended for your scale and criticality, even though it requires more resources temporarily. The investment in safety is worthwhile for multi-week training runs worth significant compute costs.