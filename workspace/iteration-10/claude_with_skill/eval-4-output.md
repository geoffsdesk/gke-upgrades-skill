# GKE Control Plane Upgrade: 1.31 → 1.32

## Control Plane Availability During Upgrade

**Good news: No API server downtime.** Regional GKE clusters run **multiple control plane replicas across zones** with a load balancer. During upgrades:

- One replica upgrades at a time while others serve traffic
- API server remains available throughout the entire process  
- Only brief (<1 second) connection interruptions as load balancer shifts traffic
- `kubectl` commands continue working normally
- Workloads are completely unaffected (nodes don't change during control plane upgrade)

**Duration:** Typically 10-15 minutes for the full control plane upgrade.

## Pre-flight Checklist

```bash
# Verify current versions and channel
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, releaseChannel.channel)"

# Confirm 1.32 is available in Regular channel
gcloud container get-server-config --region us-central1 \
  --format="yaml(channels.REGULAR)"

# Check for deprecated API usage (most common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Verify cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed
kubectl get pods -n kube-system
```

## Safe Upgrade Commands

```bash
# 1. Upgrade control plane only (--master flag)
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32

# You'll get a confirmation prompt showing:
# - Current version: 1.31.x-gke.xxxx  
# - Target version: 1.32.x-gke.xxxx
# - "This will upgrade only the master" confirmation

# 2. Monitor progress (optional)
gcloud container operations list --region us-central1 \
  --filter="clusterName=CLUSTER_NAME AND operationType=UPGRADE_MASTER"
```

## Validation Commands

```bash
# Verify control plane upgraded successfully
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"
# Should show: 1.32.x-gke.xxxx

# Confirm API server responding normally  
kubectl get pods -n kube-system
kubectl get nodes
kubectl version --short
# Server version should show 1.32.x

# Check system pods adapted to new control plane
kubectl get pods -n kube-system | grep -v Running
# Should be empty or only brief ContainerCreating
```

## What Happens to Your Nodes

- **Nodes stay at 1.31** — they are NOT upgraded automatically
- **Version skew is supported** — 1.31 nodes work fine with 1.32 control plane  
- **When you're ready:** Upgrade node pools separately using `gcloud container node-pools upgrade`
- **Skip-level supported:** You can upgrade nodes directly from 1.31 → 1.32 (or even 1.31 → 1.33 later)

## Risk Mitigation

Since you're concerned about safety:

```bash
# Optional: Set a maintenance window first (upgrades will respect it)
gcloud container clusters update CLUSTER_NAME \
  --region us-central1 \
  --maintenance-window-start 2024-01-06T02:00:00Z \
  --maintenance-window-end 2024-01-06T06:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Optional: Add a maintenance exclusion if you need to postpone
gcloud container clusters update CLUSTER_NAME \
  --region us-central1 \
  --add-maintenance-exclusion-name "planned-maintenance" \
  --add-maintenance-exclusion-start-time 2024-01-01T00:00:00Z \
  --add-maintenance-exclusion-end-time 2024-01-15T00:00:00Z \
  --add-maintenance-exclusion-scope no_minor_upgrades
```

## Summary

This is a **low-risk operation**. The 1.31 → 1.32 control plane upgrade:
- ✅ No API server downtime (regional cluster advantage)
- ✅ No workload impact  
- ✅ Nodes continue running 1.31 normally
- ✅ Can be done during business hours
- ✅ ~15 minute duration

Your biggest risk is deprecated API usage, which the pre-flight check will catch. The upgrade itself is seamless for regional clusters.