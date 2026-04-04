# GKE Control Plane Upgrade: Regional Standard Cluster (1.31 → 1.32)

## What happens during a regional control plane upgrade

**Good news: Zero API server downtime expected.** Regional clusters have multiple control plane replicas across zones, and GKE upgrades them one at a time. Your cluster remains highly available throughout the process.

**Upgrade process:**
1. GKE upgrades one control plane replica at a time
2. Each replica is briefly unavailable during its upgrade (~2-5 minutes)
3. Other replicas continue serving API requests
4. Total upgrade time: ~10-15 minutes
5. **No workload disruption** — only the control plane is upgraded

## Pre-flight verification

Before upgrading, verify 1.32 is available in Regular channel and check for any compatibility issues:

```bash
# Check current cluster state
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, releaseChannel.channel)"

# Verify 1.32 is available in Regular channel
gcloud container get-server-config --region us-central1 \
  --format="yaml(channels.REGULAR.validVersions)" | grep "1\.32"

# Check for deprecated API usage (most common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Alternative: Check GKE deprecation insights
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=us-central1 \
    --project=PROJECT_ID \
    --filter="category.category:RELIABILITY"

# Verify cluster health
kubectl get nodes
kubectl get pods -n kube-system
```

## Safe upgrade commands

**Option 1: Manual upgrade to specific 1.32 patch (recommended for control)**
```bash
# Upgrade to latest 1.32 patch available in Regular channel
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version=1.32.X-gke.XXXX

# Monitor progress (upgrade typically completes in 10-15 minutes)
gcloud container operations list \
  --region us-central1 \
  --filter="operationType=UPGRADE_MASTER AND targetId=CLUSTER_NAME" \
  --limit=1
```

**Option 2: Auto-upgrade with timing control**
Since you're on Regular channel, 1.32 will become the auto-upgrade target soon. You can:
- Let it upgrade automatically during your maintenance window
- Or trigger it manually now using Option 1

## Validation after upgrade

```bash
# Verify control plane version
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"

# Check API server responsiveness
kubectl get nodes
kubectl get pods -n kube-system

# Verify no issues with system components
kubectl get events -n kube-system --sort-by='.lastTimestamp' | tail -10
```

## What about node pools?

**Important:** This upgrade only affects the control plane. Your node pools remain at 1.31, which is perfectly valid (nodes can be up to 2 minor versions behind the control plane).

**Next steps for nodes:**
- Node pools will auto-upgrade to 1.32 in the coming days/weeks (controlled by your maintenance window)
- Or you can manually upgrade them after validating the control plane upgrade
- Consider your node pool upgrade strategy (surge settings) when ready

## Risk mitigation

**Why this upgrade is low-risk:**
- Regional cluster = no API downtime
- Control plane only = no workload disruption  
- 1.31→1.32 is a single minor version jump (supported)
- Regular channel = versions are well-tested before reaching you

**If something goes wrong:**
- Control plane upgrades rarely fail, but if issues occur, contact Google Cloud Support
- Your workloads continue running even if the API is temporarily impacted
- Node pools remain at 1.31 and functional

## Maintenance window consideration

If you have a maintenance window configured, manual upgrades bypass it. Auto-upgrades respect the window. Since regional upgrades have no downtime, you can safely run this upgrade during business hours if needed.

Would you like me to help you plan the node pool upgrade strategy for after the control plane is upgraded?