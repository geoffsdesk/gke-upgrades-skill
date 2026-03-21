This is a critical operation that requires careful planning. Here's a comprehensive strategy to upgrade your GKE cluster without disrupting your training workload:

## Pre-Upgrade Assessment

First, verify your current setup and upgrade compatibility:

```bash
# Check current cluster version and node pool details
gcloud container clusters describe YOUR_CLUSTER_NAME \
  --zone=YOUR_ZONE \
  --format="yaml(currentMasterVersion,nodeConfig.machineType)"

# Verify GPUDirect-TCPXO status
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.allocatable.nvidia\.com/gpu}{"\n"}{end}'
```

## Strategy 1: Blue-Green Node Pool Migration (Recommended)

This approach creates a new node pool alongside your existing one:

### Step 1: Create New Node Pool with GKE 1.32

```bash
# Create new node pool with 1.32
gcloud container node-pools create training-pool-v132 \
  --cluster=YOUR_CLUSTER_NAME \
  --zone=YOUR_ZONE \
  --machine-type=a3-megagpu-8g \
  --accelerator=type=nvidia-h100-mega-80gb,count=8,gpu-driver-version=latest \
  --num-nodes=512 \
  --node-version=1.32.x-gke.xxxx \
  --enable-autoscaling \
  --max-nodes=512 \
  --min-nodes=512 \
  --disk-type=pd-ssd \
  --disk-size=200GB \
  --enable-gvnic \
  --placement-type=COMPACT \
  --network-performance-config=total-egress-bandwidth-tier=TIER_1
```

### Step 2: Configure GPUDirect-TCPXO on New Nodes

Create a DaemonSet to ensure GPUDirect-TCPXO is properly configured:

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: gpu-tcpxo-setup
  namespace: kube-system
spec:
  selector:
    matchLabels:
      name: gpu-tcpxo-setup
  template:
    metadata:
      labels:
        name: gpu-tcpxo-setup
    spec:
      nodeSelector:
        cloud.google.com/gke-nodepool: training-pool-v132
      hostNetwork: true
      hostPID: true
      containers:
      - name: tcpxo-setup
        image: gcr.io/gke-release/nvidia-partition-gpu:v1.0.0
        securityContext:
          privileged: true
        volumeMounts:
        - name: dev
          mountPath: /dev
        - name: proc
          mountPath: /host/proc
        env:
        - name: NVIDIA_MIG_CONFIG_DEVICES
          value: "all"
      volumes:
      - name: dev
        hostPath:
          path: /dev
      - name: proc
        hostPath:
          path: /proc
```

## Strategy 2: Rolling Node Pool Upgrade (If Training Can Checkpoint)

If your training framework supports checkpointing and resuming:

### Step 1: Prepare Checkpoint Strategy

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: training-checkpoint-config
data:
  checkpoint-interval: "3600"  # Checkpoint every hour
  checkpoint-path: "gs://YOUR-BUCKET/checkpoints/"
  auto-resume: "true"
```

### Step 2: Controlled Node Pool Upgrade

```bash
# Upgrade node pool with controlled surge settings
gcloud container node-pools upgrade training-pool \
  --cluster=YOUR_CLUSTER_NAME \
  --zone=YOUR_ZONE \
  --node-version=1.32.x-gke.xxxx \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=0
```

## Strategy 3: Control Plane First, Then Selective Node Migration

### Step 1: Upgrade Control Plane Only

```bash
# Upgrade master/control plane first
gcloud container clusters upgrade YOUR_CLUSTER_NAME \
  --zone=YOUR_ZONE \
  --master \
  --cluster-version=1.32.x-gke.xxxx
```

### Step 2: Cordon Critical Training Nodes

```bash
# Identify and cordon nodes running your training workload
kubectl get pods -o wide | grep training-job
kubectl cordon NODE_NAME_1 NODE_NAME_2  # etc.
```

## Critical Considerations

### GPUDirect-TCPXO Validation Script

Create this validation script to run after any node changes:

```bash
#!/bin/bash
# validate-gpu-interconnect.sh

echo "Validating GPUDirect-TCPXO setup..."

# Check NCCL topology
kubectl exec -it YOUR_TRAINING_POD -- python3 -c "
import torch
import torch.distributed as dist
if torch.cuda.is_available():
    print(f'GPUs available: {torch.cuda.device_count()}')
    for i in range(torch.cuda.device_count()):
        print(f'GPU {i}: {torch.cuda.get_device_name(i)}')
"

# Validate inter-node bandwidth
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: nccl-test
spec:
  template:
    spec:
      containers:
      - name: nccl-test
        image: nvcr.io/nvidia/pytorch:23.10-py3
        command: ["/opt/hpcx/nccl_tests/build/all_reduce_perf"]
        args: ["-b", "1G", "-e", "8G", "-f", "2", "-g", "8"]
        resources:
          limits:
            nvidia.com/gpu: 8
      restartPolicy: Never
EOF
```

### Monitoring During Upgrade

Set up comprehensive monitoring:

```yaml
apiVersion: v1
kind: ServiceMonitor
metadata:
  name: training-health-monitor
spec:
  selector:
    matchLabels:
      app: training-workload
  endpoints:
  - port: metrics
    interval: 30s
    path: /metrics
```

## Recommended Upgrade Sequence

1. **Week Before**: Test the upgrade on a smaller staging cluster
2. **Day Before**: Create fresh checkpoint and validate restore process
3. **Upgrade Day**:
   - Create new node pool (Strategy 1)
   - Validate GPUDirect-TCPXO on new nodes
   - Gradually migrate non-critical workloads
   - Schedule training migration during natural checkpoint window
   - Monitor interconnect performance continuously

### Emergency Rollback Plan

```bash
# If issues arise, quickly rollback
gcloud container node-pools delete training-pool-v132 \
  --cluster=YOUR_CLUSTER_NAME \
  --zone=YOUR_ZONE

# Restore from checkpoint
kubectl apply -f training-job-restore.yaml
```

## Key Success Metrics

Monitor these during upgrade:
- GPU utilization remains >95%
- Inter-node communication latency <10ms
- Training loss continues expected trajectory
- No NCCL timeout errors
- Memory usage patterns remain stable

The blue-green node pool approach (Strategy 1) is strongly recommended for your critical 2-3 week training runs, as it provides the safest path with immediate rollback capability.