This is a complex upgrade scenario that requires careful planning. Here's a comprehensive approach to upgrade your GKE cluster without disrupting your training workload:

## 1. Pre-Upgrade Assessment and Preparation

### Validate GPU Direct-TCPXO Compatibility
```bash
# Check current TCPXO driver version
kubectl get nodes -o custom-columns=NAME:.metadata.name,TCPXO:.status.nodeInfo.kernelVersion

# Verify TCPXO pods are running
kubectl get pods -n kube-system -l app=tcpxo-daemon

# Document current network topology
kubectl get nodes --show-labels | grep cloud.google.com/gke-accelerator
```

### Create a Staging Environment
```bash
# Create a small test cluster with 1.32
gcloud container clusters create test-upgrade-cluster \
  --zone=us-central1-a \
  --machine-type=a3-megagpu-8g \
  --num-nodes=2 \
  --cluster-version=1.32 \
  --enable-ip-alias \
  --enable-gvnic \
  --placement-type=COMPACT \
  --network-performance-configs=total-egress-bandwidth-tier=TIER_1
```

## 2. Blue-Green Cluster Strategy (Recommended)

### Step 1: Create New Cluster with 1.32
```yaml
# new-cluster-config.yaml
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerCluster
metadata:
  name: training-cluster-v132
spec:
  location: us-central1-a
  initialNodeCount: 1
  minMasterVersion: "1.32"
  nodeVersion: "1.32"
  releaseChannel:
    channel: REGULAR
  networkingMode: VPC_NATIVE
  ipAllocationPolicy:
    useIpAliases: true
  networkPerformanceConfig:
    totalEgressBandwidthTier: TIER_1
```

### Step 2: Create GPU Node Pool
```bash
gcloud container node-pools create h100-pool \
  --cluster=training-cluster-v132 \
  --zone=us-central1-a \
  --machine-type=a3-megagpu-8g \
  --accelerator=type=nvidia-h100-mega-80gb,count=8 \
  --num-nodes=64 \
  --enable-autoscaling \
  --max-nodes=512 \
  --min-nodes=64 \
  --node-taints=nvidia.com/gpu=present:NoSchedule \
  --node-labels=accelerator=nvidia-h100 \
  --placement-type=COMPACT \
  --enable-gvnic \
  --disk-type=pd-ssd \
  --disk-size=200GB
```

### Step 3: Install GPU and TCPXO Components
```yaml
# gpu-tcpxo-setup.yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: nvidia-driver-installer
  namespace: kube-system
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
      - image: gcr.io/gke-release/nvidia-driver-installer@sha256:latest
        name: nvidia-driver-installer
        resources:
          requests:
            cpu: 0.15
        securityContext:
          privileged: true
        env:
        - name: NVIDIA_INSTALL_DIR_HOST
          value: /home/kubernetes/bin/nvidia
        volumeMounts:
        - name: nvidia-install-dir-host
          mountPath: /usr/local/nvidia
        - name: dev
          mountPath: /dev
      volumes:
      - name: nvidia-install-dir-host
        hostPath:
          path: /home/kubernetes/bin/nvidia
      - name: dev
        hostPath:
          path: /dev
      nodeSelector:
        accelerator: nvidia-h100
---
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: tcpxo-daemon
  namespace: kube-system
spec:
  selector:
    matchLabels:
      name: tcpxo-daemon
  template:
    metadata:
      labels:
        name: tcpxo-daemon
    spec:
      hostNetwork: true
      containers:
      - name: tcpxo-daemon
        image: gcr.io/gke-release/tcpxo:latest
        securityContext:
          privileged: true
        volumeMounts:
        - name: proc
          mountPath: /host/proc
        - name: sys
          mountPath: /host/sys
      volumes:
      - name: proc
        hostPath:
          path: /proc
      - name: sys
        hostPath:
          path: /sys
      nodeSelector:
        accelerator: nvidia-h100
```

## 3. In-Place Upgrade Strategy (Alternative)

If you must upgrade in-place, use a rolling upgrade approach:

### Step 1: Upgrade Control Plane First
```bash
# Upgrade master (minimal disruption)
gcloud container clusters upgrade training-cluster \
  --master \
  --cluster-version=1.32 \
  --zone=us-central1-a
```

### Step 2: Rolling Node Pool Upgrade
```bash
# Create new node pool with 1.32
gcloud container node-pools create h100-pool-v132 \
  --cluster=training-cluster \
  --zone=us-central1-a \
  --machine-type=a3-megagpu-8g \
  --accelerator=type=nvidia-h100-mega-80gb,count=8 \
  --num-nodes=64 \
  --node-version=1.32 \
  --placement-type=COMPACT

# Gradually migrate workloads
kubectl cordon <old-nodes>
kubectl drain <old-nodes> --ignore-daemonsets --delete-emptydir-data --grace-period=300
```

## 4. Checkpoint and Migration Strategy

### Implement Checkpointing
```python
# training-checkpoint.py
import torch
import os
from datetime import datetime

def save_checkpoint(model, optimizer, epoch, loss, filepath):
    """Save training checkpoint with metadata"""
    checkpoint = {
        'epoch': epoch,
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'loss': loss,
        'timestamp': datetime.now().isoformat(),
        'gpu_topology': os.environ.get('NCCL_TOPO_DUMP_FILE', 'unknown')
    }
    torch.save(checkpoint, filepath)
    
    # Sync to persistent storage
    os.system(f'gsutil cp {filepath} gs://your-training-bucket/checkpoints/')

def load_checkpoint(filepath, model, optimizer):
    """Load checkpoint and restore training state"""
    checkpoint = torch.load(filepath)
    model.load_state_dict(checkpoint['model_state_dict'])
    optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
    return checkpoint['epoch'], checkpoint['loss']
```

### Create Migration Job
```yaml
# migration-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: training-migration
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: migrate
        image: your-training-image:latest
        command: ["/bin/bash"]
        args:
          - -c
          - |
            # Save current state
            python save_checkpoint.py --output=/checkpoints/pre-migration-$(date +%s).pt
            
            # Verify TCPXO connectivity on new cluster
            python verify_gpu_topology.py
            
            # Resume training from checkpoint
            python resume_training.py --checkpoint=/checkpoints/latest.pt
        env:
        - name: NCCL_DEBUG
          value: "INFO"
        - name: CUDA_VISIBLE_DEVICES
          value: "0,1,2,3,4,5,6,7"
        resources:
          limits:
            nvidia.com/gpu: 8
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /checkpoints
      volumes:
      - name: checkpoint-storage
        persistentVolumeClaim:
          claimName: training-checkpoints
      nodeSelector:
        accelerator: nvidia-h100
```

## 5. Validation and Monitoring

### Pre-Migration Validation
```bash
#!/bin/bash
# validate-cluster.sh

echo "Validating new cluster setup..."

# Check GPU availability
kubectl get nodes -l accelerator=nvidia-h100 | wc -l

# Verify TCPXO daemon
kubectl get pods -n kube-system -l name=tcpxo-daemon | grep Running | wc -l

# Test GPU-to-GPU connectivity
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: nccl-test
spec:
  containers:
  - name: nccl-test
    image: nvcr.io/nvidia/pytorch:24.01-py3
    command: ["python", "-c", "import torch; print(f'GPUs available: {torch.cuda.device_count()}'); print('NCCL backend available:', torch.distributed.is_nccl_available())"]
    resources:
      limits:
        nvidia.com/gpu: 8
  nodeSelector:
    accelerator: nvidia-h100
EOF

# Wait and check results
kubectl wait --for=condition=completed pod/nccl-test --timeout=60s
kubectl logs nccl-test
```

## 6. Rollback Plan

### Automated Rollback
```yaml
# rollback-plan.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: rollback-config
data:
  rollback.sh: |
    #!/bin/bash
    set -e
    
    echo "Initiating rollback to original cluster..."
    
    # Save current checkpoint
    kubectl exec -it training-pod -- python save_checkpoint.py
    
    # Update kubeconfig to original cluster
    gcloud container clusters get-credentials original-training-cluster
    
    # Restore training from latest checkpoint
    kubectl apply -f original-training-manifest.yaml
    
    echo "Rollback completed"
```

## 7. Migration Execution Timeline

### Week 1: Preparation
- Create and validate new cluster
- Test GPU connectivity and TCPXO
- Implement checkpoint saving in current training

### Week 2: Migration Window
- Save final checkpoint
- Pause training (5-10 minutes)
- Switch to new cluster
- Resume training from checkpoint

### Week 3: Monitoring
- Monitor training performance
- Compare convergence rates
- Keep old cluster as backup for 48 hours

## Key Considerations

1. **TCPXO Compatibility**: Ensure the new GKE version supports your TCPXO configuration
2. **Checkpoint Frequency**: Increase checkpoint frequency before migration
3. **Network Topology**: Maintain the same GPU placement and network topology
4. **Resource Limits**: Ensure identical resource allocations
5. **Monitoring**: Set up alerts for training divergence post-migration

This approach minimizes training disruption while ensuring a safe upgrade path. The blue-green strategy is recommended for critical training runs, while the in-place upgrade can work for more flexible scenarios.