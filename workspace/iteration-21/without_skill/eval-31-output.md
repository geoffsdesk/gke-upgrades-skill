For upgrading a large-scale LLM training cluster on GKE without disrupting active training runs, you'll need a carefully orchestrated approach. Here's a comprehensive strategy:

## 1. Pre-Upgrade Assessment & Preparation

```bash
# Check current cluster state
kubectl get nodes -o wide
kubectl describe nodes | grep -E "(Taints|GPUDirect|nvidia)"

# Verify GPUDirect-TCPXO status
kubectl get pods -n gpu-operator -o wide
kubectl logs -n gpu-operator -l app=nvidia-device-plugin
```

## 2. Implement Checkpointing Strategy

First, ensure your training job can handle checkpointing:

```yaml
# training-job.yaml - Add checkpoint configuration
apiVersion: batch/v1
kind: Job
metadata:
  name: llm-training
spec:
  template:
    spec:
      containers:
      - name: trainer
        env:
        - name: CHECKPOINT_INTERVAL
          value: "3600" # Checkpoint every hour
        - name: CHECKPOINT_PATH
          value: "/persistent-storage/checkpoints"
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /persistent-storage
      volumes:
      - name: checkpoint-storage
        persistentVolumeClaim:
          claimName: training-checkpoints
```

## 3. Rolling Upgrade Strategy

### Option A: Node Pool Rotation (Recommended for GPU workloads)

```bash
# 1. Create new node pool with GKE 1.32
gcloud container node-pools create gpu-pool-v132 \
  --cluster=llm-training-cluster \
  --machine-type=a3-megagpu-8g \
  --accelerator=type=nvidia-h100-mega-80gb,count=8,gpu-driver-version=latest \
  --num-nodes=64 \
  --zone=us-central1-a \
  --node-version=1.32.x \
  --enable-gvnic \
  --placement-type=COMPACT \
  --placement-policy=gpu-topology-block \
  --enable-autoscaling \
  --max-nodes=512 \
  --min-nodes=0

# 2. Cordon old nodes (but don't drain yet)
kubectl get nodes -l cloud.google.com/gke-nodepool=gpu-pool-v131 -o name | \
  xargs -I {} kubectl cordon {}
```

### Option B: In-Place Upgrade with Careful Orchestration

```bash
# Configure upgrade settings for minimal disruption
gcloud container clusters update llm-training-cluster \
  --enable-autoupgrade \
  --enable-autorepair=false \
  --maintenance-window-start="2024-01-15T02:00:00Z" \
  --maintenance-window-end="2024-01-15T06:00:00Z" \
  --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SU"
```

## 4. GPU-Aware Migration Script

```python
#!/usr/bin/env python3
import kubernetes
import time
import subprocess
import logging

class GPUClusterUpgrader:
    def __init__(self):
        kubernetes.config.load_incluster_config()
        self.v1 = kubernetes.client.CoreV1Api()
        
    def checkpoint_training_job(self, job_name, namespace="default"):
        """Trigger checkpoint before migration"""
        # Send SIGUSR1 to training processes to trigger checkpoint
        pods = self.v1.list_namespaced_pod(
            namespace=namespace,
            label_selector=f"job-name={job_name}"
        )
        
        for pod in pods.items:
            logging.info(f"Triggering checkpoint for pod {pod.metadata.name}")
            # Execute checkpoint command
            subprocess.run([
                "kubectl", "exec", pod.metadata.name, 
                "--", "/bin/bash", "-c", 
                "kill -USR1 $(pgrep -f 'python.*train')"
            ])
        
        # Wait for checkpoint completion
        time.sleep(300)  # Adjust based on checkpoint time
    
    def migrate_gpu_workload(self, old_node, new_node):
        """Migrate GPU workload maintaining topology"""
        # Get pods on old node
        pods = self.v1.list_pod_for_all_namespaces(
            field_selector=f"spec.nodeName={old_node}"
        )
        
        gpu_pods = [pod for pod in pods.items 
                   if any(container.resources.limits.get('nvidia.com/gpu') 
                         for container in pod.spec.containers)]
        
        for pod in gpu_pods:
            if 'training' in pod.metadata.name:
                # Checkpoint before migration
                self.checkpoint_training_job(
                    pod.metadata.labels.get('job-name')
                )
            
            # Update node affinity to target new node
            self.update_pod_node_affinity(pod, new_node)
    
    def verify_gpu_connectivity(self, node_name):
        """Verify GPUDirect-TCPXO after migration"""
        test_pod = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": f"gpu-test-{node_name}"},
            "spec": {
                "nodeName": node_name,
                "containers": [{
                    "name": "gpu-test",
                    "image": "nvcr.io/nvidia/pytorch:23.10-py3",
                    "command": ["/bin/bash", "-c", 
                              "nvidia-smi topo -m && sleep 300"],
                    "resources": {
                        "limits": {"nvidia.com/gpu": "1"}
                    }
                }]
            }
        }
        
        self.v1.create_namespaced_pod(namespace="default", body=test_pod)
        # Monitor and validate GPU topology
```

## 5. Upgrade Execution Plan

```bash
#!/bin/bash
set -e

CLUSTER_NAME="llm-training-cluster"
OLD_POOL="gpu-pool-v131"
NEW_POOL="gpu-pool-v132"

# Phase 1: Create checkpoint
echo "Phase 1: Creating checkpoint..."
kubectl exec -it $(kubectl get pods -l app=llm-training -o jsonpath='{.items[0].metadata.name}') \
  -- python -c "import torch; torch.save(model.state_dict(), '/checkpoints/pre_upgrade.pt')"

# Phase 2: Migrate in batches of 8 nodes (1 A3 Mega unit)
for batch in $(seq 0 8 512); do
  echo "Phase 2: Migrating batch starting at node $batch"
  
  # Select 8 nodes for migration
  nodes_to_migrate=$(kubectl get nodes -l cloud.google.com/gke-nodepool=$OLD_POOL \
    -o jsonpath='{.items[*].metadata.name}' | tr ' ' '\n' | head -8)
  
  # Scale up new pool
  gcloud container clusters resize $CLUSTER_NAME \
    --node-pool=$NEW_POOL \
    --num-nodes=$((batch + 8)) \
    --zone=us-central1-a
  
  # Wait for new nodes to be ready
  kubectl wait --for=condition=Ready nodes \
    -l cloud.google.com/gke-nodepool=$NEW_POOL \
    --timeout=600s
  
  # Migrate workloads
  for node in $nodes_to_migrate; do
    kubectl drain $node --ignore-daemonsets \
      --delete-emptydir-data --force --grace-period=300
  done
  
  # Verify GPU connectivity on new nodes
  python3 gpu_cluster_upgrader.py --verify-batch $batch
  
  # Remove old nodes
  echo $nodes_to_migrate | xargs kubectl delete node
  
  echo "Batch $batch migration completed successfully"
done

# Phase 3: Cleanup
gcloud container node-pools delete $OLD_POOL \
  --cluster=$CLUSTER_NAME --zone=us-central1-a --quiet
```

## 6. GPUDirect-TCPXO Validation

```yaml
# gpu-connectivity-test.yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: gpu-connectivity-test
spec:
  selector:
    matchLabels:
      name: gpu-connectivity-test
  template:
    metadata:
      labels:
        name: gpu-connectivity-test
    spec:
      nodeSelector:
        cloud.google.com/gke-accelerator: nvidia-h100-mega-80gb
      containers:
      - name: test
        image: nvcr.io/nvidia/pytorch:23.10-py3
        command:
        - /bin/bash
        - -c
        - |
          # Test GPU topology
          nvidia-smi topo -m
          # Test NCCL with GPUDirect
          python -c "
          import torch
          import torch.distributed as dist
          if torch.cuda.is_available():
              print(f'GPUs available: {torch.cuda.device_count()}')
              # Test inter-GPU communication
              for i in range(torch.cuda.device_count()):
                  print(f'GPU {i}: {torch.cuda.get_device_properties(i)}')
          "
        resources:
          limits:
            nvidia.com/gpu: 8
        securityContext:
          privileged: true
```

## 7. Monitoring and Rollback Plan

```bash
# Monitor training metrics during upgrade
kubectl logs -f deployment/training-monitor --tail=100

# Rollback plan if issues occur
gcloud container clusters update $CLUSTER_NAME \
  --node-version=1.31.x  # Rollback node version

# Emergency checkpoint restoration
kubectl exec -it $(kubectl get pods -l app=llm-training -o jsonpath='{.items[0].metadata.name}') \
  -- python -c "
import torch
model.load_state_dict(torch.load('/checkpoints/pre_upgrade.pt'))
print('Model restored from checkpoint')
"
```

## Key Considerations:

1. **Batch Size**: Migrate 64 nodes (8 A3 Mega instances) at a time to maintain training parallelism
2. **Checkpoint Frequency**: Increase checkpoint frequency during upgrade window
3. **Network Topology**: Ensure new nodes maintain the same GPUDirect-TCPXO configuration
4. **Monitoring**: Monitor training loss/metrics closely for any degradation
5. **Timing**: Schedule during lowest priority training phases if possible

This approach minimizes downtime while preserving your GPU interconnect topology and training state.