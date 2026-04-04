# GKE Control Plane Upgrade: Regional Cluster (No Downtime)

## What Will Happen During Your Upgrade

**Good news: Regional clusters have NO API server downtime during control plane upgrades.**

Your regional Standard cluster has multiple control plane replicas distributed across zones in us-central1. During the upgrade:

1. **High Availability Maintained**: GKE upgrades one control plane replica at a time
2. **API Server Always Available**: While one replica upgrades (~5-10 minutes), the others continue serving API requests
3. **No Workload Impact**: Your pods keep running normally throughout the process
4. **Total Duration**: ~15-20 minutes for all replicas to upgrade sequentially

This is fundamentally different from zonal clusters, which do experience brief API downtime during control plane upgrades.

## Pre-Flight Safety Checks

```bash
# Verify current state and target availability
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, releaseChannel.channel)"

# Confirm 1.32 is available in Regular channel
gcloud container get-server-config --region us-central1 \
  --format="yaml(channels.REGULAR.validVersions)" | grep "1\.32"

# Check for deprecated API usage (most common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Also check GKE deprecation insights
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=us-central1 \
  --project=PROJECT_ID \
  --filter="category.category:RELIABILITY"

# Verify cluster health
kubectl get nodes
kubectl get pods -n kube-system
kubectl get pods -A | grep -v Running | grep -v Completed
```

## Safe Upgrade Commands

### Option 1: Standard One-Step Upgrade (Recommended)
```bash
# Direct upgrade to 1.32 (no rollback after completion)
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32

# Monitor progress (upgrade status will show)
gcloud container operations list \
  --region us-central1 \
  --filter="targetLink~CLUSTER_NAME AND operationType=UPGRADE_MASTER"
```

### Option 2: Two-Step Rollback-Safe Upgrade (Extra Cautious)
For maximum safety with rollback option:

```bash
# Step 1: Binary upgrade (rollback possible for 6h-7d)
gcloud beta container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32 \
  --control-plane-soak-duration 24h

# Test your applications for 24 hours...
# If issues arise, you can roll back:
# gcloud container clusters upgrade CLUSTER_NAME --region us-central1 --master --cluster-version 1.31

# Step 2: Complete the upgrade (no rollback after this)
gcloud beta container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32 \
  --emulated-version-upgrade
```

## Validation Steps

```bash
# Verify control plane upgraded successfully
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"

# Check system component health
kubectl get pods -n kube-system
kubectl get events -n kube-system --sort-by='.lastTimestamp' | tail -10

# Verify API server responsiveness
kubectl get nodes
time kubectl get pods -A | head -5
```

## What to Monitor During Upgrade

1. **API Responsiveness**: Run occasional `kubectl` commands to verify API access
2. **System Pods**: Watch `kubectl get pods -n kube-system` for any restarts
3. **Application Health**: Your monitoring should show no impact on workloads
4. **GKE Operations**: Track progress with the operations list command above

## Important Notes

- **Node pools remain at 1.31** after this upgrade - they don't auto-upgrade with the control plane
- **Version skew is fine** - nodes can run up to 2 minor versions behind the control plane
- **No maintenance window needed** for control plane upgrades on regional clusters
- **Auto-upgrades bypass maintenance exclusions** - this manual upgrade will proceed regardless of any active exclusions

## Next Steps After Control Plane Upgrade

Once your control plane is successfully at 1.32, you can plan your node pool upgrades separately. Node pools can stay at 1.31 indefinitely (within the 2-minor-version skew policy) or be upgraded to 1.32 when convenient.

Your regional cluster architecture gives you the best of both worlds: zero-downtime control plane upgrades and flexible node pool upgrade timing.