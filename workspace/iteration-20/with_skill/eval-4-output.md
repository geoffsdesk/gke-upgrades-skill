# GKE Control Plane Upgrade Plan: 1.31 → 1.32

## What happens during a regional control plane upgrade

**Good news: Zero API server downtime expected.** Regional GKE clusters have multiple control plane replicas distributed across zones. During an upgrade:

1. **Rolling upgrade process**: GKE upgrades one control plane replica at a time
2. **High availability maintained**: Other replicas continue serving API requests
3. **Brief individual replica downtime**: Each replica is unavailable for ~2-3 minutes during its upgrade
4. **Total upgrade duration**: ~10-15 minutes for the entire control plane
5. **Workloads unaffected**: Your pods and services continue running normally

This is the key advantage of regional clusters over zonal clusters (which do experience API server downtime during control plane upgrades).

## Pre-flight checklist

```bash
# 1. Verify current versions and channel
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, releaseChannel.channel)"

# 2. Check if 1.32 is available in Regular channel
gcloud container get-server-config --region us-central1 \
  --format="yaml(channels)"
# Look for 1.32.x under "regular" channel

# 3. Check for deprecated API usage (most common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# 4. Verify cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed
kubectl get pods -n kube-system
```

## Upgrade commands

### Option 1: Auto-upgrade (recommended)
Since you're on Regular channel, 1.32 will become the auto-upgrade target eventually. You can wait for automatic upgrade or proceed manually:

```bash
# Check current auto-upgrade target
gcloud container clusters get-upgrade-info CLUSTER_NAME --region us-central1

# If 1.32 is already the target, it will upgrade automatically during your maintenance window
```

### Option 2: Manual upgrade (for immediate control)
```bash
# Upgrade control plane to latest 1.32 patch
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32

# Or specify exact patch version if needed
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32.0-gke.1200
```

### Two-step upgrade option (for maximum safety)
GKE 1.33+ supports a rollback-safe two-step process. Since you're upgrading to 1.32, this isn't available, but good to know for future upgrades:

```bash
# Future reference: Two-step upgrade (1.33+)
gcloud beta container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version TARGET_VERSION \
  --control-plane-soak-duration 24h  # Rollback window
```

## Monitoring the upgrade

```bash
# Watch upgrade progress
gcloud container operations list \
  --region us-central1 \
  --filter="operationType=UPGRADE_MASTER" \
  --limit=1

# Verify completion (should show 1.32.x)
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"

# Ensure system pods are healthy after upgrade
kubectl get pods -n kube-system
```

## Post-upgrade validation

```bash
# Confirm API server responsiveness
kubectl get nodes
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded

# Check for any admission webhook issues (common after control plane upgrades)
kubectl get events -A --field-selector type=Warning | grep webhook

# Verify critical workloads
kubectl get deployments -A
kubectl get statefulsets -A
```

## Important notes

1. **Node pools stay at 1.31**: This upgrade only affects the control plane. Your nodes remain at 1.31 (within the 2-minor-version skew limit).

2. **No workload disruption**: Pods continue running during control plane upgrade.

3. **API compatibility**: 1.32 maintains compatibility with 1.31 workloads. Check [GKE release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) for any breaking changes.

4. **Rollback limitation**: Control plane minor version rollbacks require GKE support involvement. Patch downgrades within 1.32 can be done by customers.

5. **Node upgrades next**: After control plane upgrade, plan your node pool upgrades separately (these DO cause pod disruption).

The regional architecture makes this a low-risk operation. Your team can proceed with confidence that API server availability will be maintained throughout the upgrade.