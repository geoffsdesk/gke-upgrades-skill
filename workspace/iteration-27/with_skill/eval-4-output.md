# GKE Control Plane Upgrade: 1.31 → 1.32

## What to Expect (Regional Cluster)

**Good news: Zero API server downtime.** Regional clusters have multiple control plane replicas across zones, and GKE upgrades them one at a time. Your cluster API remains highly available throughout the entire upgrade process.

**Upgrade process:**
1. GKE upgrades one control plane replica at a time
2. Each replica is briefly unavailable during its individual upgrade (~2-5 minutes)
3. Other replicas continue serving API requests
4. Total upgrade time: ~10-15 minutes for all replicas
5. **No impact on running workloads** - pods keep running normally

This is a major advantage of regional clusters over zonal clusters (which do have brief API downtime).

## Pre-Flight Safety Checks

```bash
# 1. Verify current state and target version availability
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, releaseChannel.channel)"

gcloud container get-server-config --region us-central1 \
  --format="yaml(channels)" | grep -A 10 "regular"

# 2. Check for deprecated API usage (most common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Alternative - check GKE deprecation insights
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=us-central1 \
  --project=PROJECT_ID \
  --filter="category.category:RELIABILITY"

# 3. Verify system health
kubectl get nodes
kubectl get pods -n kube-system | grep -v Running

# 4. Check for any active maintenance exclusions
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="yaml(maintenancePolicy)"
```

## Safe Upgrade Commands

### Option 1: Manual Control (Recommended)
```bash
# Apply temporary "no upgrades" exclusion to prevent auto-upgrade during your planned window
gcloud container clusters update CLUSTER_NAME \
  --region us-central1 \
  --add-maintenance-exclusion-name "manual-cp-upgrade" \
  --add-maintenance-exclusion-start "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-end "$(date -u -d '+4 hours' +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-scope no_upgrades

# Manually trigger control plane upgrade to 1.32
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32

# Monitor progress
gcloud container operations list --region us-central1 --filter="targetLink~CLUSTER_NAME AND operationType=UPGRADE_MASTER"

# Remove exclusion after upgrade completes
gcloud container clusters update CLUSTER_NAME \
  --region us-central1 \
  --remove-maintenance-exclusion "manual-cp-upgrade"
```

### Option 2: Let Auto-Upgrade Handle It
```bash
# Simply wait for Regular channel auto-upgrade (typically within 1-2 weeks of 1.32 becoming available)
# Check current auto-upgrade target:
gcloud container clusters get-upgrade-info CLUSTER_NAME --region us-central1
```

## Validation After Upgrade

```bash
# 1. Verify control plane version
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"

# 2. Check system pod health
kubectl get pods -n kube-system
kubectl get events -n kube-system --sort-by='.lastTimestamp' | tail -10

# 3. Verify API functionality
kubectl get nodes
kubectl get deployments -A

# 4. Test basic operations
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "API working"
```

## What About Node Pools?

**Important:** This upgrade only affects the control plane. Your node pools will remain at 1.31 until you upgrade them separately. This is normal and supported - nodes can be up to 2 minor versions behind the control plane.

**Next steps for node pools:**
- You can upgrade them immediately after CP upgrade, or wait
- Plan node pool upgrade strategy (surge settings, maintenance windows)
- Node pool upgrades DO cause pod disruption (unlike CP upgrade)

## Rollback Options

**Control plane minor version rollback** requires GKE support involvement in most cases. However, GKE 1.33+ supports two-step upgrades with a rollback-safe period:

```bash
# If you want maximum safety for future upgrades, consider two-step process (available 1.33+):
gcloud beta container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.33 \
  --control-plane-soak-duration 24h  # Rollback window
```

## Recommended Approach

Given your team's concerns, I recommend **Option 1 (Manual Control)**:
1. Schedule during a low-traffic window (though downtime risk is zero)
2. Have your team monitoring during the 15-minute upgrade window  
3. Run validation steps immediately after
4. Proceed with node pool planning once CP upgrade is validated

This gives you full control over timing while taking advantage of regional cluster's zero-downtime capability.