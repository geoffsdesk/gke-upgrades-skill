This is a critical operation that requires careful planning. Here's a comprehensive approach to upgrade your GKE cluster without interrupting your training runs:

## Pre-Upgrade Assessment

First, verify your current setup and upgrade compatibility:

```bash
# Check current cluster version and node pool details
kubectl get nodes -o wide
gcloud container clusters describe CLUSTER_NAME --zone=ZONE

# Verify GPUDirect-TCPXO status
kubectl get nodes -o jsonpath='{.items[*].status.allocatable}' | grep nvidia.com/gpu
```

## Strategy 1: Blue-Green Node Pool Migration (Recommended)

### Step 1: Create New Node Pool with GKE 1.32

```yaml
# new-nodepool-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: gpu-nodepool-config
data:
  machine-type: "a3-megagpu-8g"
  accelerator: "nvidia-h100-mega-80gb"
  count: "8"
---
```

```bash
# Create new node pool with 1.32
gcloud container node-pools create training-pool-v132 \
  --cluster=CLUSTER_NAME \
  --zone=ZONE \
  --machine-type=a3-megagpu-8g \
  --accelerator=type=nvidia-h100-mega-80gb,count=8,gpu-driver-version=latest \
  --num-nodes=64 \
  --node-version=1.32.x-gke.xxx \
  --enable-gvnic \
  --enable-ip-alias \
  --network-performance-config=total-egress-bandwidth-tier=TIER_1 \
  --placement-type=COMPACT \
  --reservation-affinity=none \
  --disk-type=pd-ssd \
  --disk-size=200GB \
  --enable-autoscaling \
  --max-nodes=64 \
  --min-nodes=0 \
  --node-taints=nvidia.com/gpu=present:NoSchedule \
  --node-labels=nodepool-version=v132,gpu-type=h100
```

### Step 2: Prepare Training Job for Migration

```yaml
# training-job-updated.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: llm-training-continued
spec:
  template:
    spec:
      nodeSelector:
        nodepool-version: v132
      tolerations:
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule
      containers:
      - name: training
        image: your-training-image
        resources:
          limits:
            nvidia.com/gpu: 8
        env:
        - name: NCCL_DEBUG
          value: "INFO"
        - name: NCCL_IB_DISABLE
          value: "1"
        - name: NCCL_SOCKET_IFNAME
          value: "eth0"
        # Checkpoint recovery configuration
        - name: CHECKPOINT_PATH
          value: "/checkpoints"
        - name: RESUME_FROM_CHECKPOINT
          value: "true"
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /checkpoints
```

### Step 3: Checkpoint and Migrate

```bash
# Create checkpoint save job
kubectl create job checkpoint-save --from=cronjob/training-checkpoint

# Wait for checkpoint completion
kubectl wait --for=condition=complete job/checkpoint-save --timeout=1800s

# Scale down old training job gracefully
kubectl scale deployment llm-training --replicas=0

# Apply new training configuration
kubectl apply -f training-job-updated.yaml
```

## Strategy 2: Rolling Update with Checkpoint Orchestration

### Step 1: Enhanced Checkpointing Setup

```yaml
# checkpoint-orchestrator.yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: checkpoint-orchestrator
spec:
  selector:
    matchLabels:
      app: checkpoint-orchestrator
  template:
    spec:
      tolerations:
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule
      containers:
      - name: orchestrator
        image: google/cloud-sdk:alpine
        command:
        - /bin/sh
        - -c
        - |
          while true; do
            if [ -f /tmp/upgrade-signal ]; then
              echo "Upgrade signal detected, triggering checkpoint..."
              kubectl exec deployment/llm-training -- python save_checkpoint.py
              echo "Checkpoint saved, node ready for upgrade"
              rm /tmp/upgrade-signal
            fi
            sleep 30
          done
        volumeMounts:
        - name: upgrade-signals
          mountPath: /tmp
```

### Step 2: Controlled Rolling Update

```bash
# Enable maintenance mode with checkpointing
kubectl patch deployment llm-training -p '{"spec":{"template":{"spec":{"containers":[{"name":"training","env":[{"name":"MAINTENANCE_MODE","value":"checkpoint"}]}]}}}}'

# Perform rolling upgrade of node pool
gcloud container node-pools update training-pool \
  --cluster=CLUSTER_NAME \
  --zone=ZONE \
  --node-version=1.32.x-gke.xxx \
  --max-surge-upgrade=2 \
  --max-unavailable-upgrade=1

# Monitor upgrade progress
watch gcloud container operations list
```

## Critical Configurations for GPU Interconnect Preservation

### GPUDirect-TCPXO Configuration

```yaml
# gpu-interconnect-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: gpu-interconnect-config
data:
  setup.sh: |
    #!/bin/bash
    # Preserve GPUDirect-TCPXO configuration
    modprobe nvidia
    nvidia-smi -pm 1
    
    # Configure NCCL for A3 Mega
    export NCCL_CROSS_NIC=1
    export NCCL_ALGO=RING
    export NCCL_PROTO=Simple
    export NCCL_MIN_NCHANNELS=32
    export NCCL_BUFFSIZE=8388608
    
    # Verify GPU interconnect
    nvidia-smi topo -m
---
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: gpu-interconnect-setup
spec:
  selector:
    matchLabels:
      app: gpu-interconnect-setup
  template:
    spec:
      hostPID: true
      hostNetwork: true
      tolerations:
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule
      containers:
      - name: setup
        image: nvidia/cuda:12.2-devel-ubuntu20.04
        securityContext:
          privileged: true
        command: ["/bin/bash", "/scripts/setup.sh"]
```

## Monitoring and Validation

### Pre-Upgrade Validation

```bash
# Create validation script
cat > validate-upgrade.sh << 'EOF'
#!/bin/bash

echo "=== Pre-Upgrade Validation ==="

# Check GPU connectivity
kubectl exec -it deployment/llm-training -- nvidia-smi topo -m

# Verify NCCL performance
kubectl exec -it deployment/llm-training -- /opt/nccl-tests/build/all_reduce_perf -b 1G -e 1G -g 8

# Validate checkpoint integrity
kubectl exec -it deployment/llm-training -- python validate_checkpoint.py

echo "=== Validation Complete ==="
EOF

chmod +x validate-upgrade.sh
./validate-upgrade.sh
```

### Post-Upgrade Verification

```bash
# Verify new nodes are healthy
kubectl get nodes -l nodepool-version=v132 -o wide

# Check GPU driver compatibility
kubectl exec -it deployment/llm-training -- nvidia-smi

# Validate training resumption
kubectl logs -f deployment/llm-training --tail=100
```

## Rollback Plan

```bash
# Emergency rollback procedure
cat > rollback-plan.sh << 'EOF'
#!/bin/bash

echo "=== EMERGENCY ROLLBACK ==="

# Scale down new deployment
kubectl scale deployment llm-training-v132 --replicas=0

# Restore from checkpoint on old nodes
kubectl scale deployment llm-training --replicas=1

# Verify rollback
kubectl wait --for=condition=available deployment/llm-training --timeout=600s

echo "=== ROLLBACK COMPLETE ==="
EOF
```

## Recommendations

1. **Test First**: Run this procedure on a smaller test cluster with similar configuration
2. **Checkpoint Strategy**: Ensure your training code supports frequent checkpointing and recovery
3. **Network Validation**: Verify GPUDirect-TCPXO performance before and after upgrade
4. **Gradual Migration**: Consider migrating a subset of nodes first to validate the process
5. **Backup Strategy**: Ensure checkpoint data is stored in persistent storage (GCS/Filestore)

The blue-green migration approach is safest for your 2-3 week training runs, as it provides the ability to maintain the existing workload while preparing the new environment.