This is a critical operation that requires careful planning. Here's how to safely upgrade your GKE cluster while preserving your training run:

## Strategy: Blue-Green Node Pool Upgrade

### Phase 1: Prepare the New Node Pool

```yaml
# new-nodepool.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-plan
data:
  strategy: "blue-green-nodepool"
---
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerNodePool
metadata:
  name: h100-nodepool-v132
spec:
  cluster: your-cluster-name
  location: your-zone
  nodeCount: 64  # Same as current pool
  nodeConfig:
    machineType: a3-megagpu-8g
    guestAccelerator:
    - type: nvidia-h100-mega-80gb
      count: 8
      gpuDriverInstallationConfig:
        gpuDriverVersion: "LATEST"
    nodeLocations: 
    - your-zone-a
    - your-zone-b
    # Ensure same network topology
    networkConfig:
      enablePrivateNodes: true
    metadata:
      disable-legacy-endpoints: "true"
    oauthScopes:
    - "https://www.googleapis.com/auth/cloud-platform"
    taints:
    - key: "nvidia.com/gpu"
      value: "present"
      effect: "NO_SCHEDULE"
    - key: "training-v132"
      value: "true" 
      effect: "NO_SCHEDULE"
```

### Phase 2: Pre-upgrade Validation

```bash
#!/bin/bash
# pre-upgrade-check.sh

echo "=== Pre-upgrade validation ==="

# 1. Check training job status
kubectl get pods -l job=llm-training -o wide
kubectl logs -l job=llm-training --tail=50

# 2. Verify GPUDirect-TCPXO status
kubectl exec -it training-pod-0 -- nvidia-smi nvlink --status
kubectl exec -it training-pod-0 -- cat /proc/driver/nvidia/gpus/*/information

# 3. Check NCCL topology
kubectl exec -it training-pod-0 -- python3 -c "
import torch
print(f'NCCL version: {torch.cuda.nccl.version()}')
print(f'GPU count: {torch.cuda.device_count()}')
"

# 4. Backup training state
kubectl exec training-pod-0 -- python3 /training/checkpoint.py --force-checkpoint
```

### Phase 3: Control Plane Upgrade (Non-disruptive)

```bash
# Upgrade control plane first (doesn't affect running pods)
gcloud container clusters upgrade your-cluster-name \
    --master \
    --cluster-version=1.32.latest \
    --zone=your-zone \
    --quiet

# Verify control plane upgrade
kubectl version
```

### Phase 4: Create Checkpoint and Pause Strategy

```python
# checkpoint_manager.py
import torch
import torch.distributed as dist
import os
import time

class UpgradeCheckpointManager:
    def __init__(self, checkpoint_dir="/persistent-storage/checkpoints"):
        self.checkpoint_dir = checkpoint_dir
        
    def create_upgrade_checkpoint(self, model, optimizer, scheduler, step):
        """Create a comprehensive checkpoint before upgrade"""
        checkpoint_path = f"{self.checkpoint_dir}/pre_upgrade_step_{step}.pt"
        
        checkpoint = {
            'model_state_dict': model.state_dict(),
            'optimizer_state_dict': optimizer.state_dict(),
            'scheduler_state_dict': scheduler.state_dict(),
            'step': step,
            'timestamp': time.time(),
            'nccl_version': torch.cuda.nccl.version(),
            'cuda_version': torch.version.cuda,
            'upgrade_marker': True
        }
        
        if dist.get_rank() == 0:
            torch.save(checkpoint, checkpoint_path)
            print(f"Upgrade checkpoint saved: {checkpoint_path}")
            
        dist.barrier()
        return checkpoint_path

# In your training script, add:
if os.environ.get('PREPARE_FOR_UPGRADE') == 'true':
    checkpoint_manager = UpgradeCheckpointManager()
    checkpoint_path = checkpoint_manager.create_upgrade_checkpoint(
        model, optimizer, scheduler, current_step
    )
    print("Checkpoint complete. Ready for upgrade.")
    # Keep pods alive but pause training
    while True:
        time.sleep(30)
```

### Phase 5: Safe Node Pool Transition

```yaml
# updated-training-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: llm-training-v132
spec:
  template:
    spec:
      restartPolicy: Never
      nodeSelector:
        cloud.google.com/gke-nodepool: h100-nodepool-v132
      tolerations:
      - key: "nvidia.com/gpu"
        operator: "Equal"
        value: "present"
        effect: "NoSchedule"
      - key: "training-v132"
        operator: "Equal" 
        value: "true"
        effect: "NoSchedule"
      containers:
      - name: training
        image: your-training-image:v132
        env:
        - name: RESUME_FROM_CHECKPOINT
          value: "true"
        - name: CHECKPOINT_PATH
          value: "/persistent-storage/checkpoints/pre_upgrade_step_*.pt"
        resources:
          limits:
            nvidia.com/gpu: 8
        volumeMounts:
        - name: training-data
          mountPath: /persistent-storage
```

### Phase 6: Controlled Migration Script

```bash
#!/bin/bash
# controlled-migration.sh

set -e

echo "=== Starting controlled migration ==="

# 1. Signal training to checkpoint and pause
kubectl patch configmap training-config --patch '{"data":{"PREPARE_FOR_UPGRADE":"true"}}'

# 2. Wait for checkpoint completion
echo "Waiting for training checkpoint..."
while ! kubectl logs -l job=llm-training | grep -q "Checkpoint complete. Ready for upgrade"; do
    sleep 30
    echo "Still waiting for checkpoint..."
done

# 3. Verify checkpoint integrity
kubectl exec training-pod-0 -- python3 -c "
import torch
import glob
checkpoints = glob.glob('/persistent-storage/checkpoints/pre_upgrade_*.pt')
latest = max(checkpoints)
data = torch.load(latest, map_location='cpu')
print(f'Checkpoint verified: step {data[\"step\"]}, upgrade_marker: {data[\"upgrade_marker\"]}')
"

# 4. Create new node pool
kubectl apply -f new-nodepool.yaml

# 5. Wait for new nodes to be ready
echo "Waiting for new nodes..."
kubectl wait --for=condition=Ready nodes -l cloud.google.com/gke-nodepool=h100-nodepool-v132 --timeout=900s

# 6. Verify GPU connectivity on new nodes
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: gpu-test-v132
spec:
  selector:
    matchLabels:
      name: gpu-test-v132
  template:
    metadata:
      labels:
        name: gpu-test-v132
    spec:
      nodeSelector:
        cloud.google.com/gke-nodepool: h100-nodepool-v132
      tolerations:
      - operator: Exists
      containers:
      - name: gpu-test
        image: nvidia/cuda:12.3-runtime-ubuntu22.04
        command: ["/bin/sh", "-c", "nvidia-smi && sleep 3600"]
        resources:
          limits:
            nvidia.com/gpu: 1
EOF

# 7. Start new training job on v1.32 nodes
kubectl apply -f updated-training-job.yaml

# 8. Monitor new job startup
kubectl logs -f -l job=llm-training-v132

echo "=== Migration complete ==="
```

### Phase 7: Validation and Cleanup

```bash
#!/bin/bash
# post-upgrade-validation.sh

echo "=== Post-upgrade validation ==="

# 1. Verify training resumed correctly
kubectl logs -l job=llm-training-v132 --tail=100 | grep -E "(Resumed from|Training step)"

# 2. Check GPU interconnect
kubectl exec -it $(kubectl get pods -l job=llm-training-v132 -o name | head -1) -- \
    python3 -c "
import torch
import torch.distributed as dist
print(f'NCCL All-reduce test...')
dist.init_process_group(backend='nccl')
tensor = torch.randn(1000, 1000).cuda()
dist.all_reduce(tensor)
print('NCCL communication: OK')
"

# 3. Performance validation
kubectl exec -it training-pod-0 -- nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits

# 4. Clean up old resources after validation
if [ "$1" == "--cleanup" ]; then
    echo "Cleaning up old node pool..."
    gcloud container node-pools delete h100-nodepool-v131 \
        --cluster=your-cluster-name \
        --zone=your-zone \
        --quiet
    
    kubectl delete job llm-training
    kubectl delete daemonset gpu-test-v132
fi
```

## Key Safety Measures:

1. **Persistent Storage**: Ensure checkpoints are on persistent volumes that survive pod deletion
2. **Network Preservation**: New node pool maintains same network topology for GPUDirect-TCPXO
3. **Gradual Migration**: Blue-green approach eliminates downtime risk
4. **Rollback Plan**: Keep old node pool until new training is validated
5. **Monitoring**: Continuous validation of GPU interconnect performance

## Timeline Estimate:
- Control plane upgrade: 10-15 minutes
- Node pool creation: 15-20 minutes  
- Training migration: 5-10 minutes
- Total downtime: ~5-10 minutes (only during job transition)

This approach preserves your training progress while safely upgrading the infrastructure.