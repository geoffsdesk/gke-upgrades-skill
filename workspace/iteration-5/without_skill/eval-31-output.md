This is a challenging scenario that requires careful planning. Here's a comprehensive approach to upgrade your GKE cluster without disrupting your training run:

## Option 1: Blue-Green Cluster Strategy (Recommended)

### Create a New Cluster
```bash
# Create new cluster with GKE 1.30
gcloud container clusters create llm-training-v130 \
  --zone=us-central1-a \
  --machine-type=a3-megagpu-8g \
  --num-nodes=64 \
  --node-locations=us-central1-a \
  --cluster-version=1.30 \
  --enable-ip-alias \
  --enable-network-policy \
  --enable-autoscaling \
  --max-nodes=64 \
  --min-nodes=64 \
  --accelerator type=nvidia-h100-mega-80gb,count=8 \
  --enable-gvnic \
  --enable-private-nodes \
  --master-ipv4-cidr 172.16.0.0/28 \
  --enable-shielded-nodes
```

### Preserve Training State
```yaml
# Create checkpoint PVC that spans both clusters
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: training-checkpoints
spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 10Ti
  storageClassName: filestore-csi
```

### Migration Strategy
1. **Let current training complete its epoch/checkpoint cycle**
2. **Pause training gracefully** at next checkpoint
3. **Deploy to new cluster** with same GPUDirect-TCPXO configuration
4. **Resume from checkpoint**

## Option 2: In-Place Node Pool Replacement

### Create New Node Pool
```bash
# Create new node pool with 1.30
gcloud container node-pools create llm-training-130 \
  --cluster=llm-training-cluster \
  --zone=us-central1-a \
  --machine-type=a3-megagpu-8g \
  --num-nodes=64 \
  --node-version=1.30 \
  --accelerator type=nvidia-h100-mega-80gb,count=8 \
  --enable-autoscaling \
  --max-nodes=64 \
  --min-nodes=0
```

### Gradual Migration DaemonSet
```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: node-migration-controller
spec:
  selector:
    matchLabels:
      app: node-migration
  template:
    spec:
      tolerations:
      - key: nvidia.com/gpu
        operator: Exists
      containers:
      - name: migration-controller
        image: gcr.io/your-project/migration-controller:latest
        env:
        - name: OLD_NODE_POOL
          value: "default-pool"
        - name: NEW_NODE_POOL  
          value: "llm-training-130"
        - name: TRAINING_JOB_NAME
          value: "llm-training-job"
```

## Critical GPUDirect-TCPXO Considerations

### Maintain GPU Topology
```yaml
# Ensure proper GPU placement
apiVersion: v1
kind: Pod
spec:
  nodeSelector:
    cloud.google.com/gke-nodepool: llm-training-130
    nvidia.com/gpu.product: H100-MEGA-80GB
  tolerations:
  - key: nvidia.com/gpu
    operator: Exists
  containers:
  - name: training
    resources:
      limits:
        nvidia.com/gpu: 8
    env:
    - name: NCCL_CROSS_NIC
      value: "0"
    - name: NCCL_NET_GDR_LEVEL
      value: "5"
    - name: NCCL_GPUDIRECTTCPX_FORCE_ACK
      value: "0"
```

### Network Configuration Validation
```bash
# Validate TCPXO after migration
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: tcpxo-validation
spec:
  parallelism: 512
  template:
    spec:
      containers:
      - name: nccl-test
        image: nvcr.io/nvidia/pytorch:23.10-py3
        command: ["/usr/local/bin/all_reduce_perf_mpi"]
        args: ["-b", "1G", "-e", "8G", "-i", "2"]
        resources:
          limits:
            nvidia.com/gpu: 8
EOF
```

## Checkpoint Management Strategy

### Enhanced Checkpoint Script
```python
import torch
import torch.distributed as dist
import os
import time

class CheckpointManager:
    def __init__(self, checkpoint_dir="/shared/checkpoints"):
        self.checkpoint_dir = checkpoint_dir
        self.migration_signal_file = f"{checkpoint_dir}/.migration_requested"
    
    def should_checkpoint_for_migration(self):
        return os.path.exists(self.migration_signal_file)
    
    def save_migration_checkpoint(self, model, optimizer, epoch, step):
        if dist.get_rank() == 0:
            checkpoint = {
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'epoch': epoch,
                'step': step,
                'migration_checkpoint': True,
                'timestamp': time.time()
            }
            
            migration_path = f"{self.checkpoint_dir}/migration_checkpoint.pt"
            torch.save(checkpoint, migration_path)
            
            # Signal migration ready
            with open(f"{self.checkpoint_dir}/.migration_ready", 'w') as f:
                f.write(str(time.time()))
```

## Monitoring During Migration

### Migration Health Check
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: migration-monitor
data:
  monitor.sh: |
    #!/bin/bash
    while true; do
      # Check GPU utilization
      nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits
      
      # Check NCCL health
      if [ -f /tmp/nccl_trace.log ]; then
        tail -n 10 /tmp/nccl_trace.log
      fi
      
      # Check training progress
      kubectl logs -l app=llm-training --tail=5
      
      sleep 30
    done
```

## Step-by-Step Migration Process

### 1. Preparation Phase
```bash
# Set migration signal
kubectl create configmap migration-control \
  --from-literal=phase="prepare" \
  --from-literal=target_checkpoint="epoch_100"

# Increase checkpoint frequency
kubectl patch deployment llm-training \
  -p '{"spec":{"template":{"spec":{"containers":[{"name":"trainer","env":[{"name":"CHECKPOINT_INTERVAL","value":"100"}]}]}}}}'
```

### 2. Checkpoint and Pause
```bash
# Signal for migration checkpoint
kubectl create configmap migration-signal \
  --from-literal=migrate="true"

# Wait for checkpoint completion
kubectl wait --for=condition=complete job/checkpoint-job --timeout=1800s
```

### 3. Deploy to New Infrastructure
```bash
# Apply training job to new cluster
kubectl --context=new-cluster apply -f training-job-v130.yaml

# Verify GPU topology
kubectl --context=new-cluster exec -it llm-training-0 -- nvidia-smi topo -m
```

### 4. Resume Training
```bash
# Resume from migration checkpoint
kubectl --context=new-cluster patch deployment llm-training \
  -p '{"spec":{"template":{"spec":{"containers":[{"name":"trainer","env":[{"name":"RESUME_FROM","value":"/shared/checkpoints/migration_checkpoint.pt"}]}]}}}}'
```

## Rollback Strategy

```bash
# If issues arise, quick rollback
kubectl --context=old-cluster patch deployment llm-training \
  -p '{"spec":{"replicas":512}}'

# Restore from same checkpoint
kubectl --context=old-cluster set env deployment/llm-training \
  RESUME_FROM=/shared/checkpoints/migration_checkpoint.pt
```

## Key Success Factors

1. **Use shared storage** (Filestore/Persistent Disks) for checkpoints
2. **Validate GPU topology** before resuming training
3. **Monitor NCCL performance** during first few hours
4. **Keep old cluster** running until validation complete
5. **Test migration process** on smaller replica first

This approach minimizes training disruption while ensuring your GPU interconnect remains optimally configured.