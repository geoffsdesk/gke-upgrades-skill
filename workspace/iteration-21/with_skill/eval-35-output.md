# GKE Cluster Configuration for Foundation Model Training

## Executive Summary

For multi-week foundation model training with H100 GPUs, you need **maximum upgrade control** to prevent training interruption while maintaining security posture. This configuration protects training runs while ensuring control plane security patches flow automatically.

## Recommended Cluster Configuration

### Core Settings
```bash
gcloud container clusters create training-cluster \
    --machine-type c2-standard-60 \
    --num-nodes 3 \
    --zone us-central1-a \
    --release-channel extended \
    --maintenance-window-start "2024-01-07T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU" \
    --maintenance-patch-version-disruption-interval=7776000s \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support \
    --enable-network-policy \
    --enable-shielded-nodes \
    --disk-type pd-ssd \
    --disk-size 500GB
```

### GPU Training Node Pool
```bash
gcloud container node-pools create h100-training-pool \
    --cluster training-cluster \
    --zone us-central1-a \
    --machine-type a3-highgpu-8g \
    --accelerator type=nvidia-h100-80gb,count=8 \
    --num-nodes 8 \
    --enable-autoscaling \
    --min-nodes 0 \
    --max-nodes 32 \
    --node-locations us-central1-a \
    --placement-type COMPACT \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 1 \
    --disk-type pd-ssd \
    --disk-size 2TB \
    --enable-gvnic \
    --reservation-affinity specific \
    --reservation H100_RESERVATION_NAME
```

## Release Channel Strategy: Extended

**Why Extended channel:**
- **Up to 24 months support** (cost only during extended period)
- **No automatic minor version upgrades** - only patches auto-apply
- **Full SLA coverage** unlike Rapid channel
- **Maximum flexibility** around end-of-support enforcement
- **Manual control over disruptive changes**

Extended channel is specifically designed for workloads like yours that need predictable, controlled upgrade cycles.

## Maintenance Exclusion Strategy

### "No minor or node upgrades" exclusion (recommended)
- **Control plane patches flow automatically** for security
- **Blocks all disruptive upgrades** (minor versions + node pool changes)
- **Persistent until end-of-support** - no 30-day renewal needed
- **Prevents version skew** between control plane and nodes

```bash
# Applied in cluster creation above, or add to existing cluster:
gcloud container clusters update training-cluster \
    --zone us-central1-a \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

## GPU Node Pool Upgrade Strategy

### Fixed Reservation Strategy (most common for H100)
```bash
# For fixed GPU reservations (no surge capacity available)
--max-surge-upgrade 0 \
--max-unavailable-upgrade 1
```

**Why this configuration:**
- H100 machines typically use **fixed reservations** with no surge capacity
- `maxUnavailable=1` is the **primary lever** for GPU pools - controls upgrade speed
- **No extra GPU quota needed** - drains first, then creates replacement
- **Temporary capacity loss** during node replacement (acceptable for checkpointed training)

### Alternative: Autoscaled Blue-Green (if you have reservation headroom)
```bash
gcloud container node-pools update h100-training-pool \
    --cluster training-cluster \
    --zone us-central1-a \
    --strategy=AUTOSCALED_BLUE_GREEN \
    --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25
```

**Use autoscaled blue-green when:**
- You have reservation capacity for replacement nodes
- Training jobs exceed 8+ hours (respects longer termination grace periods)
- Cost efficiency is important (scales down old pool as new pool scales up)

## Training Workload Protection

### 1. Maintenance Exclusions During Training Campaigns
```bash
# Add temporary "no upgrades" exclusion during active training
gcloud container clusters update training-cluster \
    --zone us-central1-a \
    --add-maintenance-exclusion-name "foundation-model-training-q1" \
    --add-maintenance-exclusion-start-time "2024-01-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-02-14T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
```

### 2. Pod Disruption Budget for Training Jobs
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-job-pdb
  namespace: ml-training
spec:
  minAvailable: 100%  # Protect ALL training replicas
  selector:
    matchLabels:
      app: foundation-model-training
      job-type: training
```

### 3. Extended Termination Grace Period
```yaml
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 28800  # 8 hours - time for checkpoint save
      containers:
      - name: trainer
        image: gcr.io/PROJECT/foundation-model-trainer
        # ... rest of training container spec
```

## Multi-Week Training Operational Pattern

### Phase 1: Pre-Training Setup (Week -1)
- [ ] Apply "no upgrades" exclusion for training duration
- [ ] Verify cluster at stable versions (CP and nodes aligned)
- [ ] Test checkpoint/restore functionality
- [ ] Validate GPU interconnect (GPUDirect-TCPX if using)
- [ ] Confirm reservation capacity and placement groups

### Phase 2: Training Campaign (Weeks 1-4)
- [ ] Monitor training progress and checkpoint frequency
- [ ] Security patches still flow to control plane (unblocked)
- [ ] Node pools frozen - no disruptions
- [ ] On-call team aware of exclusion period

### Phase 3: Post-Training Maintenance (Week 5)
- [ ] Remove "no upgrades" exclusion
- [ ] Plan catch-up upgrades during training gaps
- [ ] Update training images to work with newer node versions
- [ ] Validate next training run compatibility

## Security and Compliance Posture

This configuration maintains strong security:

✅ **Control plane security patches** flow automatically  
✅ **Node security** protected by GKE's security hardening  
✅ **Shielded nodes** enabled for additional protection  
✅ **Network policies** enabled for workload isolation  
✅ **Extended support** provides security fixes for up to 24 months  

The security trade-off is **node-level patches delayed** during training campaigns, but this is acceptable for time-bounded ML workloads with proper operational controls.

## Cost Optimization Notes

### Extended Channel Costs
- **No extra cost** during standard 14-month support period
- **Additional cost** only applies during months 15-24 of extended support
- **Savings** from avoiding training re-runs far exceed extended support costs

### Resource Optimization
```bash
# Scale down to 0 between training runs
kubectl scale deployment foundation-model-trainer --replicas=0

# Or use node auto-scaling to min-nodes=0
gcloud container node-pools update h100-training-pool \
    --min-nodes 0 --max-nodes 32
```

## Monitoring and Alerting Setup

### Critical Alerts
```yaml
# Example Cloud Monitoring alert policy
displayName: "GKE Training Cluster Upgrade Events"
conditions:
  - displayName: "Unexpected upgrade started"
    conditionThreshold:
      filter: 'resource.type="gke_cluster" AND protoPayload.methodName="container.clusters.update"'
      comparison: COMPARISON_GT
      thresholdValue: 0
```

### Scheduled Upgrade Notifications
```bash
# Enable 72-hour advance notifications (preview)
gcloud container clusters update training-cluster \
    --zone us-central1-a \
    --send-scheduled-upgrade-notifications
```

## Validation Checklist

- [ ] Extended release channel configured
- [ ] "No minor or node upgrades" exclusion active and persistent
- [ ] Maintenance window set to Sunday 2-6 AM (low-traffic period)
- [ ] Patch disruption interval set to 90 days maximum
- [ ] GPU node pool using maxUnavailable=1 (no surge capacity assumed)
- [ ] H100 reservation properly configured and verified
- [ ] Training workload PDBs configured for full protection
- [ ] Checkpoint/restore tested and working
- [ ] Monitoring alerts configured for unexpected upgrade events
- [ ] Scheduled upgrade notifications enabled for 72-hour advance warning

## Troubleshooting Training Job Eviction

If training jobs get evicted despite protections:

### 1. Check PDB Status
```bash
kubectl get pdb -n ml-training
kubectl describe pdb training-job-pdb -n ml-training
```

### 2. Verify Maintenance Exclusions
```bash
gcloud container clusters describe training-cluster \
    --zone us-central1-a \
    --format="yaml(maintenancePolicy.window,maintenancePolicy.exclusions)"
```

### 3. Emergency Training Protection
```bash
# Immediate "no upgrades" exclusion if training starts unexpectedly
gcloud container clusters update training-cluster \
    --zone us-central1-a \
    --add-maintenance-exclusion-name "emergency-training-protection" \
    --add-maintenance-exclusion-start-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --add-maintenance-exclusion-end-time "$(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ)" \
    --add-maintenance-exclusion-scope no_upgrades
```

This configuration provides **maximum protection for multi-week training runs** while maintaining **security posture** through automated control plane patching. The Extended release channel + persistent maintenance exclusions give you complete control over when disruptive changes happen, allowing you to schedule them between training campaigns.