This is a challenging scenario that requires careful planning to avoid disrupting your multi-week training runs. Here's a comprehensive approach:

## Pre-Upgrade Assessment

**Check Compatibility First:**
```bash
# Check current cluster version and available upgrades
gcloud container clusters describe CLUSTER_NAME --zone=ZONE \
  --format="value(currentMasterVersion,currentNodeVersion)"

# Check available versions for A3 Mega nodes
gcloud container get-server-config --zone=ZONE \
  --format="value(validNodeVersions[])"
```

## Option 1: Blue-Green Cluster Migration (Recommended)

**Step 1: Create New GKE 1.32 Cluster**
```bash
# Create new cluster with identical configuration
gcloud container clusters create training-cluster-v132 \
  --zone=ZONE \
  --cluster-version=1.32.x \
  --machine-type=a3-megagpu-8g \
  --num-nodes=512 \
  --enable-gvnic \
  --enable-ip-alias \
  --network=NETWORK_NAME \
  --subnetwork=SUBNET_NAME \
  --placement-policy-type=COMPACT \
  --enable-autoscaling \
  --max-nodes=512 \
  --min-nodes=512
```

**Step 2: Configure GPU and Networking**
```yaml
# gpu-operator-values.yaml
operator:
  defaultRuntime: containerd
driver:
  enabled: true
  version: "535.129.03"  # Ensure H100 compatibility
toolkit:
  version: "1.14.3-ubuntu20.04"
```

```bash
# Install GPU operator
helm install gpu-operator nvidia/gpu-operator \
  --namespace gpu-operator-system \
  --create-namespace \
  -f gpu-operator-values.yaml
```

**Step 3: Verify GPUDirect-TCPXO**
```yaml
# test-gpudirect.yaml
apiVersion: v1
kind: Pod
metadata:
  name: gpudirect-test
spec:
  nodeSelector:
    cloud.google.com/gke-accelerator: nvidia-h100-80gb
  containers:
  - name: test
    image: nvcr.io/nvidia/pytorch:23.10-py3
    command: ["/bin/bash", "-c", "nvidia-smi topo -m && sleep 3600"]
    resources:
      limits:
        nvidia.com/gpu: 8
```

## Option 2: Rolling Node Pool Updates

**Step 1: Create New Node Pool**
```bash
# Add new node pool with 1.32
gcloud container node-pools create training-pool-v132 \
  --cluster=CLUSTER_NAME \
  --zone=ZONE \
  --machine-type=a3-megagpu-8g \
  --num-nodes=0 \
  --enable-autoscaling \
  --max-nodes=512 \
  --min-nodes=0 \
  --node-version=1.32.x \
  --placement-policy-type=COMPACT
```

**Step 2: Gradual Migration Strategy**
```yaml
# training-job-affinity.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: training-continue
spec:
  template:
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - key: cloud.google.com/gke-nodepool
                operator: In
                values: ["training-pool-v131"]  # Keep on old pool during migration
```

## Option 3: Checkpoint-Based Migration

**Step 1: Enhanced Checkpointing**
```python
# training-checkpoint.py
import torch
import os
from datetime import datetime

class MigrationCheckpointer:
    def __init__(self, checkpoint_dir="/gcs/checkpoints"):
        self.checkpoint_dir = checkpoint_dir
        self.migration_signal_file = "/tmp/migration_signal"
    
    def should_checkpoint_for_migration(self):
        return os.path.exists(self.migration_signal_file)
    
    def save_migration_checkpoint(self, model, optimizer, scheduler, epoch, step):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        checkpoint = {
            'model_state_dict': model.state_dict(),
            'optimizer_state_dict': optimizer.state_dict(),
            'scheduler_state_dict': scheduler.state_dict(),
            'epoch': epoch,
            'step': step,
            'migration_timestamp': timestamp,
            'gpu_topology': self.get_gpu_topology()
        }
        
        path = f"{self.checkpoint_dir}/migration_checkpoint_{timestamp}.pt"
        torch.save(checkpoint, path)
        return path
    
    def get_gpu_topology(self):
        # Capture current GPU interconnect state
        import subprocess
        result = subprocess.run(['nvidia-smi', 'topo', '-m'], 
                              capture_output=True, text=True)
        return result.stdout
```

## Critical Considerations for GPUDirect-TCPXO

**Verify Network Configuration:**
```bash
# Check TCPXO configuration
kubectl get nodes -o yaml | grep -A5 -B5 "gvnic\|tcpx"

# Verify GPU topology preservation
kubectl exec -it POD_NAME -- nvidia-smi topo -m
```

**Network Policy for Training:**
```yaml
# preserve-gpu-network.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: preserve-gpu-interconnect
spec:
  podSelector:
    matchLabels:
      app: training-job
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: training-job
    ports:
    - protocol: TCP
      port: 23000  # NCCL port range
      endPort: 23100
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: training-job
```

## Migration Execution Plan

**Timeline for Active Training Run:**

1. **Immediate (Day 0):**
   ```bash
   # Create new cluster in parallel
   # Test GPU interconnect functionality
   # Verify checkpoint compatibility
   ```

2. **Week 2 of Current Run:**
   ```bash
   # Signal training job to create migration checkpoint
   kubectl exec TRAINING_POD -- touch /tmp/migration_signal
   
   # Wait for checkpoint completion
   # Gracefully terminate current training
   ```

3. **Migration Window:**
   ```bash
   # Deploy to new cluster
   kubectl apply -f training-job-resume.yaml --cluster=new-cluster
   
   # Verify GPU topology matches
   # Resume from checkpoint
   ```

## Monitoring During Migration

```yaml
# migration-monitor.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: migration-monitor
data:
  monitor.sh: |
    #!/bin/bash
    while true; do
      echo "=== GPU Status ==="
      nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv
      
      echo "=== Network Interconnect ==="
      nvidia-smi topo -m | grep -E "GPU|NV"
      
      echo "=== Training Progress ==="
      tail -5 /training/logs/latest.log
      
      sleep 30
    done
```

## Recommendations

1. **Use Blue-Green Migration** if you can afford the additional compute costs
2. **Test thoroughly** on a smaller replica first
3. **Coordinate with Google Cloud Support** for A3 Mega-specific guidance
4. **Plan migration during natural checkpoint intervals** in your training schedule
5. **Have rollback procedures** ready

The key is ensuring GPUDirect-TCPXO configuration remains identical between clusters and that your training job can seamlessly resume from checkpoints without topology changes affecting performance.