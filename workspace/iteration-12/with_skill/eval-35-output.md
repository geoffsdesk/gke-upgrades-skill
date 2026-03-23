# GKE Configuration for Foundation Model Training

## Executive Summary

For multi-week H100 training runs, your primary goal is **preventing mid-training evictions** while maintaining security patches. This requires a dual-strategy approach: aggressive upgrade control during training campaigns, plus streamlined upgrade paths during natural training gaps.

## Recommended Cluster Configuration

### Release Channel Strategy
```bash
# Use Regular channel (not Stable) - provides better security patch velocity
gcloud container clusters create training-cluster \
  --release-channel regular \
  --zone us-central1-c \
  --enable-autorepair \
  --enable-autoupgrade
```

**Why Regular over Stable:** Foundation model training clusters need security patches more frequently than the Stable channel provides, but don't need the bleeding-edge features of Rapid. Regular strikes the right balance for production AI workloads with full SLA coverage.

### Node Pool Architecture - Separation of Concerns

Create **separate node pools** for different workload types:

```bash
# Training node pool (H100s) - tight upgrade control
gcloud container node-pools create training-h100 \
  --cluster training-cluster \
  --zone us-central1-c \
  --machine-type a3-highgpu-8g \
  --accelerator type=nvidia-h100-80gb,count=8 \
  --num-nodes 16 \
  --node-locations us-central1-c \
  --placement-type COMPACT \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1 \
  --enable-autorepair \
  --disk-size 1000GB \
  --disk-type pd-ssd

# System/monitoring node pool (CPU) - allow auto-upgrades
gcloud container node-pools create system-cpu \
  --cluster training-cluster \
  --zone us-central1-c \
  --machine-type n2-standard-8 \
  --num-nodes 3 \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0 \
  --enable-autorepair
```

**Key decisions:**
- **Compact placement:** Preserves RDMA topology for H100 interconnect
- **maxSurge=0, maxUnavailable=1:** Assumes no H100 surge capacity available (typical with reservations)
- **Separate pools:** System workloads can upgrade independently of training nodes

### Maintenance Window Configuration

```bash
# Set maintenance window during your natural training gaps
gcloud container clusters update training-cluster \
  --zone us-central1-c \
  --maintenance-window-start 2024-12-15T06:00:00Z \
  --maintenance-window-end 2024-12-15T10:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```

Configure this to align with your training schedule - when you typically restart/checkpoint jobs.

## Training Campaign Protection Strategy

### During Active Training (Multi-Week Runs)

Apply **cluster-level maintenance exclusion** to block ALL disruptive upgrades:

```bash
# Block minor version upgrades AND node pool upgrades, allow control plane patches
gcloud container clusters update training-cluster \
  --zone us-central1-c \
  --add-maintenance-exclusion-name "training-campaign-q1-2024" \
  --add-maintenance-exclusion-start-time 2024-03-01T00:00:00Z \
  --add-maintenance-exclusion-end-time 2024-04-15T23:59:59Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**This exclusion:**
- ✅ Allows control plane security patches (non-disruptive)
- ❌ Blocks control plane minor version upgrades
- ❌ Blocks ALL node pool upgrades (patches + minor versions)
- Automatically expires when training campaign ends

### Between Training Campaigns (Upgrade Windows)

Remove the exclusion and perform accelerated upgrades:

```bash
# Remove training protection
gcloud container clusters update training-cluster \
  --zone us-central1-c \
  --remove-maintenance-exclusion-name "training-campaign-q1-2024"

# Optionally trigger immediate upgrade to latest available
gcloud container clusters upgrade training-cluster \
  --zone us-central1-c \
  --master

# Then upgrade H100 node pool
gcloud container node-pools upgrade training-h100 \
  --cluster training-cluster \
  --zone us-central1-c
```

## H100-Specific Node Pool Strategy

### GPU Node Pool Upgrade Approach

For H100 pools, use the **cordon-and-wait pattern** during planned upgrades:

```bash
# 1. Cordon H100 nodes (prevents new scheduling)
kubectl cordon -l cloud.google.com/gke-nodepool=training-h100

# 2. Wait for current training jobs to complete naturally or reach checkpoint

# 3. Upgrade the empty node pool (fast since no running workloads)
gcloud container node-pools upgrade training-h100 \
  --cluster training-cluster \
  --zone us-central1-c

# 4. Uncordon when upgrade completes
kubectl uncordon -l cloud.google.com/gke-nodepool=training-h100
```

**Why this approach:**
- **No forced eviction** of multi-day training jobs
- **Minimal capacity loss** during the transition period
- **Fast upgrade** since nodes drain cleanly
- **GPU driver compatibility** automatically handled by GKE

### Alternative: Autoscaled Blue-Green for H100

If you have sufficient H100 quota/reservations for 2x capacity:

```bash
gcloud container node-pools update training-h100 \
  --cluster training-cluster \
  --zone us-central1-c \
  --enable-blue-green-upgrade \
  --node-pool-soak-duration 7200s \
  --standard-rollout-policy-max-unavailable-percentage 0 \
  --standard-rollout-policy-max-surge-percentage 100
```

This creates a parallel H100 pool, gradually migrates workloads, then removes the old pool. **Only use if you have confirmed H100 surge capacity.**

## Workload Protection Configuration

### Pod Disruption Budgets for Training Jobs

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-job-pdb
  namespace: training
spec:
  minAvailable: 100%  # Prevent ANY pod eviction
  selector:
    matchLabels:
      workload-type: training
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: llm-training
  namespace: training
spec:
  replicas: 16  # Match your H100 node count
  selector:
    matchLabels:
      workload-type: training
  template:
    metadata:
      labels:
        workload-type: training
    spec:
      terminationGracePeriodSeconds: 3600  # 1 hour for graceful checkpoint
      nodeSelector:
        cloud.google.com/gke-nodepool: training-h100
      containers:
      - name: training
        image: your-training-image
        resources:
          requests:
            nvidia.com/gpu: 8
          limits:
            nvidia.com/gpu: 8
```

### Checkpointing Strategy

Ensure your training framework supports:
- **Automatic checkpointing** every few hours
- **SIGTERM handling** for graceful shutdown
- **Resume from checkpoint** capability

## Operational Runbook

### Pre-Training Campaign Checklist

```
- [ ] Maintenance exclusion applied for campaign duration
- [ ] Training node pool cordoned if upgrading before campaign
- [ ] GPU driver version confirmed compatible with training framework
- [ ] Checkpointing tested and working
- [ ] PDBs configured to prevent eviction
- [ ] Monitoring alerts configured for node health
```

### Training Campaign Commands

```bash
# Apply protection (start of campaign)
gcloud container clusters update training-cluster \
  --zone us-central1-c \
  --add-maintenance-exclusion-name "training-campaign-$(date +%Y%m%d)" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d "+30 days" +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Monitor cluster health during training
kubectl get nodes -l cloud.google.com/gke-nodepool=training-h100
kubectl get pods -n training -o wide

# Remove protection (end of campaign)
gcloud container clusters update training-cluster \
  --zone us-central1-c \
  --remove-maintenance-exclusion-name "training-campaign-$(date +%Y%m%d)"
```

### Emergency Upgrade (Security Patches During Training)

If a critical security patch requires immediate node upgrade during training:

```bash
# 1. Trigger checkpoint immediately in training code
# 2. Cordon nodes
kubectl cordon -l cloud.google.com/gke-nodepool=training-h100

# 3. Wait for graceful job termination
kubectl delete pods -n training -l workload-type=training --grace-period=3600

# 4. Force upgrade
gcloud container node-pools upgrade training-h100 \
  --cluster training-cluster \
  --zone us-central1-c

# 5. Resume training from checkpoint
```

## Security vs Availability Trade-offs

This configuration prioritizes **training job continuity** over **immediate patching**:

- ✅ **Control plane** gets security patches automatically (non-disruptive)
- ⚠️ **Node patches** are delayed during training campaigns
- ✅ **Systematic upgrades** happen between campaigns
- ✅ **Emergency path** available for critical vulnerabilities

For most foundation model training scenarios, this is the right balance. The control plane receives security updates, and node vulnerabilities have limited attack surface in a dedicated training environment.

## Monitoring and Alerts

Set up alerts for:
- Node health degradation during training
- Automatic repair events (may disrupt training)
- Approaching End of Support versions
- Training job failures due to node issues

This configuration gives you **maximum protection for multi-week training runs** while maintaining **security patch velocity** on the control plane and **streamlined upgrade paths** during natural training gaps.