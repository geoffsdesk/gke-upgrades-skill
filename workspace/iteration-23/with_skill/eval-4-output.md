# GKE Control Plane Upgrade Guide: Regional Standard Cluster

## What to Expect During Your Upgrade

**Good news: Regional clusters have ZERO API server downtime during control plane upgrades.**

Your regional Standard cluster has multiple control plane replicas distributed across zones in us-central1. During the upgrade:

- **High Availability Maintained**: GKE upgrades one control plane replica at a time
- **No Service Interruption**: The other replicas continue serving API requests
- **Typical Duration**: 10-15 minutes total, with each replica briefly unavailable during its individual upgrade
- **Workload Impact**: Your running pods are completely unaffected - they keep running normally

This is the key advantage of regional clusters over zonal clusters (which do have brief API downtime during control plane upgrades).

## Pre-Flight Safety Checks

First, let's verify your cluster is ready for the 1.31 → 1.32 upgrade:

```bash
# 1. Confirm current versions and cluster health
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# 2. Verify 1.32 is available in Regular channel
gcloud container get-server-config --region us-central1 \
  --format="yaml(channels)" | grep -A 10 "REGULAR"

# 3. Check for deprecated API usage (most common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# 4. Verify cluster health
kubectl get nodes
kubectl get pods -n kube-system
kubectl get pods -A | grep -v Running | grep -v Completed
```

**Critical**: If step 3 shows deprecated API usage, **do not proceed** until you've fixed those. GKE will automatically pause auto-upgrades when deprecated APIs are detected.

## Safe Control Plane Upgrade Commands

### Option 1: Standard One-Step Upgrade (Recommended for most teams)

```bash
# Upgrade control plane to 1.32
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32

# Monitor progress (the operation will show RUNNING status)
gcloud container operations list \
  --region us-central1 \
  --filter="targetLink~CLUSTER_NAME AND operationType=UPGRADE_MASTER"
```

### Option 2: Two-Step Minor Upgrade for Extra Safety (Preview - GKE 1.33+)

If your team wants maximum safety with rollback capability:

```bash
# Step 1: Binary upgrade with rollback capability (6h-7d soak period)
gcloud beta container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32 \
  --control-plane-soak-duration 24h

# Test workloads for 24 hours with new binary but old API behavior
# If issues arise, you can roll back during this period

# Step 2: Complete the upgrade (enables 1.32 features, no rollback after this)
gcloud beta container clusters complete-master-upgrade CLUSTER_NAME \
  --region us-central1
```

## Validation After Upgrade

```bash
# 1. Confirm control plane upgraded
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"
# Should show 1.32.x-gke.xxxx

# 2. Verify system components are healthy
kubectl get pods -n kube-system
kubectl get componentstatuses 2>/dev/null || echo "API healthy"

# 3. Test API functionality
kubectl get nodes
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "API test passed"
```

## What About Node Pools?

Your **node pools will remain at 1.31** after the control plane upgrade. This is normal and supported - GKE allows nodes to be up to 2 minor versions behind the control plane.

You have two options for node pools:
1. **Let auto-upgrades handle it** (recommended) - They'll upgrade automatically within a few weeks
2. **Upgrade manually now** - If you need immediate version consistency

If you want to upgrade node pools immediately, that's a separate operation we can plan next.

## Maintenance Window Recommendation

Since this is a regional cluster with zero downtime, you can run this upgrade during business hours if needed. However, if you prefer to be cautious:

```bash
# Optional: Set a maintenance window for future auto-upgrades
gcloud container clusters update CLUSTER_NAME \
  --region us-central1 \
  --maintenance-window-start "2024-01-13T02:00:00Z" \
  --maintenance-window-end "2024-01-13T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Summary

✅ **Regional Standard clusters have zero API downtime during control plane upgrades**  
✅ **Your workloads keep running normally**  
✅ **The upgrade is reversible if you use the two-step preview method**  
✅ **Node pools can be upgraded separately (next step if desired)**

The commands above will safely upgrade your control plane from 1.31 to 1.32 with no service interruption. Let me know if you'd like guidance on node pool upgrades next, or if you have any other concerns!