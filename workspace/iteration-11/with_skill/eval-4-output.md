# GKE Control Plane Upgrade Plan: 1.31 → 1.32

## API Server Availability During Upgrade

**Good news: Regional GKE clusters have zero API server downtime during control plane upgrades.** Here's what happens:

- **Regional clusters**: Multi-master setup with automatic failover. During upgrade, masters are upgraded sequentially while others handle API requests. **Zero downtime expected.**
- **Upgrade duration**: Typically 10-15 minutes for control plane only
- **Workload impact**: None during control plane upgrade. Pods keep running, ingress keeps working
- **API access**: Continuous availability through the upgrade process

## Pre-Flight Validation

First, let's confirm your upgrade path and cluster health:

```bash
# Check current cluster version and available upgrades
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, releaseChannel.channel)"

# Verify 1.32 is available in Regular channel
gcloud container get-server-config --region us-central1 \
  --format="yaml(channels.REGULAR)"

# Check for deprecated API usage (most common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Verify cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed
```

## Control Plane Upgrade Commands

```bash
# Upgrade control plane to 1.32 (replace CLUSTER_NAME with your actual cluster)
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32

# Monitor upgrade progress
gcloud container operations list \
  --region us-central1 \
  --cluster CLUSTER_NAME \
  --filter="operationType=UPGRADE_MASTER"
```

## Validation After Upgrade

```bash
# Confirm control plane upgraded successfully
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"

# Verify system components are healthy
kubectl get pods -n kube-system
kubectl get componentstatuses

# Test API server connectivity
kubectl get nodes -o wide
```

## Safety Checklist

- [ ] **Regional cluster confirmed** ✓ (you mentioned regional)
- [ ] **Regular channel confirmed** ✓ 
- [ ] **No deprecated APIs in use** (verify with pre-flight command)
- [ ] **System monitoring active** during upgrade window
- [ ] **Upgrade performed during maintenance window** (optional but recommended)

## What About Node Pools?

**Important**: This upgrade only affects the control plane. Your node pools will remain at 1.31 until you separately upgrade them. This is normal and supported - nodes can be up to 2 minor versions behind the control plane.

Node pool upgrades involve pod disruption (unlike control plane), so plan those separately with appropriate surge settings for your workloads.

## Rollback Option

If you encounter issues post-upgrade, GKE supports **patch-level downgrades** for the control plane. Minor version downgrades (1.32 → 1.31) require GKE support involvement, so test thoroughly in staging first.

The control plane upgrade itself is very low-risk for regional clusters due to zero-downtime design. Your main concern should be application compatibility with the new Kubernetes version, which you can test beforehand.