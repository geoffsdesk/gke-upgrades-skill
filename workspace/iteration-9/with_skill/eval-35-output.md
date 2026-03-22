# GKE Configuration for Foundation Model Training with H100 GPUs

## Executive Summary

For multi-week H100 training runs, your primary concern is **preventing forced disruption during training campaigns**. This requires a defensive configuration that blocks disruptive upgrades while maintaining security patches. The key strategy is using **maintenance exclusions** to create training-safe windows and **dedicated training node pools** with tight upgrade control.

## Recommended Cluster Configuration

### Release Channel Strategy
```bash
# Use Regular channel (NOT Rapid)
gcloud container clusters create CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular \
  --cluster-version LATEST_REGULAR_VERSION
```

**Why Regular over Stable/Extended:**
- **Regular**: Good balance of stability and security patches (~2-4 week delay after Rapid)
- **Avoid Rapid**: No SLA for upgrade stability, too bleeding-edge for production training
- **Stable consideration**: 2-3 month delay may leave you vulnerable to security issues
- **Extended channel**: Overkill unless you have compliance requirements. Manual minor upgrades add operational overhead.

### Node Pool Architecture

Create **separate node pools** for training vs. infrastructure:

```bash
# Training node pool - tight control
gcloud container node-pools create training-h100 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --machine-type a3-highgpu-8g \
  --accelerator type=nvidia-h100-80gb,count=8 \
  --num-nodes 64 \
  --node-version CURRENT_VERSION \
  --enable-autorepair \
  --enable-autoupgrade=false \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1 \
  --placement-type COMPACT \
  --placement-policy-name training-placement

# Infrastructure node pool - auto-upgrades OK
gcloud container node-pools create system \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --machine-type c2-standard-4 \
  --num-nodes 3 \
  --enable-autoupgrade \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Key decisions:**
- **Training pool**: Auto-upgrades DISABLED (`--enable-autoupgrade=false`)
- **Infrastructure pool**: Auto-upgrades ENABLED for security patches
- **Compact placement**: Preserves RDMA topology for multi-node training
- **maxUnavailable=1 for GPU**: H100 reservations rarely have surge capacity

### Maintenance Windows & Exclusions

Set up **predictable maintenance windows** aligned with training schedules:

```bash
# Maintenance window during planned training gaps (e.g., Sunday 2-6 AM PST)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-07T10:00:00Z" \
  --maintenance-window-end "2024-01-07T14:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"

# Default exclusion: allow CP patches, block disruptive changes
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Exclusion strategy:**
- **"no_minor_or_node_upgrades"**: Blocks disruptive changes, allows CP security patches
- **"until-end-of-support"**: Auto-renews until version reaches EoS (~14 months)
- **Emergency override**: Can add 30-day "no_upgrades" exclusion for critical training runs

### Cluster-Level Settings

```bash
# Configure disruption intervals (reduce upgrade frequency)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-patch-version-disruption-interval 30d \
  --maintenance-minor-version-disruption-interval 90d

# Enable scheduled upgrade notifications (72h advance warning)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --enable-notification-config
```

## Operational Procedures

### Pre-Training Checklist

Before starting multi-week training runs:

```
Training Campaign Preparation
- [ ] Current GKE version reviewed for upcoming EoS (~14 months out)
- [ ] Training node pool auto-upgrades confirmed DISABLED
- [ ] "no_minor_or_node_upgrades" exclusion active and tracking EoS
- [ ] Emergency "no_upgrades" exclusion ready to deploy if needed:
      gcloud container clusters update CLUSTER_NAME --zone ZONE \
        --add-maintenance-exclusion-name "emergency-freeze" \
        --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
        --add-maintenance-exclusion-end-time $(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ) \
        --add-maintenance-exclusion-scope no_upgrades
- [ ] Checkpoint mechanism verified and tested
- [ ] H100 driver version confirmed compatible: `nvidia-smi`
- [ ] RDMA/GPUDirect-TCPX validated: `kubectl get nodes -o custom-columns=NAME:.metadata.name,RDMA:.metadata.labels.cloud\.google\.com/gke-accelerator`
```

### Planned Upgrade Windows

Schedule upgrades during natural training gaps:

```bash
# During training gaps, temporarily enable auto-upgrades
gcloud container node-pools update training-h100 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoupgrade

# Or manually upgrade training nodes during planned windows
gcloud container node-pools upgrade training-h100 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

### GPU-Specific Upgrade Strategy

For H100 pools, use **drain-then-upgrade** approach:

```bash
# Step 1: Cordon training nodes
kubectl cordon -l cloud.google.com/gke-nodepool=training-h100

# Step 2: Wait for current training job to checkpoint/complete naturally
# (Don't force-drain running training pods)

# Step 3: Upgrade empty pool
gcloud container node-pools upgrade training-h100 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION

# Step 4: Verify H100 drivers and RDMA after upgrade
kubectl create job gpu-validation --image=nvidia/cuda:12.3-devel-ubuntu20.04 \
  --dry-run=client -o yaml | kubectl apply -f -
```

## Security & Compliance Balance

This configuration balances training protection with security:

✅ **Security maintained:**
- Control plane gets security patches automatically
- Infrastructure nodes stay current
- Can emergency-upgrade if critical CVE discovered

✅ **Training protected:**
- Node pool upgrades blocked during campaigns
- No surprise H100 driver changes
- RDMA topology preserved

✅ **Operational flexibility:**
- Can manually upgrade training nodes during gaps
- Emergency exclusions available for critical runs
- Clear procedures for planned maintenance

## Alternative: Extended Channel for Maximum Control

If you need **maximum flexibility** around version upgrades:

```bash
# Extended channel - manual minor upgrades required
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

**Extended channel considerations:**
- Minor upgrades are NOT automated (except at end of extended support)
- Up to 24 months support for versions 1.27+
- Extra cost during extended period (months 15-24)
- Requires internal processes for planning minor upgrades

Use Extended if your training campaigns are measured in quarters, not weeks.

## Monitoring & Alerting

Set up alerts for upgrade-related events:

```bash
# Cloud Logging alert for forced upgrade notifications
# Filter: resource.type="gke_cluster" AND jsonPayload.reason="NodeUpgrade"

# Custom metric for training job interruption
# Monitor: kubectl get pods -l app=foundation-training --field-selector=status.phase=Failed
```

## Summary

**Recommended configuration for H100 foundation model training:**

1. **Regular release channel** - balanced stability and security
2. **Dedicated training node pool** with auto-upgrades disabled
3. **"no_minor_or_node_upgrades" exclusion** tracking EoS
4. **Weekly maintenance window** aligned with training schedules
5. **Manual upgrade procedures** during natural training gaps

This setup gives you **maximum control over disruption timing** while maintaining security through control plane patches. Training campaigns can run for weeks without forced interruption, and you retain the flexibility to upgrade during planned windows.