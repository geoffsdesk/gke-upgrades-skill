# GKE Control Plane Upgrade: 1.31 → 1.32 (Regional Standard Cluster)

## API Server Availability During Upgrade

**Good news: Regional GKE clusters have ZERO control plane downtime during upgrades.** Here's what happens:

- **Regional clusters** run multiple API server replicas across 3 zones with a load balancer
- During upgrade, GKE performs a **rolling update** of the control plane replicas
- One replica upgrades while others continue serving traffic
- Total upgrade time: ~10-15 minutes with continuous API availability
- Your `kubectl` commands, CI/CD pipelines, and workloads continue operating normally

This is a major advantage of regional clusters over zonal clusters (which do have brief API server downtime).

## Pre-Flight Verification

First, let's confirm your upgrade path:

```bash
# Check current version and available upgrades
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
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
```

## Control Plane Upgrade Commands

```bash
# Upgrade control plane to 1.32
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32

# Monitor progress (upgrade takes ~10-15 minutes)
gcloud container operations list \
  --region us-central1 \
  --cluster CLUSTER_NAME \
  --filter="operationType=UPGRADE_MASTER" \
  --limit=1

# Verify completion
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"
```

## What to Expect During Upgrade

**Timeline:**
- **Minute 0:** Upgrade initiated, first control plane replica begins updating
- **Minutes 1-5:** First replica offline, other replicas handle all traffic
- **Minutes 5-10:** First replica returns, second replica upgrades
- **Minutes 10-15:** Final replica upgrades, all replicas now at 1.32
- **Throughout:** API server remains available, no `kubectl` interruption

**Monitoring during upgrade:**
```bash
# Watch system pods (will restart as control plane upgrades)
watch 'kubectl get pods -n kube-system'

# Verify API responsiveness
kubectl get ns  # Should work throughout upgrade
```

## Post-Upgrade Validation

```bash
# Confirm control plane version
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"
# Should show: 1.32.x-gke.xxxx

# Check system pod health
kubectl get pods -n kube-system
# All should be Running

# Verify node versions (will still be 1.31 until you upgrade node pools)
kubectl get nodes -o wide
# Nodes remain at 1.31 - this is expected and supported
```

## Important Notes

1. **Node pools remain at 1.31** - Only the control plane upgrades. Nodes can be up to 2 minor versions behind (1.31 vs 1.32 is fine).

2. **No workload impact** - Your application pods continue running on 1.31 nodes and can communicate with the 1.32 control plane.

3. **Auto-upgrade behavior** - Since you're on Regular channel, GKE will automatically upgrade your node pools to 1.32 within the next few weeks (respecting your maintenance windows).

4. **Breaking changes** - Review [GKE 1.32 release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) for any API changes that might affect your workloads.

## Next Steps

After control plane upgrade completes successfully:
- Plan node pool upgrades (can be done immediately or wait for auto-upgrade)
- Test applications against 1.32 control plane
- Node pools will auto-upgrade to 1.32 based on your maintenance windows and Regular channel timing

The control plane upgrade is the lowest-risk step since regional clusters maintain API availability throughout. Let me know if you'd like a node pool upgrade plan next!