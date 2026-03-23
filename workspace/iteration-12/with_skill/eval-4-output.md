# GKE Control Plane Upgrade Plan: 1.31 → 1.32

## What happens during control plane upgrade

**Good news: Zero API server downtime.** Regional GKE clusters have multiple control plane replicas across zones. During upgrade:

1. **Rolling upgrade**: Control plane replicas upgrade one at a time
2. **Load balancer switches traffic** to healthy replicas during each upgrade
3. **No API interruption**: kubectl, deployments, pods continue working normally
4. **Duration**: Typically 10-15 minutes for the entire process

The only brief interruptions (seconds, not minutes) may occur during load balancer failover between replicas, but these are handled automatically by kubectl retry logic.

## Pre-flight checks

```bash
# Verify current state and available versions
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, releaseChannel.channel)"

# Check available 1.32 versions in Regular channel
gcloud container get-server-config --region us-central1 \
  --format="yaml(channels.regular.validVersions)" | grep "1\.32"

# Verify cluster health before upgrade
kubectl get nodes
kubectl get pods -n kube-system | grep -v Running
```

## Control plane upgrade commands

```bash
# Option 1: Upgrade to latest 1.32 patch (recommended)
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32

# Option 2: Upgrade to specific 1.32 patch
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32.X-gke.XXXX
```

## Monitor progress

```bash
# Check upgrade status
gcloud container operations list \
  --region us-central1 \
  --cluster CLUSTER_NAME \
  --filter="operationType=UPGRADE_MASTER" \
  --limit=1

# Verify new control plane version (after completion)
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"

# Confirm system pods healthy
kubectl get pods -n kube-system
kubectl get componentstatuses  # Should show all healthy
```

## Important notes

- **Node pools remain at 1.31** after this upgrade - that's normal and supported
- **Version skew**: Nodes can be up to 2 minor versions behind control plane
- **No workload impact**: Your application pods are unaffected by control plane upgrade
- **Auto-upgrade timing**: Since you're on Regular channel, this upgrade would happen automatically within the next few weeks anyway

## Next steps after control plane upgrade

Once the control plane is at 1.32, you can upgrade node pools at your convenience:

```bash
# List node pools and their versions
gcloud container node-pools list --cluster CLUSTER_NAME --region us-central1

# Upgrade node pools (when ready) - this WILL restart pods
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region us-central1 \
  --cluster-version 1.32
```

**Timeline recommendation**: Upgrade control plane now (zero downtime), then schedule node pool upgrades during your next maintenance window since those will restart application pods.

Does this address your concerns about API server availability? The control plane upgrade is the safe, zero-downtime part of the process.