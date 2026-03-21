This is a challenging scenario that requires careful planning. Here's a comprehensive approach to upgrade your GKE cluster without disrupting your training run:

## Option 1: Blue-Green Cluster Strategy (Recommended)

### 1. Create a New GKE 1.32 Cluster
```bash
# Create new cluster with identical configuration
gcloud container clusters create training-cluster-v132 \
  --zone=us-central1-a \
  --machine-type=a3-megagpu-8g \
  --num-nodes=64 \
  --node-locations=us-central1-a,us-central1-b,us-central1-c \
  --enable-ip-alias \
  --network=training-network \
  --subnetwork=training-subnet \
  --cluster-version=1.32 \
  --enable-autoscaling \
  --max-nodes=64 \
  --min-nodes=0 \
  --enable-autorepair \
  --enable-autoupgrade=false \
  --accelerator=type=nvidia-h100-80gb,count=8,gpu-driver-version=latest \
  --enable-gvnic \
  --placement-type=COMPACT \
  --placement-policy=training-placement-policy
```

### 2. Preserve Training State
```bash
# Create checkpoint before migration
kubectl exec -n training <training-pod> -- python save_checkpoint.py \
  --checkpoint-path=/shared-storage/checkpoints/migration-checkpoint-$(date +%s)
```

### 3. Configure New Cluster
```yaml
# Apply GPUDirect-TCPXO configuration
apiVersion: v1
kind: ConfigMap
metadata:
  name: tcpxo-config
  namespace: kube-system
data:
  enable-tcpxo: "true"
  tcpxo-net-device: "gve0"
---
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: nvidia-tcpxo-installer
  namespace: kube-system
spec:
  selector:
    matchLabels:
      name: nvidia-tcpxo-installer
  template:
    metadata:
      labels:
        name: nvidia-tcpxo-installer
    spec:
      hostNetwork: true
      containers:
      - name: tcpxo-installer
        image: gcr.io/gke-release/nvidia-tcpxo:latest
        securityContext:
          privileged: true
        volumeMounts:
        - name: dev
          mountPath: /dev
        - name: nvidia-install-dir-host
          mountPath: /usr/local/nvidia
      volumes:
      - name: dev
        hostPath:
          path: /dev
      - name: nvidia-install-dir-host
        hostPath:
          path: /home/kubernetes/bin/nvidia
```

## Option 2: Rolling Node Pool Replacement

### 1. Create New Node Pool with 1.32
```bash
# Create new node pool
gcloud container node-pools create training-pool-v132 \
  --cluster=training-cluster \
  --zone=us-central1-a \
  --machine-type=a3-megagpu-8g \
  --num-nodes=64 \
  --node-version=1.32 \
  --accelerator=type=nvidia-h100-80gb,count=8 \
  --enable-autoscaling \
  --max-nodes=64 \
  --min-nodes=0 \
  --placement-type=COMPACT \
  --disk-size=1000 \
  --disk-type=pd-ssd
```

### 2. Gradual Migration Script
```python
#!/usr/bin/env python3
import subprocess
import time
import json

def get_training_pods():
    """Get list of training pods and their nodes"""
    result = subprocess.run([
        'kubectl', 'get', 'pods', '-n', 'training', 
        '-o', 'json'
    ], capture_output=True, text=True)
    return json.loads(result.stdout)

def cordon_and_drain_node(node_name):
    """Safely cordon and drain a node"""
    # Cordon node
    subprocess.run(['kubectl', 'cordon', node_name])
    
    # Wait for checkpoint save
    time.sleep(300)  # 5 minutes for checkpoint
    
    # Drain node
    subprocess.run([
        'kubectl', 'drain', node_name, 
        '--ignore-daemonsets', 
        '--delete-emptydir-data',
        '--grace-period=300'
    ])

def migrate_training_workload():
    """Migrate training workload with checkpointing"""
    
    # Save checkpoint
    subprocess.run([
        'kubectl', 'exec', '-n', 'training', 'training-coordinator-0', 
        '--', 'python', 'save_checkpoint.py'
    ])
    
    # Scale down training temporarily
    subprocess.run([
        'kubectl', 'scale', 'statefulset', 'training-workers', 
        '--replicas=0', '-n', 'training'
    ])
    
    # Wait for pods to terminate gracefully
    time.sleep(600)  # 10 minutes
    
    # Apply node affinity for new nodes
    subprocess.run([
        'kubectl', 'patch', 'statefulset', 'training-workers', 
        '-n', 'training', '--patch-file', 'node-affinity-patch.yaml'
    ])
    
    # Scale back up
    subprocess.run([
        'kubectl', 'scale', 'statefulset', 'training-workers', 
        '--replicas=64', '-n', 'training'
    ])

if __name__ == "__main__":
    migrate_training_workload()
```

## Option 3: In-Place Upgrade with Maintenance Window

### 1. Enhanced Checkpointing Strategy
```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: training-checkpoint
  namespace: training
spec:
  schedule: "0 */2 * * *"  # Every 2 hours
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: checkpoint-saver
            image: your-training-image
            command:
            - python
            - checkpoint_manager.py
            env:
            - name: CHECKPOINT_PATH
              value: "/shared-storage/checkpoints"
            - name: RETENTION_HOURS
              value: "72"
            volumeMounts:
            - name: shared-storage
              mountPath: /shared-storage
```

### 2. Upgrade Script with Validation
```bash
#!/bin/bash

# Pre-upgrade validation
validate_gpu_topology() {
    kubectl get nodes -l accelerator=nvidia-h100-80gb -o custom-columns="NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu"
    
    # Validate TCPXO connectivity
    kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: tcpxo-test
spec:
  containers:
  - name: test
    image: nvcr.io/nvidia/pytorch:23.12-py3
    command: ["nvidia-smi", "topo", "-m"]
    resources:
      limits:
        nvidia.com/gpu: 8
EOF
}

# Perform upgrade
upgrade_cluster() {
    # Save current state
    kubectl get all -n training -o yaml > training-backup-$(date +%s).yaml
    
    # Trigger final checkpoint
    kubectl exec -n training training-coordinator-0 -- python save_checkpoint.py --final=true
    
    # Scale down training
    kubectl scale statefulset training-workers --replicas=0 -n training
    
    # Wait for graceful shutdown
    sleep 600
    
    # Upgrade control plane
    gcloud container clusters upgrade training-cluster \
      --master \
      --cluster-version=1.32 \
      --zone=us-central1-a
    
    # Upgrade nodes
    gcloud container clusters upgrade training-cluster \
      --zone=us-central1-a \
      --cluster-version=1.32
}

# Post-upgrade validation
post_upgrade_validation() {
    # Verify GPU driver compatibility
    kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: gpu-validation
spec:
  containers:
  - name: test
    image: nvcr.io/nvidia/cuda:12.3-runtime-ubuntu22.04
    command: ["nvidia-smi"]
    resources:
      limits:
        nvidia.com/gpu: 1
EOF
    
    # Test TCPXO functionality
    kubectl exec gpu-validation -- nvidia-smi topo -m
}

# Main execution
validate_gpu_topology
upgrade_cluster
post_upgrade_validation
```

## Critical Considerations

### 1. GPUDirect-TCPXO Preservation
```yaml
# Ensure TCPXO settings persist
apiVersion: v1
kind: ConfigMap
metadata:
  name: gke-node-startup-script
  namespace: kube-system
data:
  startup-script: |
    #!/bin/bash
    # Configure TCPXO after node startup
    echo 'net.core.rmem_max = 134217728' >> /etc/sysctl.conf
    echo 'net.core.wmem_max = 134217728' >> /etc/sysctl.conf
    sysctl -p
    
    # Verify GPU topology
    nvidia-smi topo -m
```

### 2. Training State Management
```python
# Enhanced checkpoint manager
class UpgradeCheckpointManager:
    def __init__(self, checkpoint_dir):
        self.checkpoint_dir = checkpoint_dir
        
    def create_migration_checkpoint(self):
        """Create comprehensive checkpoint for cluster migration"""
        checkpoint = {
            'model_state': self.model.state_dict(),
            'optimizer_state': self.optimizer.state_dict(),
            'scheduler_state': self.scheduler.state_dict(),
            'epoch': self.current_epoch,
            'global_step': self.global_step,
            'random_states': {
                'torch': torch.get_rng_state(),
                'numpy': np.random.get_state(),
                'python': random.getstate()
            },
            'distributed_state': {
                'rank': dist.get_rank(),
                'world_size': dist.get_world_size()
            },
            'gpu_topology': self.get_gpu_topology(),
            'tcpxo_config': self.get_tcpxo_config()
        }
        
        torch.save(checkpoint, f'{self.checkpoint_dir}/migration_checkpoint.pt')
```

## Recommended Approach

For your critical 2-3 week training runs, I recommend **Option 1 (Blue-Green)** because:

1. **Zero downtime risk** for active training
2. **Full validation** before switching
3. **Easy rollback** if issues occur
4. **Preserved GPU interconnect** topology

The key is ensuring your shared storage (likely Filestore or persistent disks) is accessible from both clusters, and that your checkpoint/resume logic is robust enough to handle the transition.

Would you like me to elaborate on any specific aspect of this upgrade strategy?