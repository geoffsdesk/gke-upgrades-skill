# GKE Control Plane Upgrade Plan: 1.31 → 1.32

## Control Plane Availability During Upgrade

**Good news: Zero downtime for your workloads.** Here's what happens during a regional Standard cluster control plane upgrade:

- **API server availability**: ~5-10 seconds of brief interruptions as traffic shifts between API server replicas
- **Workload impact**: None - your pods keep running normally
- **kubectl/CI disruption**: Minimal - automatic retries handle the brief API unavailability
- **Duration**: 10-15 minutes total for the control plane upgrade

Regional clusters have multiple API server replicas across zones. GKE upgrades them in a rolling fashion, so you maintain API availability throughout.

## Pre-flight Validation

First, let's confirm your current state and target availability:

```bash
# Check current versions
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Verify 1.32 is available in Regular channel
gcloud container get-server-config --region us-central1 \
  --format="yaml(channels.regular)"

# Check for deprecated API usage (common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# If the above is empty, also check GKE deprecation insights
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=us-central1 \
    --project=PROJECT_ID \
    --filter="category.category:PERFORMANCE"
```

## Safe Control Plane Upgrade Commands

```bash
# 1. Upgrade control plane only (leaves nodes at 1.31)
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32

# 2. Monitor progress (upgrade takes ~10-15 minutes)
watch 'gcloud container clusters describe CLUSTER_NAME --region us-central1 --format="value(currentMasterVersion,status)"'
```

## Post-Upgrade Validation

```bash
# Verify control plane version
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"

# Check system components are healthy
kubectl get pods -n kube-system

# Verify API server responsiveness
kubectl get nodes
kubectl get namespaces
```

## Version Skew Consideration

After upgrading the control plane to 1.32, your nodes will remain at 1.31. This is supported (1 minor version skew), but plan your node pool upgrades:

- **Supported skew**: Control plane 1.32 + nodes 1.31 ✅
- **Next step**: Upgrade node pools to 1.32 within a reasonable timeframe
- **Auto-upgrade**: If you have auto-upgrades enabled, node pools will upgrade automatically according to your maintenance windows

## If You Want to Control the Full Timeline

Consider setting a maintenance exclusion if you want to control when node pools upgrade:

```bash
# Prevent node pool auto-upgrades for 30 days (allows you to plan timing)
gcloud container clusters update CLUSTER_NAME \
  --region us-central1 \
  --add-maintenance-exclusion-name "planned-node-upgrade" \
  --add-maintenance-exclusion-start-time "2024-01-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-02-14T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

This blocks node pool upgrades while allowing control plane patches, giving you control over when to tackle node upgrades.

## What Could Go Wrong?

The most common control plane upgrade issue is **deprecated API usage**. If GKE detects your cluster is using APIs removed in 1.32, the upgrade will be automatically paused with a clear error message. The pre-flight checks above will catch this.

Your regional Standard cluster on Regular channel is in the ideal configuration for smooth upgrades - you should expect this to complete without issues.