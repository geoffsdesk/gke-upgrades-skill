This is a critical operation that requires careful planning. Here's a comprehensive strategy to upgrade your GKE cluster without disrupting your training runs:

## Pre-Upgrade Assessment

First, verify your current setup and upgrade compatibility:

```bash
# Check current cluster version and node pool details
kubectl get nodes -o wide
gcloud container clusters describe YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE --format="value(currentMasterVersion,currentNodeVersion)"

# Verify GPUDirect-TCPXO status
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.allocatable.google\.com/gpudirecttcpxo}{"\n"}{end}'
```

## Strategy 1: Blue-Green Node Pool Migration (Recommended)

### Step 1: Create New Node Pool with GKE 1.32

```bash
# Create new node pool with identical A3 Mega configuration
gcloud container node-pools create "a3-mega-pool-132" \
  --cluster=YOUR_CLUSTER_NAME \
  --zone=YOUR_ZONE \
  --machine-type=a3-megagpu-8g \
  --accelerator=type=nvidia-h100-mega-80gb,count=8,gpu-driver-version=LATEST \
  --node-version=1.32.x-gke.xxxx \
  --num-nodes=64 \  # Start with subset for testing
  --enable-gvnic \
  --enable-ip-alias \
  --network-performance-config=total-egress-bandwidth-tier=TIER_1 \
  --placement-policy-type=COMPACT \
  --node-taints=nvidia.com/gpu=present:NoSchedule \
  --node-labels=nodepool=a3-mega-132,gpu-type=h100 \
  --disk-size=2000 \
  --disk-type=pd-ssd
```

### Step 2: Validate New Nodes

```bash
# Wait for nodes to be ready
kubectl wait --for=condition=Ready nodes -l nodepool=a3-mega-132 --timeout=600s

# Verify GPU and TCPXO functionality on new nodes
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: gpu-test-132
spec:
  restartPolicy: Never
  nodeSelector:
    nodepool: a3-mega-132
  containers:
  - name: gpu-test
    image: nvcr.io/nvidia/cuda:12.3-devel-ubuntu22.04
    command: ["/bin/bash", "-c", "nvidia-smi && nvidia-smi topo -m"]
    resources:
      limits:
        nvidia.com/gpu: 1
        google.com/gpudirecttcpxo: 1
EOF

kubectl logs gpu-test-132
```

### Step 3: Test Multi-Node Communication

Create a small-scale test to verify TCPXO connectivity:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: tcpxo-test-132
spec:
  parallelism: 4
  completions: 4
  template:
    spec:
      nodeSelector:
        nodepool: a3-mega-132
      containers:
      - name: nccl-test
        image: nvcr.io/nvidia/pytorch:23.12-py3
        command: ["/bin/bash", "-c"]
        args:
        - |
          apt-get update && apt-get install -y openssh-server
          # Add NCCL test commands here
          python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}'); print(f'GPU count: {torch.cuda.device_count()}')"
        resources:
          limits:
            nvidia.com/gpu: 8
            google.com/gpudirecttcpxo: 8
      restartPolicy: Never
```

## Strategy 2: Rolling Upgrade with Checkpointing

If you must upgrade the existing cluster:

### Step 1: Implement Robust Checkpointing

Ensure your training job can save/restore state frequently:

```python
# Add to your training script
import signal
import sys

class GracefulKiller:
    def __init__(self):
        self.kill_now = False
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
    
    def _handle_signal(self, signum, frame):
        logging.info(f"Received signal {signum}, preparing for graceful shutdown...")
        self.kill_now = True

killer = GracefulKiller()

# In your training loop
if killer.kill_now or step % checkpoint_interval == 0:
    save_checkpoint(model, optimizer, step, epoch)
    if killer.kill_now:
        sys.exit(0)
```

### Step 2: Configure Pod Disruption Budget

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
spec:
  minAvailable: 80%  # Allow only 20% of nodes to be disrupted
  selector:
    matchLabels:
      app: llm-training
```

### Step 3: Set Graceful Termination

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: llm-training
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 3600  # 1 hour for checkpoint
      containers:
      - name: training
        # ... your container config
        lifecycle:
          preStop:
            exec:
              command: ["/bin/bash", "-c", "touch /tmp/shutdown && sleep 30"]
```

## Upgrade Execution Plan

### Phase 1: Control Plane Upgrade (Non-disruptive)

```bash
# Upgrade master first - this doesn't affect running workloads
gcloud container clusters upgrade YOUR_CLUSTER_NAME \
  --master \
  --cluster-version=1.32.x-gke.xxxx \
  --zone=YOUR_ZONE
```

### Phase 2: Node Pool Migration

```bash
# Gradually scale up new pool and down old pool
# Do this in small batches to maintain training capacity

# Scale new pool up
gcloud container node-pools resize a3-mega-pool-132 \
  --cluster=YOUR_CLUSTER_NAME \
  --zone=YOUR_ZONE \
  --num-nodes=128

# Cordon old nodes (prevent new scheduling)
kubectl get nodes -l nodepool=old-pool-name -o name | \
  xargs kubectl cordon

# Drain nodes in small batches during natural checkpoint intervals
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data \
  --grace-period=3600 --timeout=7200s
```

## Monitoring and Validation

### Monitor Training Continuity

```bash
# Watch for training job health
kubectl get pods -l app=llm-training -w

# Monitor GPU utilization
kubectl top nodes --use-protocol-buffers

# Check TCPXO connectivity
kubectl exec -it training-pod-0 -- nvidia-smi nvlink -s
```

### Rollback Plan

Keep the old node pool available for immediate rollback:

```bash
# If issues arise, quickly scale back old pool
gcloud container node-pools resize old-a3-mega-pool \
  --cluster=YOUR_CLUSTER_NAME \
  --zone=YOUR_ZONE \
  --num-nodes=64

# Reschedule pods back to old nodes
kubectl uncordon nodes -l nodepool=old-pool-name
```

## Best Practices

1. **Timing**: Perform upgrades during natural checkpoint intervals
2. **Batch Size**: Upgrade no more than 10-20% of nodes at once
3. **Monitoring**: Set up alerts for training loss spikes or communication failures
4. **Testing**: Always test the new configuration with a smaller training job first
5. **Communication**: Coordinate with your ML team on optimal timing

The blue-green approach is strongly recommended for your use case, as it allows you to validate the new environment completely before migrating your critical training workload.