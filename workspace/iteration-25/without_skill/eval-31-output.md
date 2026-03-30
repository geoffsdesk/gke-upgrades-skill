This is a critical upgrade scenario that requires careful planning to avoid disrupting your multi-week training runs. Here's a comprehensive approach:

## Pre-Upgrade Assessment

First, verify your current setup's upgrade compatibility:

```bash
# Check current cluster version and upgrade path
gcloud container clusters describe CLUSTER_NAME --zone=ZONE \
  --format="value(currentMasterVersion,currentNodeVersion)"

# Verify GPUDirect-TCPXO configuration
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.allocatable.nvidia\.com/gpu}{"\n"}{end}'
```

## Strategy 1: Blue-Green Cluster Migration (Recommended)

Create a parallel cluster for future workloads while preserving the current one:

```bash
# Create new GKE 1.32 cluster with identical GPU configuration
gcloud container clusters create training-cluster-v2 \
  --zone=us-central1-a \
  --machine-type=a3-megagpu-8g \
  --num-nodes=64 \
  --node-locations=us-central1-a,us-central1-b,us-central1-c \
  --cluster-version=1.32 \
  --enable-ip-alias \
  --enable-network-policy \
  --accelerator=type=nvidia-h100-mega-80gb,count=8,gpu-driver-version=latest \
  --enable-gvnic \
  --placement-type=COMPACT \
  --placement-policy=gpu-topology-aware
```

Apply the same GPUDirect-TCPXO configuration:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: tcpxo-config
  namespace: kube-system
data:
  enable_tcpxo: "true"
  tcpxo_net_plugin: "gvnic"
---
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: tcpxo-installer
  namespace: kube-system
spec:
  selector:
    matchLabels:
      name: tcpxo-installer
  template:
    metadata:
      labels:
        name: tcpxo-installer
    spec:
      hostNetwork: true
      hostPID: true
      containers:
      - name: tcpxo-installer
        image: gcr.io/gke-release/tcpxo-daemon:latest
        securityContext:
          privileged: true
        volumeMounts:
        - name: host-root
          mountPath: /host
      volumes:
      - name: host-root
        hostPath:
          path: /
      tolerations:
      - operator: Exists
```

## Strategy 2: Gradual Node Pool Rotation (Higher Risk)

If you must upgrade the existing cluster, use a careful node pool approach:

```bash
# Create new node pool with 1.32
gcloud container node-pools create training-pool-v2 \
  --cluster=training-cluster \
  --zone=us-central1-a \
  --machine-type=a3-megagpu-8g \
  --num-nodes=8 \
  --node-version=1.32 \
  --accelerator=type=nvidia-h100-mega-80gb,count=8 \
  --enable-gvnic \
  --placement-type=COMPACT

# Cordon nodes in batches to prevent new workload scheduling
kubectl cordon NODE_NAME
```

## Critical Checkpoints

Before proceeding with either strategy:

```bash
# Save current training state/checkpoint
kubectl exec -it TRAINING_POD -- /save_checkpoint.sh

# Verify GPUDirect-TCPXO status
kubectl get pods -n kube-system -l name=tcpxo-installer
kubectl logs -n kube-system -l name=tcpxo-installer

# Check NCCL topology
kubectl exec -it TRAINING_POD -- nvidia-smi topo -m
```

## Training Job Protection

Ensure your training job can handle node maintenance:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: llm-training
spec:
  template:
    spec:
      restartPolicy: Never
      tolerations:
      - key: "maintenance"
        operator: "Equal"
        value: "true"
        effect: "NoSchedule"
      - key: "node.kubernetes.io/not-ready"
        operator: "Exists"
        effect: "NoExecute"
        tolerationSeconds: 300
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - key: "cloud.google.com/gke-nodepool"
                operator: In
                values: ["training-pool-v1"]  # Pin to current pool
```

## Recommended Approach

Given your 2-3 week training runs and the critical nature of H100 clusters:

1. **Complete current training run** on existing cluster
2. **Create new 1.32 cluster** in parallel for next training cycle
3. **Validate GPUDirect-TCPXO** performance on new cluster with shorter test runs
4. **Migrate workloads** only after validation
5. **Decommission old cluster** once stable

## Validation Script

```bash
#!/bin/bash
# validate-tcpxo.sh

# Test GPU connectivity
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: nccl-test
spec:
  containers:
  - name: nccl-test
    image: nvcr.io/nvidia/pytorch:24.01-py3
    command: ["/bin/bash", "-c", "python -c 'import torch; print(torch.cuda.device_count()); torch.distributed.init_process_group(backend=\"nccl\")'"]
    resources:
      limits:
        nvidia.com/gpu: 8
EOF

# Monitor for 10 minutes
kubectl logs -f nccl-test
```

This approach prioritizes your active training run while ensuring a safe upgrade path. The key is avoiding any disruption to your current expensive compute workload while preparing a validated environment for future runs.