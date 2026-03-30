# GKE Cluster Configuration for H100 Foundation Model Training

## Recommended Cluster Configuration

### Release Channel Strategy
**Extended channel** is optimal for your use case:
- **No automatic minor version upgrades** on the control plane (except at end of extended support)
- **24 months of support** for versions 1.27+ (cost only during extended period)
- **Patches auto-applied at Regular channel timing** — you still get security patches without delay
- **Maximum flexibility around EoS enforcement** — upgrades only when you choose

```bash
gcloud container clusters create training-cluster \
    --zone=ZONE \
    --release-channel=extended \
    --cluster-version=LATEST_SUPPORTED_VERSION \
    --enable-ip-alias \
    --enable-shielded-nodes \
    --enable-network-policy \
    --num-nodes=0 \
    --machine-type=e2-standard-4
```

### Maintenance Controls for Maximum Protection

Configure the most restrictive maintenance policy to protect training runs:

```bash
# Block minor and node upgrades, allow control plane patches only
gcloud container clusters update training-cluster \
    --zone=ZONE \
    --add-maintenance-exclusion-scope=no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support \
    --maintenance-window-start="2024-01-01T02:00:00Z" \
    --maintenance-window-duration=4h \
    --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SUN" \
    --maintenance-patch-version-disruption-interval=7776000s
```

**Key settings explained:**
- `no_minor_or_node_upgrades`: Prevents disruptive upgrades, allows CP security patches
- `until-end-of-support`: Auto-renews exclusion when adopting new minor versions
- **Sunday 2-6 AM maintenance window**: Patches applied during low-activity period
- **90-day patch interval**: Maximum gap between CP patches (adjust to monthly if needed for compliance)

### H100 Training Node Pool Configuration

Create dedicated training pools with upgrade protection:

```bash
gcloud container node-pools create h100-training-pool \
    --cluster=training-cluster \
    --zone=ZONE \
    --machine-type=a3-highgpu-8g \
    --accelerator=type=nvidia-h100-80gb,count=8 \
    --num-nodes=8 \
    --enable-autoscaling=false \
    --disk-type=pd-ssd \
    --disk-size=1000GB \
    --node-taints=nvidia.com/gpu=present:NoSchedule \
    --node-labels=workload-type=training,gpu-type=h100 \
    --max-surge-upgrade=0 \
    --max-unavailable-upgrade=1
```

**Critical H100-specific settings:**
- **`maxSurge=0, maxUnavailable=1`**: H100 reservations typically have no surge capacity
- **Autoscaling disabled**: Fixed pool size prevents scaling conflicts during training
- **Taints/labels**: Ensure only training workloads land on expensive H100 nodes

### GPU Driver and Networking Considerations

```bash
# Verify GPUDirect-TCPX support (requires GKE 1.27.7-gke.1121000+)
gcloud container clusters update training-cluster \
    --zone=ZONE \
    --enable-gvnic \
    --network-performance-config=tier=PREMIUM

# Configure compact placement for RDMA topology
gcloud compute resource-policies create group-placement h100-placement \
    --collocation=COLLOCATED \
    --zone=ZONE

gcloud container node-pools update h100-training-pool \
    --cluster=training-cluster \
    --zone=ZONE \
    --placement-policy-name=h100-placement
```

## Training Workload Protection Strategy

### Pod-level Protection

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: foundation-model-training
spec:
  serviceName: training-service
  replicas: 8  # Match node count
  template:
    metadata:
      annotations:
        cluster-autoscaler.kubernetes.io/safe-to-evict: "false"
    spec:
      terminationGracePeriodSeconds: 3600  # 1 hour for checkpointing
      nodeSelector:
        workload-type: training
      tolerations:
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule
      containers:
      - name: training
        image: your-training-image:latest
        resources:
          requests:
            nvidia.com/gpu: 8
            memory: 400Gi
            cpu: 90
          limits:
            nvidia.com/gpu: 8
            memory: 400Gi
            cpu: 90
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
spec:
  selector:
    matchLabels:
      app: foundation-model-training
  minAvailable: 7  # Allow 1 pod to be disrupted max
```

### Checkpointing and Recovery

```bash
# Example checkpoint script to run before any maintenance
#!/bin/bash
CHECKPOINT_DIR="/mnt/checkpoints/$(date +%Y%m%d_%H%M%S)"
kubectl exec training-pod-0 -- python save_checkpoint.py --path=${CHECKPOINT_DIR}

# Verify checkpoint integrity
kubectl exec training-pod-0 -- python verify_checkpoint.py --path=${CHECKPOINT_DIR}
```

## Upgrade Strategy for Training Environments

### Planned Upgrade Workflow

1. **Between training campaigns only:**
```bash
# Check training status
kubectl get pods -l app=foundation-model-training -o wide

# Wait for natural training completion
# Apply temporary "no upgrades" exclusion if emergency upgrade needed during training
gcloud container clusters update training-cluster \
    --zone=ZONE \
    --add-maintenance-exclusion-name="training-campaign-protection" \
    --add-maintenance-exclusion-start="2024-MM-DDTHH:MM:SSZ" \
    --add-maintenance-exclusion-end="2024-MM-DDTHH:MM:SSZ" \
    --add-maintenance-exclusion-scope=no_upgrades
```

2. **When ready to upgrade (training gap):**
```bash
# Remove temporary exclusion, keep persistent exclusion
gcloud container clusters update training-cluster \
    --zone=ZONE \
    --remove-maintenance-exclusion="training-campaign-protection"

# Manual upgrade during controlled window
gcloud container clusters upgrade training-cluster \
    --zone=ZONE \
    --master \
    --cluster-version=TARGET_VERSION

# Node pool upgrade (if needed)
gcloud container node-pools upgrade h100-training-pool \
    --cluster=training-cluster \
    --zone=ZONE \
    --cluster-version=TARGET_VERSION
```

## Monitoring and Alerting Setup

### Upgrade Notification Monitoring

```bash
# Enable scheduled upgrade notifications (72h advance warning)
gcloud container clusters update training-cluster \
    --zone=ZONE \
    --enable-scheduled-upgrades

# Create log-based alert for upgrade notifications
gcloud alpha logging sinks create upgrade-alerts \
    pubsub.googleapis.com/projects/PROJECT_ID/topics/gke-upgrades \
    --log-filter='resource.type="gke_cluster"
    protoPayload.methodName="google.container.v1beta1.ClusterManager.UpdateCluster"
    protoPayload.metadata.operationType="UPGRADE_MASTER"'
```

### Training Health Monitoring

```yaml
# Prometheus alerting rules for training disruption
groups:
- name: training.rules
  rules:
  - alert: TrainingPodEvicted
    expr: increase(kube_pod_container_status_terminated_reason{reason="Evicted"}[5m]) > 0
    labels:
      severity: critical
    annotations:
      summary: "Training pod evicted - check for upgrade activity"
      
  - alert: H100NodeNotReady
    expr: kube_node_status_condition{condition="Ready",status="false",node=~".*h100.*"} == 1
    for: 2m
    labels:
      severity: critical
```

## Security and Compliance Considerations

For maximum security while protecting training:

```bash
# Enable binary authorization
gcloud container binauthz policy import policy.yaml

# Network policies for H100 pool isolation
kubectl apply -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: training-isolation
spec:
  podSelector:
    matchLabels:
      workload-type: training
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: training-namespace
  egress:
  - to: []
    ports:
    - protocol: TCP
      port: 443  # Allow HTTPS for model downloads
EOF
```

## Key Recommendations Summary

✅ **Extended release channel** - No auto minor upgrades, 24-month support  
✅ **"No minor or node upgrades" exclusion** - Persistent until EoS  
✅ **90-day patch disruption interval** - Minimize CP restart frequency  
✅ **maxSurge=0, maxUnavailable=1** - Works with fixed H100 reservations  
✅ **Dedicated training pools** with taints/tolerations  
✅ **PDB protection** allowing max 1 disrupted pod  
✅ **Checkpointing strategy** with 1-hour termination grace period  
✅ **Scheduled upgrade notifications** for 72h advance warning  

This configuration gives you maximum protection for multi-week training runs while maintaining security through automated control plane patching. The persistent maintenance exclusion means you only upgrade when YOU decide it's time, not when GKE's auto-upgrade schedule dictates.