# Regional Standard GKE Control Plane Upgrade: No Downtime Expected

## Good news about regional clusters

Since you're running a **regional** Standard cluster, you have **multiple control plane replicas** across zones in us-central1. During the upgrade:

- ✅ **No API server downtime** - replicas are upgraded one at a time
- ✅ **Cluster remains highly available** throughout the upgrade
- ✅ **Workloads continue running** normally
- ✅ **You can deploy/modify resources** during the upgrade

This is very different from zonal clusters, which do experience brief API downtime during control plane upgrades.

## Pre-flight checklist

Run these commands to verify readiness:

```bash
# 1. Confirm current state
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, releaseChannel.channel, locations)"

# 2. Check 1.32 is available in Regular channel
gcloud container get-server-config --region us-central1 \
  --format="yaml(channels.REGULAR)"

# 3. Check for deprecated API usage (upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# 4. Verify cluster health
kubectl get nodes --show-labels | grep failure-domain
kubectl get pods -n kube-system | grep -v Running
```

## Safe upgrade commands

### Option 1: Manual upgrade (immediate)
```bash
# Upgrade control plane to 1.32
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32

# Monitor progress (upgrade typically takes 10-20 minutes)
gcloud container operations list \
  --region us-central1 \
  --filter="operationType=UPGRADE_MASTER AND targetId=CLUSTER_NAME"
```

### Option 2: Configure maintenance window first
If you want to control exactly when auto-upgrades happen in the future:

```bash
# Set maintenance window (example: Saturdays 2-6 AM Central Time)
gcloud container clusters update CLUSTER_NAME \
  --region us-central1 \
  --maintenance-window-start "2025-01-01T08:00:00Z" \
  --maintenance-window-end "2025-01-01T12:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Then upgrade manually or wait for auto-upgrade during window
```

## Validation after upgrade

```bash
# 1. Verify control plane version
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"

# 2. Check system pod health
kubectl get pods -n kube-system

# 3. Test API responsiveness
kubectl get namespaces
kubectl create deployment test-deploy --image=nginx --dry-run=client -o yaml

# 4. Verify all zones are healthy
kubectl get nodes -o wide --sort-by='.metadata.labels.failure-domain\.beta\.kubernetes\.io/zone'
```

## What happens during the upgrade

1. **Replica 1** (zone A): Upgraded first while replicas 2+3 handle traffic
2. **Replica 2** (zone B): Upgraded second while replicas 1+3 handle traffic  
3. **Replica 3** (zone C): Upgraded last while replicas 1+2 handle traffic

Each replica upgrade takes ~3-5 minutes. Total time: **10-20 minutes** with zero API downtime.

## Node pools remain at 1.31

**Important**: This upgrade only affects the control plane. Your node pools will remain at 1.31, which is perfectly fine - nodes can be up to 2 minor versions behind the control plane.

You can upgrade node pools later when convenient using your preferred strategy (surge, blue-green, etc.).

## Next steps after control plane upgrade

1. **Test critical workloads** - Deploy a test application to verify everything works
2. **Plan node pool upgrades** - Decide when to upgrade your node pools from 1.31 to 1.32
3. **Review GKE 1.32 features** - Check the [release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) for new capabilities

Your team can proceed with confidence - regional clusters provide excellent availability during control plane upgrades! 🚀