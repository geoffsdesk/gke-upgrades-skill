# GKE Foundation Model Training Cluster Configuration

Based on your H100 GPU foundation model training requirements, here's the optimal configuration to protect multi-week training runs while maintaining security posture.

## Cluster Configuration

### Release Channel Strategy
**Recommended: Regular channel with "no minor or node upgrades" exclusion**

```bash
gcloud container clusters create foundation-training-cluster \
  --zone us-central1-a \
  --release-channel regular \
  --enable-autoscaling \
  --enable-autorepair \
  --enable-autoupgrade \
  --num-nodes 0 \
  --machine-type e2-medium
```

**Why Regular channel:**
- Stable patches without Rapid channel's experimental features
- Security patches arrive faster than Stable channel
- Full SLA coverage (unlike Rapid)
- Better for production training workloads than Extended channel

### Maintenance Configuration

```bash
# Configure maintenance window during training gaps
gcloud container clusters update foundation-training-cluster \
  --zone us-central1-a \
  --maintenance-window-start "2024-12-15T02:00:00Z" \
  --maintenance-window-end "2024-12-15T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"

# Add persistent "no minor or node upgrades" exclusion (tracks EoS automatically)
gcloud container clusters update foundation-training-cluster \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Configure disruption intervals for controlled upgrade frequency
gcloud container clusters update foundation-training-cluster \
  --zone us-central1-a \
  --maintenance-minor-version-disruption-interval=60d \
  --maintenance-patch-version-disruption-interval=14d
```

**Key benefits:**
- **Control plane patches still allowed** — maintains security posture without disrupting training
- **Node upgrades blocked** — prevents H100 node replacement during training runs
- **Persistent exclusion** — automatically renews at End of Support, no manual maintenance
- **Emergency override** — can add 30-day "no upgrades" exclusion for critical training phases

## Node Pool Strategy

### Training Node Pool (H100)
```bash
gcloud container node-pools create h100-training-pool \
  --cluster foundation-training-cluster \
  --zone us-central1-a \
  --machine-type a3-highgpu-8g \
  --num-nodes 8 \
  --enable-autoscaling \
  --min-nodes 0 \
  --max-nodes 32 \
  --node-locations us-central1-a \
  --placement-type COMPACT \
  --placement-policy-name training-placement-policy \
  --accelerator type=nvidia-h100-80gb,count=8 \
  --enable-gvnic \
  --disk-type pd-ssd \
  --disk-size 500GB \
  --enable-autorepair=false \
  --enable-autoupgrade=false \
  --node-taints=training=true:NoSchedule
```

**Critical H100-specific settings:**
- **`--enable-autoupgrade=false`** — Prevents automatic node upgrades during training
- **`--enable-autorepair=false`** — Prevents node replacement that would kill training jobs
- **Compact placement** — Maintains RDMA topology for multi-node training
- **Node taints** — Isolates training workloads from other pods

### Inference/Management Node Pool (separate)
```bash
gcloud container node-pools create management-pool \
  --cluster foundation-training-cluster \
  --zone us-central1-a \
  --machine-type n2-standard-4 \
  --num-nodes 2 \
  --enable-autoscaling \
  --min-nodes 1 \
  --max-nodes 10
  # Auto-upgrades enabled for non-training workloads
```

## Upgrade Strategy for Training Workloads

### During Active Training (Emergency Only)
```bash
# Add 30-day freeze for critical training phases
gcloud container clusters update foundation-training-cluster \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "critical-training-freeze" \
  --add-maintenance-exclusion-start-time "2024-12-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

### Between Training Runs (Planned Maintenance)
```bash
# 1. Checkpoint and stop training jobs
kubectl delete -f training-workload.yaml

# 2. Cordon training nodes
kubectl cordon -l cloud.google.com/gke-nodepool=h100-training-pool

# 3. Manually upgrade node pool during gap
gcloud container node-pools upgrade h100-training-pool \
  --cluster foundation-training-cluster \
  --zone us-central1-a \
  --cluster-version TARGET_VERSION

# 4. Verify GPU drivers and RDMA connectivity
kubectl apply -f gpu-test-job.yaml
kubectl logs -f job/gpu-connectivity-test

# 5. Resume training from checkpoint
kubectl apply -f training-workload.yaml
```

## Workload Protection Configuration

### Pod Disruption Budget
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
spec:
  minAvailable: 100%  # No disruption allowed during training
  selector:
    matchLabels:
      app: foundation-model-training
```

### Training Job Template
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: foundation-training
spec:
  template:
    spec:
      tolerations:
      - key: training
        operator: Equal
        value: "true"
        effect: NoSchedule
      nodeSelector:
        cloud.google.com/gke-nodepool: h100-training-pool
      terminationGracePeriodSeconds: 3600  # Allow checkpointing
      containers:
      - name: training
        image: gcr.io/your-project/training:latest
        resources:
          requests:
            nvidia.com/gpu: 8
            memory: 200Gi
            cpu: 90
          limits:
            nvidia.com/gpu: 8
            memory: 200Gi
            cpu: 90
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /checkpoints
      volumes:
      - name: checkpoint-storage
        persistentVolumeClaim:
          claimName: training-checkpoints
      restartPolicy: Never
```

## Security & Monitoring

### Patch Management Strategy
- **Control plane patches**: Auto-applied (security maintained)
- **Node patches**: Manual during training gaps
- **GPU driver updates**: Test in staging first — can change CUDA versions

### Monitoring Setup
```bash
# Enable GKE monitoring for upgrade events
gcloud container clusters update foundation-training-cluster \
  --zone us-central1-a \
  --enable-cloud-logging \
  --logging=SYSTEM,WORKLOAD,API_SERVER \
  --enable-cloud-monitoring
```

### Key Alerts
- Training job failures/restarts
- Node cordoning events
- GPU utilization drops
- Scheduled upgrade notifications (72h advance warning)

## Operational Runbook

### Weekly Routine
1. **Check upgrade status**: `gcloud container clusters get-upgrade-info foundation-training-cluster --zone us-central1-a`
2. **Review security patches**: Control plane patches applied automatically
3. **Plan node upgrades**: Schedule during training gaps only

### Monthly Routine
1. **Staging validation**: Test target GKE version on staging cluster
2. **GPU driver compatibility**: Verify CUDA/framework versions
3. **Backup verification**: Ensure checkpoint storage is working

### Training Campaign Prep
1. **Apply 30-day freeze**: Before starting multi-week runs
2. **Verify exclusions**: Confirm "no minor or node upgrades" is active
3. **Checkpoint strategy**: Enable regular checkpointing every 24h

## Summary

This configuration gives you:
- ✅ **Security**: Control plane patches applied automatically
- ✅ **Training protection**: Node upgrades blocked during campaigns  
- ✅ **Operational flexibility**: Manual control over disruptive changes
- ✅ **Cost efficiency**: Only pay for Extended support when needed
- ✅ **Hardware optimization**: Compact placement preserves RDMA topology

The key insight: **Regular channel + "no minor or node upgrades" exclusion** is the optimal balance for ML training — you get security patches without training disruption, and full control over when nodes are replaced.