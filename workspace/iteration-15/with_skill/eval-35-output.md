# Foundation Model Training GKE Cluster Configuration

## Executive Summary
For multi-week training runs on H100 GPUs, the primary goal is **preventing forced interruptions** while maintaining security. This requires dedicated training node pools with upgrade protection, separate infrastructure pools for auto-upgrades, and careful maintenance window orchestration.

## Cluster Foundation

### Cluster Mode & Networking
```bash
# Regional cluster for HA control plane (training continues during CP upgrades)
gcloud container clusters create llm-training-cluster \
  --region us-central1 \
  --release-channel regular \
  --enable-network-policy \
  --enable-ip-alias \
  --network training-vpc \
  --subnetwork training-subnet \
  --cluster-version 1.31.3-gke.1146000 \
  --enable-autorepair \
  --enable-autoupgrade \
  --max-nodes-per-pool 1000
```

### Release Channel Strategy
**Recommendation: Regular channel** (not Rapid, not Stable)
- **Why Regular over Rapid:** Rapid channel has no SLA for upgrade stability — versions may have issues caught before reaching Regular. H100 training workloads need maximum reliability.
- **Why Regular over Stable:** Regular provides security patches ~1 week faster than Stable while maintaining full SLA. For multi-week training runs, faster security patches reduce accumulated risk.
- **Why not Extended:** Extended requires manual minor version upgrades, adding operational overhead. Regular's auto-upgrade with proper exclusions provides better security posture.

## Node Pool Architecture

### Training Node Pool (H100) - Maximum Protection
```bash
# Dedicated training pool with upgrade protection
gcloud container node-pools create h100-training \
  --cluster llm-training-cluster \
  --region us-central1 \
  --machine-type a3-highgpu-8g \
  --accelerator type=nvidia-h100-80gb,count=8 \
  --num-nodes 16 \
  --node-locations us-central1-a,us-central1-c \
  --placement-type COMPACT \
  --placement-policy-name h100-placement-group \
  --enable-autoscaling \
  --min-nodes 0 \
  --max-nodes 32 \
  --disk-type pd-ssd \
  --disk-size 2048 \
  --enable-autorepair \
  --node-taints nvidia.com/gpu=h100:NoSchedule \
  --node-labels workload-type=training,gpu-type=h100
```

### Infrastructure Node Pool - Auto-Upgrade Enabled
```bash
# Separate pool for monitoring, logging, operators
gcloud container node-pools create infrastructure \
  --cluster llm-training-cluster \
  --region us-central1 \
  --machine-type c2d-standard-16 \
  --num-nodes 3 \
  --enable-autoscaling \
  --min-nodes 2 \
  --max-nodes 10 \
  --enable-autorepair \
  --node-labels workload-type=infrastructure
```

## Maintenance Protection Strategy

### Per-Node Pool Maintenance Exclusions
```bash
# Block all upgrades on training pool during campaigns
gcloud container node-pools update h100-training \
  --cluster llm-training-cluster \
  --region us-central1 \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-scope "no_minor_or_node_upgrades" \
  --add-maintenance-exclusion-until-end-of-support

# Allow infrastructure pool to auto-upgrade (security patches + features)
# No exclusion needed - uses cluster-level maintenance window only
```

### Cluster-Level Maintenance Windows
```bash
# Weekend maintenance window for control plane upgrades
gcloud container clusters update llm-training-cluster \
  --region us-central1 \
  --maintenance-window-start "2024-12-07T22:00:00-08:00" \
  --maintenance-window-duration "PT4H" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Set disruption intervals to control upgrade frequency
gcloud container clusters update llm-training-cluster \
  --region us-central1 \
  --maintenance-minor-version-disruption-interval=30d \
  --maintenance-patch-version-disruption-interval=7d
```

### Emergency Freeze Capability
```bash
# For critical periods (model eval, paper deadlines)
gcloud container clusters update llm-training-cluster \
  --region us-central1 \
  --add-maintenance-exclusion-name "emergency-freeze" \
  --add-maintenance-exclusion-start-time "2024-12-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-01-15T00:00:00Z" \
  --add-maintenance-exclusion-scope "no_upgrades"
```

## Training Workload Protection

### Pod Disruption Budget
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
  namespace: training
spec:
  selector:
    matchLabels:
      app: foundation-model-training
  maxUnavailable: 0  # No voluntary disruptions
```

### Extended Termination Grace Period
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: foundation-model-training
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 57600  # 16 hours for checkpoint save
      tolerations:
      - key: nvidia.com/gpu
        value: h100
        effect: NoSchedule
      nodeSelector:
        workload-type: training
        gpu-type: h100
```

## Upgrade Strategy for Training Pools

### Planned Upgrade Workflow
```bash
# 1. Pause training job submissions
kubectl scale deployment training-job-scheduler --replicas=0

# 2. Wait for current jobs to checkpoint and complete
# Monitor: kubectl get pods -n training -l app=foundation-model-training

# 3. Temporarily remove maintenance exclusion
gcloud container node-pools update h100-training \
  --cluster llm-training-cluster \
  --region us-central1 \
  --remove-maintenance-exclusion-name "training-protection"

# 4. Manual upgrade with drain-first strategy (no surge capacity needed)
gcloud container node-pools update h100-training \
  --cluster llm-training-cluster \
  --region us-central1 \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2  # Parallel upgrades for speed

gcloud container node-pools upgrade h100-training \
  --cluster llm-training-cluster \
  --region us-central1 \
  --cluster-version TARGET_VERSION

# 5. Verify GPU driver compatibility
kubectl describe nodes -l gpu-type=h100 | grep nvidia.com/gpu

# 6. Re-enable training protection
gcloud container node-pools update h100-training \
  --cluster llm-training-cluster \
  --region us-central1 \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-scope "no_minor_or_node_upgrades" \
  --add-maintenance-exclusion-until-end-of-support

# 7. Resume training
kubectl scale deployment training-job-scheduler --replicas=1
```

## Security & Compliance Balance

### Monitoring for Security Patches
```bash
# Set up alerting for security-critical patches
gcloud logging sinks create gke-security-patches \
  pubsub.googleapis.com/projects/PROJECT_ID/topics/gke-security-alerts \
  --log-filter='resource.type="gke_cluster" 
               protoPayload.methodName="google.container.v1.ClusterManager.UpdateCluster"
               severity>=WARNING'
```

### Quarterly Security Review Process
1. **Week 1:** Review accumulated patches in staging cluster
2. **Week 2:** Test GPU driver compatibility with target versions
3. **Week 3:** Schedule training gap for production upgrade
4. **Week 4:** Execute upgrade during planned maintenance window

## Multi-Environment Strategy

### Environment Topology
- **Dev cluster:** Regular channel, auto-upgrades enabled
- **Staging cluster:** Regular channel, same exclusions as prod for testing
- **Prod cluster:** Regular channel, training pool exclusions as above

### Version Synchronization
```bash
# Keep environments on same minor version using exclusions + manual upgrades
# All clusters on Regular channel, but training pools upgrade manually during gaps
```

## Cost Optimization

### Preemptible Infrastructure Pool
```bash
# Non-critical workloads on Spot VMs
gcloud container node-pools create infrastructure-spot \
  --cluster llm-training-cluster \
  --region us-central1 \
  --machine-type c2d-standard-8 \
  --spot \
  --num-nodes 5 \
  --enable-autoscaling \
  --min-nodes 0 \
  --max-nodes 20 \
  --node-labels workload-type=infrastructure,instance-type=spot
```

### H100 Reservation Management
```bash
# Verify reservation has no surge headroom (typical for H100)
gcloud compute reservations describe h100-reservation --zone us-central1-a
# Use maxUnavailable (drain-first) strategy since surge capacity unavailable
```

## Monitoring & Alerting

### Training-Specific Metrics
```yaml
# Custom metric for training job health
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: training-job-alerts
spec:
  groups:
  - name: training
    rules:
    - alert: TrainingJobInterrupted
      expr: rate(training_job_restarts_total[5m]) > 0
      for: 1m
      annotations:
        summary: "Training job was unexpectedly restarted"
```

### Upgrade Impact Monitoring
```bash
# Track GPU utilization during maintenance windows
gcloud monitoring dashboards create --config-from-file=gpu-training-dashboard.json
```

## Key Operational Procedures

### Before Each Training Campaign
- [ ] Apply training pool maintenance exclusion
- [ ] Verify current GKE version has 2+ months until EoS
- [ ] Check staging cluster for any GPU driver compatibility issues
- [ ] Configure PDB for zero voluntary disruptions
- [ ] Enable training job checkpointing every 6-12 hours

### During Training Campaigns
- [ ] Monitor for forced EoS upgrade notifications (72h advance warning)
- [ ] Track infrastructure pool upgrades (should continue normally)
- [ ] Review security patches accumulating on frozen training pools

### Between Training Campaigns (upgrade windows)
- [ ] Remove training pool exclusions
- [ ] Execute manual upgrades on training pools
- [ ] Validate GPU driver + CUDA compatibility
- [ ] Test training job restart procedures
- [ ] Re-apply exclusions before next campaign

## Emergency Procedures

### Forced EoS Upgrade Response
If GKE schedules a forced upgrade despite exclusions:
1. Apply 30-day "no_upgrades" exclusion immediately (buys time)
2. Accelerate current training job to checkpoint
3. Coordinate with GKE support for extension if needed
4. Execute controlled upgrade during next maintenance window

This configuration provides maximum protection for multi-week training runs while maintaining security through automated infrastructure upgrades and planned training pool maintenance windows.