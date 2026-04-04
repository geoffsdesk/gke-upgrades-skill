# GKE Foundation Model Training Cluster Configuration

This configuration minimizes upgrade disruption for multi-week H100 training runs while maintaining security posture.

## Core Cluster Configuration

### Release Channel Strategy
```bash
# Use Extended channel for maximum control over minor versions
gcloud container clusters create foundation-model-cluster \
  --release-channel extended \
  --cluster-version 1.31.3-gke.1146000  # Latest stable version supporting H100
  --enable-network-policy \
  --enable-ip-alias \
  --num-nodes 0  # No default pool
  --region us-central1  # Multi-zone for control plane HA
  --machine-type n1-standard-4 \
  --disk-type pd-ssd \
  --enable-autoscaling \
  --enable-autorepair \
  --enable-autoupgrade  # We'll control this with exclusions
```

**Why Extended channel:**
- Minor version auto-upgrades are NOT automatic (except at end of extended support)
- You manually control when minor upgrades happen between training campaigns
- Patches still auto-apply at Regular channel timing (security maintained)
- Up to 24 months support (cost only during extended period)
- Best fit for training workloads requiring predictable infrastructure

### Training Node Pool (H100)
```bash
# Dedicated training pool with upgrade protection
gcloud container node-pools create h100-training \
  --cluster foundation-model-cluster \
  --machine-type a3-highgpu-8g \  # 8x H100 80GB
  --num-nodes 0 \
  --enable-autoscaling \
  --min-nodes 0 \
  --max-nodes 64 \  # Adjust based on reservation
  --node-locations us-central1-a,us-central1-b \
  --disk-type pd-ssd \
  --disk-size 500GB \
  --enable-autorepair \
  --max-unavailable-upgrade 4 \  # Primary lever for GPU upgrades
  --max-surge-upgrade 0 \  # No surge capacity for H100
  --placement-type COMPACT \  # Preserve RDMA topology
  --reservation-affinity any \
  --accelerator type=nvidia-h100-80gb,count=8
```

### Inference Node Pool (Separate)
```bash
# Separate pool for inference with different upgrade strategy
gcloud container node-pools create h100-inference \
  --cluster foundation-model-cluster \
  --machine-type a3-highgpu-8g \
  --enable-autoscaling \
  --min-nodes 2 \
  --max-nodes 16 \
  --enable-blue-green-upgrade \  # Better for serving workloads
  --node-pool-soak-duration 1800s \  # 30min validation
  --standard-rollout-policy batch-node-count=1,batch-soak-duration=300s
```

## Maintenance Control Strategy

### Maximum Protection Configuration
```bash
# Block minor and node upgrades, allow only CP security patches
gcloud container clusters update foundation-model-cluster \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --add-maintenance-exclusion-name "training-protection"

# Set disruption intervals for patch control
gcloud container clusters update foundation-model-cluster \
  --maintenance-patch-version-disruption-interval 7776000s \  # 90 days max
  --maintenance-minor-version-disruption-interval 7776000s    # 90 days
```

### Maintenance Windows
```bash
# Saturday early morning maintenance window (4-hour window)
gcloud container clusters update foundation-model-cluster \
  --maintenance-window-start "2026-01-04T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Training Campaign Workflow

### Before Starting Multi-Week Training
```bash
# 1. Verify no pending upgrades
gcloud container clusters get-upgrade-info foundation-model-cluster --region us-central1

# 2. Scale training pool and start workloads
kubectl apply -f training-job.yaml

# 3. Add temporary "no upgrades" exclusion for critical training periods
gcloud container clusters update foundation-model-cluster \
  --add-maintenance-exclusion-name "critical-training-run" \
  --add-maintenance-exclusion-start "2026-02-01T00:00:00Z" \
  --add-maintenance-exclusion-end "2026-02-28T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

### Between Training Campaigns (Upgrade Window)
```bash
# 1. Wait for training completion, checkpoint saved
kubectl get pods -l job-type=training --field-selector status.phase=Running

# 2. Remove temporary exclusion
gcloud container clusters update foundation-model-cluster \
  --remove-maintenance-exclusion "critical-training-run"

# 3. Optionally upgrade control plane minor version manually
gcloud container clusters upgrade foundation-model-cluster \
  --master \
  --cluster-version 1.32.x-gke.xxxxx

# 4. Upgrade node pools during downtime
gcloud container node-pools upgrade h100-training \
  --cluster foundation-model-cluster \
  --cluster-version 1.32.x-gke.xxxxx

# 5. Validate cluster health before next training campaign
kubectl get nodes
kubectl get pods -n kube-system
```

## Training Workload Protection

### PodDisruptionBudget for Training Jobs
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
  namespace: training
spec:
  minAvailable: "100%"  # Prevent any training pod eviction
  selector:
    matchLabels:
      workload-type: training
```

### Training Job with Checkpointing
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: foundation-model-training
  namespace: training
spec:
  template:
    metadata:
      annotations:
        cluster-autoscaler.kubernetes.io/safe-to-evict: "false"
    spec:
      terminationGracePeriodSeconds: 3600  # 1 hour for checkpoint save
      containers:
      - name: trainer
        image: training-image:latest
        resources:
          requests:
            nvidia.com/gpu: 8
            memory: 200Gi
            cpu: 48
          limits:
            nvidia.com/gpu: 8
            memory: 200Gi
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /checkpoints
        - name: dataset-storage  
          mountPath: /data
      nodeSelector:
        cloud.google.com/gke-nodepool: h100-training
      tolerations:
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule
```

## Monitoring and Alerting

### Upgrade Event Monitoring
```bash
# Enable scheduled upgrade notifications (72h advance warning)
gcloud container clusters update foundation-model-cluster \
  --enable-scheduled-upgrades

# Cloud Logging query for upgrade notifications
resource.type="gke_cluster"
resource.labels.cluster_name="foundation-model-cluster"
(protoPayload.metadata.operationType="UPDATE_CLUSTER" OR 
 protoPayload.metadata.operationType="UPGRADE_MASTER" OR
 jsonPayload.notification_type="UPGRADE_AVAILABLE")
```

### Training Job Health Monitoring
```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: training-metrics
spec:
  selector:
    matchLabels:
      app: training-job
  endpoints:
  - port: metrics
    interval: 30s
```

## Security & Compliance

### Accelerated Patch Updates (if needed for compliance)
```bash
# For FedRAMP/high-security environments
gcloud container clusters update foundation-model-cluster \
  --patch-update accelerated
```

### Network Security
```yaml
# NetworkPolicy to isolate training workloads
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: training-isolation
  namespace: training
spec:
  podSelector:
    matchLabels:
      workload-type: training
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          role: training-coordinator
  egress:
  - to: []  # Restrict outbound as needed
```

## Key Benefits of This Configuration

1. **Maximum Training Protection**: Extended channel + "no minor or node" exclusion prevents disruptive upgrades during training
2. **Security Maintained**: Control plane patches still auto-apply for security
3. **Flexible Upgrade Control**: Manual minor upgrades between training campaigns
4. **GPU-Optimized**: maxUnavailable strategy for H100 pools (no surge capacity needed)
5. **Separate Inference Strategy**: Blue-green upgrades for serving workloads
6. **72-Hour Upgrade Warnings**: Scheduled notifications for planning
7. **Compliance Ready**: Accelerated patches available if needed

## Important Operational Notes

- **Maintenance exclusions are cluster-level** on release channels - they protect all node pools
- **Extended channel costs apply only during extended support period** (beyond 14 months)
- **GPU VMs require pod restarts** for any upgrade - no live migration possible
- **Compact placement preserves RDMA topology** during upgrades
- **Plan 4-8 hour upgrade windows** for large H100 clusters due to sequential upgrade constraints

This configuration gives you maximum control over when disruptions happen while maintaining Google's security patch cadence - ideal for foundation model training workloads.