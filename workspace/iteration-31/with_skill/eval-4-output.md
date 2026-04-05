You're in good shape! Since you have a **regional cluster**, your control plane will remain **highly available** during the upgrade with **zero API server downtime**. Here's what happens and how to do it safely:

## What happens during a regional control plane upgrade

**Regional clusters have multiple control plane replicas** (typically 3) spread across zones. During upgrade:
1. GKE upgrades one replica at a time
2. The other replicas continue serving API requests
3. Each replica is briefly unavailable during its individual upgrade (~2-3 minutes)
4. **No cluster-wide API downtime occurs** - you can deploy workloads, modify resources, and manage the cluster normally throughout

This is the key advantage of regional over zonal clusters for production workloads.

## Pre-flight safety checks

First, verify everything is ready:

```bash
# Check current status and available versions
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, status)"

# Confirm 1.32 is available in Regular channel
gcloud container get-server-config --region us-central1 \
  --format="yaml(channels.REGULAR)"

# Check for deprecated API usage (most common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Verify cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed
```

## Safe upgrade procedure

```bash
# 1. Apply a maintenance window (optional but recommended for timing control)
gcloud container clusters update CLUSTER_NAME \
  --region us-central1 \
  --maintenance-window-start "2024-01-20T02:00:00Z" \
  --maintenance-window-end "2024-01-20T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# 2. Upgrade control plane to 1.32 (this bypasses maintenance windows for manual upgrades)
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32

# 3. Monitor the upgrade (typically takes 10-15 minutes)
gcloud container operations list --region us-central1 --filter="targetLink~CLUSTER_NAME AND operationType=UPGRADE_MASTER"

# 4. Verify completion
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"

# 5. Check system pod health
kubectl get pods -n kube-system
```

## Expected timeline

- **Total upgrade time**: 10-15 minutes for control plane
- **API availability**: 100% throughout the process
- **Workload impact**: None (workloads continue running normally)

## Post-upgrade validation

```bash
# Confirm control plane health
kubectl get componentstatuses
kubectl get pods -n kube-system | grep -v Running

# Test API functionality
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "API test successful"

# Check for any admission webhook issues (common after CP upgrades)
kubectl get events -A --field-selector type=Warning | grep webhook
```

## Node pool considerations

After the control plane upgrade succeeds, your **nodes will still be at 1.31**. This is perfectly fine - GKE supports node versions up to 2 minor versions behind the control plane. You can:

- **Leave nodes at 1.31** - they'll auto-upgrade eventually based on your maintenance window
- **Manually upgrade node pools later** when convenient
- **Let auto-upgrade handle it** during your next maintenance window

## If something goes wrong

Regional control planes are very reliable, but if you see issues:
1. **API errors**: Check `kubectl get events -A --field-selector type=Warning`
2. **Webhook failures**: Common after version bumps - verify cert-manager and other admission controllers
3. **Stuck upgrade**: Operations typically complete within 30 minutes; contact support if longer

You're doing this the right way - regional cluster + Regular channel + manual timing control gives you the best balance of safety and predictability!