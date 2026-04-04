# GKE Configuration for Foundation Model Training with H100 GPUs

## Executive Summary

For multi-week foundation model training on H100 GPUs, you need **maximum upgrade control** while maintaining security posture. The recommended configuration uses Extended release channel with "no minor or node upgrades" exclusions, allowing critical security patches while blocking disruptive upgrades during training campaigns.

## Core Cluster Configuration

### Release Channel Strategy
**Recommendation: Extended Channel**

```bash
gcloud container clusters create training-cluster \
    --release-channel extended \
    --enable-ip-alias \
    --enable-network-policy \
    --enable-shielded-nodes \
    --cluster-version 1.31.1-gke.1678000 \
    --region us-central1 \
    --node-locations us-central1-a,us-central1-b,us-central1-c
```

**Why Extended Channel:**
- Up to 24 months support per version (extra cost only during extended period)
- Minor version upgrades are NOT automated — you control when they happen
- Security patches still auto-apply at Regular channel timing
- Best balance of security + control for long-running AI workloads
- Recommended migration path from legacy "No channel" configurations

### Maintenance Exclusion Strategy
**Primary Control: "No minor or node upgrades" exclusion**

```bash
gcloud container clusters update training-cluster \
    --region us-central1 \
    --add-maintenance-exclusion-name "training-protection" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

This exclusion:
- **Blocks:** Minor version upgrades + node pool upgrades (the disruptive changes)
- **Allows:** Control plane security patches (critical for compliance)
- **Duration:** Automatically tracks version End of Support — no manual renewal needed
- **Effect:** Training runs protected from forced restarts, but cluster stays patched

### Maintenance Window Configuration
**Schedule upgrades during planned training gaps**

```bash
gcloud container clusters update training-cluster \
    --region us-central1 \
    --maintenance-window-start "2026-01-04T06:00:00Z" \
    --maintenance-window-duration 8h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Disruption Interval for Patch Control:**
```bash
gcloud container clusters update training-cluster \
    --region us-central1 \
    --maintenance-patch-version-disruption-interval=7776000s  # 90 days max
```

This limits control plane patches to once every 90 days maximum — ideal for mega-clusters where even CP patches need careful timing.

## H100 GPU Node Pool Strategy

### Node Pool Configuration
```bash
gcloud container node-pools create h100-training \
    --cluster training-cluster \
    --region us-central1 \
    --machine-type a3-highgpu-8g \
    --accelerator type=nvidia-h100-80gb,count=8 \
    --num-nodes 16 \
    --enable-autoscaling \
    --max-nodes 64 \
    --min-nodes 0 \
    --disk-type pd-ssd \
    --disk-size 1000GB \
    --node-taints nvidia.com/gpu=present:NoSchedule \
    --enable-gvnic \
    --enable-ip-alias \
    --placement-type COMPACT \
    --max-pods-per-node 15
```

### GPU Pool Upgrade Strategy
**Critical: maxUnavailable is your PRIMARY control lever**

```bash
gcloud container node-pools update h100-training \
    --cluster training-cluster \
    --region us-central1 \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 1
```

**Why maxSurge=0:**
- H100 reservations typically have no surge capacity
- Surge nodes will fail to provision, stalling the upgrade
- maxUnavailable becomes the only effective lever

**Alternative for inference pools (if applicable):**
```bash
# Use autoscaled blue-green for inference workloads
gcloud container node-pools update h100-inference \
    --cluster training-cluster \
    --region us-central1 \
    --enable-autoscaling \
    --total-min-nodes 4 \
    --total-max-nodes 32 \
    --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

## Training Job Protection Strategy

### Pod Configuration for Multi-Week Jobs
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: foundation-model-training
spec:
  template:
    metadata:
      annotations:
        cluster-autoscaler.kubernetes.io/safe-to-evict: "false"
    spec:
      terminationGracePeriodSeconds: 3600  # 1 hour for checkpoint
      tolerations:
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule
      containers:
      - name: trainer
        image: your-training-image:latest
        resources:
          requests:
            nvidia.com/gpu: 8
            cpu: 96
            memory: 1000Gi
          limits:
            nvidia.com/gpu: 8
            cpu: 96
            memory: 1000Gi
```

### PDB for Training Jobs
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: foundation-model-training
```

### Campaign-Based Exclusions (Optional)
**For additional protection during critical training phases:**

```bash
# Apply "no upgrades" exclusion during critical training (30-day max)
gcloud container clusters update training-cluster \
    --region us-central1 \
    --add-maintenance-exclusion-name "critical-training-campaign" \
    --add-maintenance-exclusion-start-time "2026-03-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2026-03-31T00:00:00Z" \
    --add-maintenance-exclusion-scope no_upgrades
```

**Warning:** This blocks ALL upgrades including security patches. Use sparingly and plan catch-up upgrades.

## Networking for Multi-Node Training

### GPUDirect-TCPX Configuration
```bash
# Verify GKE version supports GPUDirect-TCPX (requires 1.27.7-gke.1121000+)
gcloud container clusters describe training-cluster \
    --region us-central1 \
    --format="value(currentMasterVersion)"

# Enable high-bandwidth inter-GPU communication
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: gpu-direct-config
  namespace: kube-system
data:
  enable-gpu-direct: "true"
EOF
```

### Compact Placement Verification
```bash
# Verify nodes land in same placement group
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool
kubectl describe nodes | grep "zone\|placement"
```

## Monitoring and Alerting

### Upgrade Event Monitoring
```bash
# Enable cluster notifications
gcloud container clusters update training-cluster \
    --region us-central1 \
    --enable-notification-config \
    --notification-config-pubsub-topic projects/PROJECT_ID/topics/gke-upgrades

# Enable scheduled upgrade notifications (72h advance warning)
gcloud container clusters update training-cluster \
    --region us-central1 \
    --enable-scheduled-upgrades
```

### Training Job Health Checks
```yaml
# Add to training pods
livenessProbe:
  exec:
    command:
    - /bin/sh
    - -c
    - "nvidia-smi && python /app/health_check.py"
  initialDelaySeconds: 300
  periodSeconds: 300
  timeoutSeconds: 60
readinessProbe:
  exec:
    command:
    - /bin/sh
    - -c
    - "python /app/training_progress_check.py"
  initialDelaySeconds: 60
  periodSeconds: 60
```

## Planned Upgrade Workflow

### 1. Pre-Training Setup (Week 0)
```bash
# Verify cluster configuration
gcloud container clusters describe training-cluster \
    --region us-central1 \
    --format="table(name,releaseChannel.channel,currentMasterVersion)"

# Check maintenance exclusions
gcloud container clusters describe training-cluster \
    --region us-central1 \
    --format="yaml(maintenancePolicy)"

# Validate GPU driver version
kubectl get nodes -o json | jq -r '.items[].status.nodeInfo.kubeletVersion'
```

### 2. During Training (Weeks 1-8)
```bash
# Monitor upgrade notifications
gcloud logging read 'resource.type="gke_cluster" 
  protoPayload.metadata.operationType="UPGRADE_MASTER"
  resource.labels.cluster_name="training-cluster"' \
  --limit=10 --format=json

# Check for any forced upgrade warnings
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=us-central1 \
    --project=PROJECT_ID \
    --filter="category.category:RELIABILITY"
```

### 3. Between Training Campaigns (Maintenance Window)
```bash
# Check upgrade targets
gcloud container clusters get-upgrade-info training-cluster \
    --region us-central1

# Plan staged upgrade if needed
# 1. Upgrade control plane first
gcloud container clusters upgrade training-cluster \
    --region us-central1 \
    --master \
    --cluster-version TARGET_VERSION

# 2. Create staging H100 pool for testing
gcloud container node-pools create h100-staging \
    --cluster training-cluster \
    --region us-central1 \
    --machine-type a3-highgpu-8g \
    --num-nodes 2 \
    --cluster-version TARGET_VERSION

# 3. Validate training workload on new version
# 4. Upgrade production pool after validation
```

## Cost Optimization Notes

**Extended Channel Billing:**
- No additional cost during standard 14-month support period
- Extra cost only applies during months 15-24 (extended support period)
- For 1.31.x deployed in 2026, extended charges begin ~March 2027

**Reservation Strategy:**
- Request H100 reservations in 3 zones for resilience
- Include 10% headroom for surge capacity if available
- Monitor reservation utilization during training gaps

## Security Considerations

**With "no minor or node upgrades" exclusion active:**
- ✅ Control plane security patches still auto-apply
- ✅ Node OS security patches continue via node auto-repair
- ❌ Kubernetes minor version security fixes blocked until manual upgrade
- ❌ Node image security updates blocked until manual upgrade

**Mitigation:**
- Monitor GKE security bulletins closely
- Plan emergency manual upgrades for critical CVEs
- Use vulnerability scanning on container images
- Implement runtime security monitoring (Falco, etc.)

## Emergency Procedures

### Critical Security Update Required
```bash
# Pause training gracefully
kubectl scale deployment training-job --replicas=0

# Remove exclusion temporarily
gcloud container clusters update training-cluster \
    --region us-central1 \
    --remove-maintenance-exclusion "training-protection"

# Trigger emergency upgrade
gcloud container node-pools upgrade h100-training \
    --cluster training-cluster \
    --region us-central1 \
    --cluster-version SECURITY_VERSION

# Restore exclusion after upgrade
gcloud container clusters update training-cluster \
    --region us-central1 \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

### Upgrade Stuck During Emergency
```bash
# Check for common GPU pool issues
kubectl get pods -A | grep -E "Pending|Terminating"
kubectl get nodes | grep -v Ready

# Force drain if needed (data loss risk - checkpoint first!)
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --force --grace-period=0
```

This configuration provides maximum protection for multi-week training runs while maintaining security compliance. The Extended channel + exclusion strategy is specifically designed for AI/ML workloads where training campaign protection is more critical than staying on the absolute latest Kubernetes version.