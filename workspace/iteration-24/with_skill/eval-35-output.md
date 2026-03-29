# GKE Cluster Configuration for Foundation Model Training

## Cluster Configuration for Multi-Week Training Protection

### Core Configuration
```bash
# Create cluster with Extended channel for maximum upgrade control
gcloud container clusters create foundation-training \
  --zone us-central1-a \
  --machine-type n1-standard-4 \
  --num-nodes 3 \
  --release-channel extended \
  --enable-network-policy \
  --enable-ip-alias \
  --cluster-version 1.31.3-gke.1535000 \
  --maintenance-window-start "2024-12-01T03:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU" \
  --maintenance-patch-version-disruption-interval=2592000s \
  --maintenance-minor-version-disruption-interval=7776000s \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

### GPU Training Node Pool
```bash
# Dedicated H100 training pool with upgrade protection
gcloud container node-pools create h100-training \
  --cluster foundation-training \
  --zone us-central1-a \
  --machine-type a3-highgpu-8g \
  --accelerator type=nvidia-h100-80gb,count=8 \
  --num-nodes 8 \
  --node-locations us-central1-a \
  --enable-autoscaling \
  --max-nodes 32 \
  --min-nodes 0 \
  --disk-size 1000GB \
  --disk-type pd-ssd \
  --placement-type COMPACT \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

## Release Channel Strategy: Extended Channel

**Why Extended for training clusters:**
- **24 months of support** vs 14 months on other channels
- **NO automatic minor version upgrades** — you control when minor upgrades happen
- **Only patches are auto-applied** — critical security updates continue
- **Full SLA coverage** — production-grade support
- **Cost**: Additional charges only apply during extended support period (months 15-24)

**Key insight:** Extended channel gives you maximum control over disruptive changes while maintaining security posture — exactly what multi-week training runs need.

## Maintenance Settings Configuration

### Maintenance Exclusions (Primary Protection)
```bash
# "No minor or node upgrades" exclusion - CRITICAL for training protection
gcloud container clusters update foundation-training \
  --zone us-central1-a \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**What this blocks:**
- ✅ **Minor version upgrades** (e.g., 1.31 → 1.32)
- ✅ **Node pool upgrades** (both minor and patch)
- ❌ **Control plane patches** still auto-apply (security updates)

### Disruption Intervals (Secondary Protection)
```bash
# Enforce 30-day gaps between control plane patches, 90-day gaps for any minor upgrades
gcloud container clusters update foundation-training \
  --zone us-central1-a \
  --maintenance-patch-version-disruption-interval=2592000s \
  --maintenance-minor-version-disruption-interval=7776000s
```

### Maintenance Windows
```bash
# Sunday 3-7 AM UTC maintenance window
gcloud container clusters update foundation-training \
  --zone us-central1-a \
  --maintenance-window-start "2024-12-01T03:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```

## Node Pool Upgrade Strategy

### GPU Pool Settings (H100 Training Pool)
```bash
# GPU pools: maxUnavailable is the PRIMARY lever (no surge capacity available)
gcloud container node-pools update h100-training \
  --cluster foundation-training \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

**Why these settings:**
- `maxSurge=0`: H100 reservations are fixed — no surge capacity available
- `maxUnavailable=1`: Conservative drain-first approach, minimal disruption
- **Upgrade time**: 32-node pool = ~32 sequential upgrades at current parallelism (~20 batch limit)

### Training Job Protection with PDBs
```yaml
# PDB for training workloads
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
spec:
  minAvailable: 7  # Keep 7/8 training pods running during maintenance
  selector:
    matchLabels:
      app: foundation-training
```

## Operational Workflow for Training Campaigns

### Before Starting Multi-Week Training
```bash
# 1. Verify exclusion is active
gcloud container clusters describe foundation-training \
  --zone us-central1-a \
  --format="yaml(maintenancePolicy)"

# 2. Check no pending upgrades
gcloud container clusters get-upgrade-info foundation-training \
  --zone us-central1-a

# 3. Checkpoint capability verification
kubectl describe pod TRAINING_POD | grep -A 5 "terminationGracePeriodSeconds"
```

### During Training (Emergency Upgrades)
```bash
# If urgent security patch needed during training:
# 1. Apply temporary "no upgrades" exclusion (blocks even patches)
gcloud container clusters update foundation-training \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "training-campaign-dec2024" \
  --add-maintenance-exclusion-start-time "2024-12-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# 2. After training completes, remove exclusion to resume patches
gcloud container clusters update foundation-training \
  --zone us-central1-a \
  --remove-maintenance-exclusion-name "training-campaign-dec2024"
```

### Between Training Campaigns (Upgrade Window)
```bash
# When training campaign ends:
# 1. Check for available updates
gcloud container clusters get-upgrade-info foundation-training \
  --zone us-central1-a

# 2. Upgrade control plane if needed (minor versions - manual trigger required on Extended)
gcloud container clusters upgrade foundation-training \
  --zone us-central1-a \
  --master \
  --cluster-version TARGET_VERSION

# 3. Upgrade training node pool (during downtime between campaigns)
gcloud container node-pools upgrade h100-training \
  --cluster foundation-training \
  --zone us-central1-a \
  --cluster-version TARGET_VERSION
```

## Multi-Cluster Architecture Recommendation

For production foundation model training, consider this topology:

### Cluster Separation
```bash
# Staging cluster (Regular channel, faster updates)
gcloud container clusters create foundation-staging \
  --release-channel regular \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=TU"

# Production training cluster (Extended channel, maximum protection)  
gcloud container clusters create foundation-production \
  --release-channel extended \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Rollout sequence:**
1. Test new GKE versions in staging first
2. Validate GPU driver compatibility, CUDA versions
3. Manually upgrade production during planned maintenance windows
4. Never auto-upgrade production during active training

## Security Posture with Upgrade Protection

### What You Still Get (Security Maintained)
- ✅ **Control plane security patches** auto-applied
- ✅ **72-hour advance notifications** for planned updates
- ✅ **GKE security bulletins** and CVE fixes on control plane
- ✅ **24 months of support** on Extended channel

### What You Control (Disruption Avoided)
- ❌ **No automatic minor version upgrades** (1.31 → 1.32)
- ❌ **No automatic node pool upgrades** (GPU driver changes)
- ❌ **No surprise breaking changes** during training
- ❌ **No forced eviction** of multi-day jobs

### Monitoring and Alerting Setup
```bash
# Enable scheduled upgrade notifications (72h advance warning)
gcloud container clusters update foundation-training \
  --zone us-central1-a \
  --send-scheduled-upgrade-notifications

# Cloud Logging query for upgrade events
resource.type="gke_cluster"
protoPayload.metadata.operationType=~"(UPDATE_CLUSTER|UPGRADE_MASTER)"
```

## Pre-Training Checklist

```markdown
Foundation Model Training - Pre-Campaign Checklist

Cluster Protection Verified
- [ ] Extended release channel confirmed
- [ ] "No minor or node upgrades" exclusion active until EoS
- [ ] Disruption intervals set (30d patches, 90d minor)
- [ ] Sunday 3-7 AM maintenance window configured
- [ ] No pending auto-upgrades: `gcloud container clusters get-upgrade-info`

Training Infrastructure Ready
- [ ] H100 node pool: maxSurge=0, maxUnavailable=1
- [ ] PDB configured for training workloads
- [ ] Compact placement verified for RDMA topology
- [ ] GPU driver version tested with training framework
- [ ] Checkpoint/resume functionality validated
- [ ] terminationGracePeriodSeconds ≥ checkpoint interval

Monitoring and Alerts
- [ ] Scheduled upgrade notifications enabled
- [ ] Cloud Logging alerts for cluster events
- [ ] Node health monitoring active
- [ ] Training job progress monitoring configured

Multi-Week Training Campaign: READY TO START
```

This configuration gives you **maximum protection for multi-week training runs** while maintaining security through control plane patches. The Extended channel + "no minor or node upgrades" exclusion is the gold standard for training workloads that cannot tolerate disruption.