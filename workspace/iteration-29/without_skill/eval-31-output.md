This is a critical operation that requires careful planning. Here's a comprehensive strategy to upgrade your GKE cluster without disrupting your training workload:

## Pre-Upgrade Assessment

First, verify your current setup:

```bash
# Check current cluster version and node pool details
kubectl get nodes -o wide
gcloud container clusters describe your-cluster-name --zone=your-zone

# Verify GPUDirect-TCPXO status
kubectl get nodes -o jsonpath='{.items[*].metadata.labels}' | grep -i tcpx
```

## Strategy: Blue-Green Cluster Migration

Given the scale and criticality, I recommend a **blue-green cluster approach** rather than in-place upgrades:

### Phase 1: Prepare New Cluster (1-2 days)

```yaml
# new-cluster-config.yaml
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerCluster
metadata:
  name: training-cluster-132
spec:
  location: your-zone
  initialNodeCount: 1
  minMasterVersion: "1.32"
  nodeVersion: "1.32"
  network: projects/your-project/global/networks/your-vpc
  subnetwork: projects/your-project/regions/your-region/subnetworks/your-subnet
  
  # Critical: Maintain same network topology for TCPX
  ipAllocationPolicy:
    clusterSecondaryRangeName: "pods"
    servicesSecondaryRangeName: "services"
    
  # Enable required features
  addonsConfig:
    gceEphemeralIpConfigs:
      enabled: true
```

### Phase 2: Create A3 Mega Node Pool

```bash
# Create the new A3 Mega node pool with TCPX support
gcloud container node-pools create a3-mega-pool-132 \
  --cluster=training-cluster-132 \
  --zone=your-zone \
  --machine-type=a3-megagpu-8g \
  --num-nodes=512 \
  --accelerator=type=nvidia-h100-80gb,count=8 \
  --enable-autoscaling \
  --min-nodes=512 \
  --max-nodes=512 \
  --node-taints=nvidia.com/gpu=present:NoSchedule \
  --node-labels=accelerator=nvidia-h100-80gb,gpu-partition-size=8g \
  --disk-type=pd-ssd \
  --disk-size=500GB \
  --enable-gvnic \
  --placement-type=COMPACT \
  --reservation-affinity=none \
  --enable-ip-forwarding \
  --metadata=install-gpu-driver=true
```

### Phase 3: Configure GPUDirect-TCPXO

```yaml
# tcpx-daemon-set.yaml for new cluster
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: tcpx-daemon
  namespace: kube-system
spec:
  selector:
    matchLabels:
      name: tcpx-daemon
  template:
    metadata:
      labels:
        name: tcpx-daemon
    spec:
      hostNetwork: true
      hostPID: true
      nodeSelector:
        accelerator: nvidia-h100-80gb
      tolerations:
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule
      containers:
      - name: tcpx-daemon
        image: us-docker.pkg.dev/gce-ai-infra/gpudirect-tcpxo/tcpgpudmarxd-dev:v1.0.8
        securityContext:
          privileged: true
        env:
        - name: LD_LIBRARY_PATH
          value: /usr/local/tcpxo/lib64
        volumeMounts:
        - name: sys
          mountPath: /sys
        - name: proc
          mountPath: /proc
        - name: dev
          mountPath: /dev
      volumes:
      - name: sys
        hostPath:
          path: /sys
      - name: proc
        hostPath:
          path: /proc
      - name: dev
        hostPath:
          path: /dev
```

### Phase 4: Validate New Cluster

```bash
# Test GPU and TCPX connectivity
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: tcpx-test
spec:
  nodeSelector:
    accelerator: nvidia-h100-80gb
  containers:
  - name: test
    image: nvcr.io/nvidia/pytorch:23.12-py3
    command: ["python", "-c", "import torch; print(f'GPUs available: {torch.cuda.device_count()}'); print('TCPX test passed' if torch.cuda.is_available() else 'TCPX test failed')"]
    resources:
      limits:
        nvidia.com/gpu: 8
EOF

# Verify NCCL with TCPX
kubectl exec tcpx-test -- /usr/bin/nccl-test
```

## Phase 5: Migration Strategy (Minimal Downtime)

### Option A: Checkpoint-Based Migration (Recommended)

```bash
# 1. Create checkpoint in current training
kubectl exec training-pod-0 -- python checkpoint_script.py --save /shared/checkpoint-migration

# 2. Copy checkpoint to new cluster persistent storage
kubectl cp training-pod-0:/shared/checkpoint-migration /local/checkpoint
# Transfer to new cluster's storage

# 3. Deploy training workload on new cluster
kubectl --context=new-cluster apply -f training-deployment-132.yaml

# 4. Resume from checkpoint
kubectl --context=new-cluster exec training-pod-0 -- python train.py --resume /shared/checkpoint-migration
```

### Option B: Rolling Migration (Advanced)

For gradient synchronization compatibility:

```python
# migration_handler.py
import torch.distributed as dist
import socket

def migrate_training_state():
    # Save optimizer states, learning rate schedules
    checkpoint = {
        'epoch': current_epoch,
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'lr_scheduler_state_dict': lr_scheduler.state_dict(),
        'loss': current_loss,
        'step': global_step,
        'tcpx_config': get_tcpx_topology()
    }
    torch.save(checkpoint, f'/shared/migration-checkpoint-{dist.get_rank()}.pt')
```

## Phase 6: Network Topology Preservation

Ensure TCPX topology is maintained:

```yaml
# topology-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: tcpx-topology
data:
  topology.xml: |
    <?xml version="1.0" encoding="UTF-8"?>
    <system version="1">
      <cpu numaid="0" affinity="00000000,0000ffff,00000000,0000ffff" arch="x86_64" vendor="GenuineIntel" familyid="6" modelid="143">
        <pci busid="0000:04:00.0" class="0x030200" link_speed="16 GT/s PCIe" link_width="16">
          <gpu dev="0" sm="132" gcn="0" cuda="8.9" />
        </pci>
        <!-- Define topology for all 8 H100s per node -->
      </cpu>
    </system>
```

## Rollback Plan

Maintain ability to rollback:

```bash
# Keep old cluster running until validation complete
gcloud container clusters update training-cluster-old \
  --no-enable-autoupgrade \
  --maintenance-policy-window-start="2024-12-31T00:00:00Z" \
  --zone=your-zone
```

## Monitoring During Migration

```bash
# Monitor training metrics
kubectl logs -f training-pod-0 | grep -E "(loss|accuracy|throughput)"

# Monitor TCPX performance
kubectl exec training-pod-0 -- nvidia-smi topo -m
kubectl exec training-pod-0 -- ib_write_bw # if applicable
```

## Timeline Recommendation

- **Days 1-2**: Build and validate new cluster
- **Day 3**: Create checkpoint and initiate migration (during low-activity period)
- **Day 4**: Validate training resumption and performance
- **Day 5**: Decomission old cluster

This approach minimizes risk while ensuring your GPUDirect-TCPXO configuration remains optimal for your multi-week training runs.