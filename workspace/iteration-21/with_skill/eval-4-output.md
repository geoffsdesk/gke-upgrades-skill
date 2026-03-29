# Regional Standard GKE Control Plane Upgrade: 1.31 → 1.32

Good news: **Regional clusters have no API server downtime during control plane upgrades.** Your cluster has multiple control plane replicas across zones, and GKE upgrades them one at a time while keeping the others serving traffic.

## What happens during the upgrade

**Regional cluster behavior:**
- Multiple control plane replicas (typically 3) across us-central1-a, us-central1-b, us-central1-c
- GKE upgrades one replica at a time
- The other replicas continue serving API requests
- **No downtime for kubectl, deployments, or cluster management**
- Upgrade typically completes in 10-15 minutes

**During the upgrade you CAN:**
- Deploy new workloads
- Scale existing workloads  
- Run kubectl commands
- Access the Kubernetes API normally

## Pre-flight checks

```bash
# Verify current version and channel
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, releaseChannel.channel)"

# Check if 1.32 is available in Regular channel
gcloud container get-server-config --region us-central1 \
  --format="yaml(channels.REGULAR)"

# Check for deprecated API usage (most common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Verify cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed
```

## Upgrade commands

```bash
# Upgrade control plane to 1.32
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32

# Monitor progress (optional)
gcloud container operations list \
  --region us-central1 \
  --filter="operationType=UPGRADE_MASTER"
```

## Post-upgrade validation

```bash
# Verify control plane version (wait ~10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"

# Check system pods are healthy
kubectl get pods -n kube-system

# Verify API server responsiveness
kubectl get nodes
kubectl version --short
```

## Important notes

1. **Node pools stay at 1.31** until you separately upgrade them - this is normal and supported
2. **Version skew limit:** Your 1.31 nodes can stay as-is (within 2 minor versions of 1.32 control plane)
3. **Breaking changes:** Review [GKE 1.32 release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) for any breaking changes affecting your workloads
4. **Auto-upgrades:** Since you're on Regular channel, this upgrade may happen automatically soon - doing it manually gives you control over timing

## If something goes wrong

Regional control planes are very stable during upgrades. If you see issues:

```bash
# Check for admission webhook failures (common post-upgrade)
kubectl get events -A --field-selector type=Warning | grep webhook

# Verify system components
kubectl get pods -n kube-system | grep -v Running
```

The upgrade is low-risk for your regional cluster - no API downtime expected. You can proceed with confidence during business hours if needed.