# GKE Cluster Configuration for H100 Foundation Model Training

## Cluster Architecture Recommendations

### Release Channel Strategy
**Use Regular channel** for your production training cluster:
- **Why not Rapid:** No SLA for upgrade stability - versions may have issues caught before reaching Regular
- **Why not Stable:** Training clusters need faster access to GPU driver updates and performance improvements
- **Why not Extended:** Unnecessary cost overhead; Regular provides sufficient stability with good feature velocity

### Multi-Environment Setup
```bash
# Training cluster (production)
gcloud container clusters create h100-training-prod \
    --release-channel regular \
    --zone us-central1-a \
    --machine-type n1-standard-4 \
    --num-nodes 3 \
    --enable-autorepair \
    --enable-autoupgrade

# Staging cluster for validation
gcloud container clusters create h100-training-staging \
    --release-channel regular \
    --zone us-central1-b \
    --machine-type n1-standard-4 \
    --num-nodes 2
```

## Training-Specific Maintenance Configuration

### Core Maintenance Settings
```bash
# Set maintenance window during training gaps (early Sunday morning)
gcloud container clusters update h100-training-prod \
    --zone us-central1-a \
    --maintenance-window-start "2024-12-15T06:00:00Z" \
    --maintenance-window-end "2024-12-15T10:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"

# Critical: Block node pool upgrades during active training
gcloud container clusters update h100-training-prod \
    --zone us-central1-a \
    --add-maintenance-exclusion-name "training-campaign-protection" \
    --add-maintenance-exclusion-start-time "2024-12-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2025-03-15T23:59:59Z" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Set disruption intervals to reduce upgrade frequency
gcloud container clusters update h100-training-prod \
    --zone us-central1-a \
    --maintenance-minor-version-disruption-interval=45d \
    --maintenance-patch-version-disruption-interval=14d
```

**Key insight:** The `no_minor_or_node_upgrades` exclusion allows critical control plane security patches while preventing any node disruption during your training campaign.

## H100 Node Pool Configuration

### GPU Node Pool Setup
```bash
# H100 training node pool
gcloud container node-pools create h100-training-pool \
    --cluster h100-training-prod \
    --zone us-central1-a \
    --machine-type a3-highgpu-8g \
    --num-nodes 8 \
    --accelerator type=nvidia-h100-80gb,count=8,gpu-driver-version=LATEST \
    --disk-size 2000 \
    --disk-type pd-ssd \
    --enable-autorepair \
    --enable-autoupgrade=false \
    --node-labels="workload=training,gpu=h100"

# Configure GPU-specific upgrade strategy (CRITICAL for H100s)
gcloud container node-pools update h100-training-pool \
    --cluster h100-training-prod \
    --zone us-central1-a \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 1
```

**Why `maxSurge=0, maxUnavailable=1`:** H100 reservations typically have no surge capacity. This drains one node at a time before creating replacement, avoiding surge capacity requirements but causing temporary capacity reduction.

### Per-NodePool Maintenance Exclusion
```bash
# Block upgrades specifically on the H100 pool during training
gcloud container node-pools update h100-training-pool \
    --cluster h100-training-prod \
    --zone us-central1-a \
    --add-maintenance-exclusion-name "h100-pool-training-freeze" \
    --add-maintenance-exclusion-start-time "2024-12-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2025-03-15T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
```

## Network Configuration for Multi-Host Training

### High-Performance Networking
```bash
# Create VPC with high MTU for RDMA
gcloud compute networks create training-vpc --mtu 8896

gcloud compute networks subnets create training-subnet \
    --network training-vpc \
    --range 10.0.0.0/16 \
    --region us-central1

# Cluster with GPUDirect-TCPX support
gcloud container clusters create h100-training-prod \
    --network training-vpc \
    --subnetwork training-subnet \
    --enable-ip-alias \
    --enable-network-policy \
    --release-channel regular \
    --zone us-central1-a \
    --cluster-version 1.31.3-gke.1146000  # Ensure GPUDirect-TCPX support
```

### Compact Placement for RDMA
```bash
# Create placement policy for low-latency interconnect
gcloud compute resource-policies create group-placement h100-placement \
    --region us-central1 \
    --collocation COLLOCATED

# Apply to node pool
gcloud container node-pools update h100-training-pool \
    --cluster h100-training-prod \
    --zone us-central1-a \
    --placement-policy h100-placement
```

## Workload Protection Configuration

### PodDisruptionBudgets for Training Jobs
```yaml
# training-pdb.yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-job-pdb
  namespace: training
spec:
  selector:
    matchLabels:
      job-type: foundation-model-training
  maxUnavailable: 0  # Prevent ANY voluntary eviction
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: foundation-model-trainer
  namespace: training
spec:
  replicas: 8  # Match H100 node count
  selector:
    matchLabels:
      job-type: foundation-model-training
  template:
    spec:
      terminationGracePeriodSeconds: 86400  # 24 hours for checkpointing
      tolerations:
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule
      nodeSelector:
        workload: training
        gpu: h100
      containers:
      - name: trainer
        resources:
          limits:
            nvidia.com/gpu: 8
            memory: 1Ti
            cpu: 96
          requests:
            nvidia.com/gpu: 8
            memory: 800Gi
            cpu: 80
```

### Checkpoint Strategy
```yaml
# checkpoint-storage.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: training-checkpoints
  namespace: training
spec:
  accessModes: [ReadWriteMany]
  storageClassName: filestore-csi
  resources:
    requests:
      storage: 10Ti
```

## Monitoring and Alerting Setup

### Training-Specific Monitoring
```yaml
# monitoring-config.yaml
apiVersion: v1
kind: ServiceMonitor
metadata:
  name: training-metrics
spec:
  selector:
    matchLabels:
      job-type: foundation-model-training
  endpoints:
  - port: metrics
    interval: 30s
    path: /metrics

---
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: training-alerts
spec:
  groups:
  - name: training.rules
    rules:
    - alert: TrainingJobDown
      expr: up{job_type="foundation-model-training"} == 0
      for: 5m
      annotations:
        summary: "Training job {{ $labels.instance }} is down"
        
    - alert: GPUUtilizationLow  
      expr: nvidia_gpu_duty_cycle < 80
      for: 15m
      annotations:
        summary: "GPU utilization dropped on {{ $labels.instance }}"
```

## Operational Runbook for Training Campaigns

### Pre-Training Checklist
```bash
# 1. Verify maintenance exclusions are active
gcloud container clusters describe h100-training-prod \
    --zone us-central1-a \
    --format="value(maintenancePolicy)"

# 2. Check GPU driver version compatibility
kubectl get nodes -o json | \
    jq '.items[].status.nodeInfo.kernelVersion'

# 3. Validate RDMA connectivity between nodes
kubectl exec -it training-pod-0 -- ib_write_bw -d mlx5_0 NODE_2_IP

# 4. Checkpoint system test
kubectl apply -f checkpoint-test-job.yaml
```

### During Training Monitoring
```bash
# Monitor GPU utilization
kubectl top nodes --selector=workload=training

# Check for any upgrade notifications
gcloud logging read 'resource.type="gke_cluster" AND 
    jsonPayload.message~"upgrade"' --limit=10

# Verify no pods are pending eviction
kubectl get pods -A | grep -E "Terminating|Evicted"
```

### Post-Training Upgrade Process
```bash
# 1. Remove maintenance exclusions
gcloud container clusters update h100-training-prod \
    --zone us-central1-a \
    --remove-maintenance-exclusion "training-campaign-protection"

gcloud container node-pools update h100-training-pool \
    --cluster h100-training-prod \
    --zone us-central1-a \
    --remove-maintenance-exclusion "h100-pool-training-freeze"

# 2. Test upgrade in staging first
gcloud container node-pools upgrade h100-staging-pool \
    --cluster h100-training-staging \
    --zone us-central1-b

# 3. Validate GPU drivers and RDMA after staging upgrade
# 4. Schedule production upgrade during next maintenance window
```

## Security Considerations

### Accelerated Patch Updates
```bash
# Enable faster security patch rollout
gcloud container clusters update h100-training-prod \
    --zone us-central1-a \
    --patch-update accelerated
```

**Note:** Even with `no_minor_or_node_upgrades` exclusion, critical control plane security patches will still be applied. This maintains security posture while protecting your training workloads.

## Cost Optimization

### Spot Instances for Non-Critical Workloads
```bash
# Separate pool for data preprocessing (can tolerate interruption)
gcloud container node-pools create preprocessing-spot \
    --cluster h100-training-prod \
    --zone us-central1-a \
    --machine-type n1-standard-32 \
    --preemptible \
    --num-nodes 4 \
    --max-surge-upgrade 2 \
    --max-unavailable-upgrade 1 \
    --node-labels="workload=preprocessing"
```

## Summary

**Key architectural decisions:**
1. **Regular channel** for stability with good feature velocity
2. **`no_minor_or_node_upgrades` exclusions** during active training campaigns  
3. **`maxSurge=0, maxUnavailable=1`** for H100 pools (assumes no surge capacity)
4. **Per-nodepool exclusions** for granular control over training vs. preprocessing nodes
5. **Extended `terminationGracePeriodSeconds`** (24h) for checkpointing
6. **High-MTU VPC** with compact placement for RDMA performance

This configuration protects your multi-week training runs while maintaining security through control plane patches and provides a clear operational model for upgrade windows between training campaigns.