# GKE Control Plane Upgrade: Regional Standard Cluster

## What Will Happen During Your Upgrade

**Good news: Zero API server downtime expected.** Since you have a **regional Standard cluster**, your control plane has multiple replicas distributed across zones in us-central1. During the upgrade:

1. **High availability maintained**: GKE upgrades one control plane replica at a time
2. **API server stays responsive**: Other replicas handle requests while one upgrades
3. **Typical duration**: 10-15 minutes total, with each replica briefly unavailable during its turn
4. **No workload impact**: Your pods keep running normally throughout

This is fundamentally different from zonal clusters, where the single control plane replica causes a brief API outage.

## Pre-Flight Safety Checks

First, verify your upgrade path and cluster health:

```bash
# Confirm current versions and channel
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, releaseChannel.channel, nodePools[].name, nodePools[].version)"

# Check if 1.32 is available in Regular channel
gcloud container get-server-config --region us-central1 \
  --format="yaml(channels.REGULAR)"

# Check for deprecated API usage (most common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Verify cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed | head -10
```

## Safe Upgrade Commands

### Step 1: Control Plane Upgrade Only

```bash
# Upgrade ONLY the control plane to 1.32 (leaves nodes at 1.31)
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32

# The --master flag is crucial - it upgrades only the control plane
```

### Step 2: Monitor Progress

```bash
# Check upgrade status
gcloud container operations list \
  --region us-central1 \
  --filter="targetId:CLUSTER_NAME AND operationType:UPGRADE_MASTER" \
  --limit 1

# Verify control plane version (should show 1.32 when complete)
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"

# Test API responsiveness during upgrade
kubectl get nodes --watch
```

### Step 3: Validation

```bash
# Confirm control plane health
kubectl get pods -n kube-system
kubectl cluster-info

# Verify your workloads are unaffected
kubectl get deployments -A
kubectl get pods -A | grep -v Running | grep -v Completed
```

## What About Node Pools?

After the control plane upgrade completes:
- **Your nodes stay at 1.31** - this is perfectly fine and supported
- **Version skew**: Nodes can be up to 2 minor versions behind the control plane
- **Auto-upgrade**: Regular channel will automatically upgrade your node pools in the coming weeks
- **Manual option**: You can upgrade node pools immediately if desired, but it's not required

## Safety Considerations

1. **Maintenance window**: Consider setting one for predictable timing of future auto-upgrades:
```bash
gcloud container clusters update CLUSTER_NAME \
  --region us-central1 \
  --maintenance-window-start "2025-01-25T02:00:00Z" \
  --maintenance-window-end "2025-01-25T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

2. **Two-step upgrade option**: GKE 1.33+ supports rollback-safe two-step minor upgrades. For 1.31→1.32, use the standard one-step process above.

3. **Emergency rollback**: Control plane minor version rollbacks require GKE support involvement. Node pools can be rolled back by creating a new pool at 1.31.

## Key Points for Your Team

- ✅ **Zero downtime**: Regional clusters maintain API availability during control plane upgrades
- ✅ **Workloads unaffected**: Pods continue running normally
- ✅ **Node pools can wait**: No immediate need to upgrade nodes from 1.31
- ✅ **Auto-upgrade handles nodes**: Regular channel will upgrade nodes automatically in ~2-4 weeks
- ✅ **Safe operation**: This is a routine maintenance task for regional clusters

The control plane upgrade is the low-risk part of the process. Node pool upgrades (which involve pod eviction and rescheduling) carry more complexity, but you can do those separately when ready.