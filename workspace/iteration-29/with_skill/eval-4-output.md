# Regional GKE Control Plane Upgrade: Zero Downtime Process

Good news! **Regional GKE clusters have zero API server downtime during control plane upgrades.** Your concerns about downtime don't apply to regional clusters.

## How Regional Control Plane Upgrades Work

**Regional clusters run multiple control plane replicas** (typically 3) distributed across zones in us-central1. During an upgrade:

1. **Rolling upgrade**: GKE upgrades one control plane replica at a time
2. **High availability maintained**: The other replicas continue serving API requests
3. **No service interruption**: Your `kubectl` commands, deployments, and workload operations continue normally
4. **Automatic load balancing**: The regional control plane endpoint automatically routes around the upgrading replica

**Total upgrade time**: ~15-30 minutes for the entire process, but your API server remains available throughout.

## Pre-Flight Verification

First, confirm your setup and check for any blockers:

```bash
# Verify cluster is regional and on Regular channel
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, location, releaseChannel.channel)"

# Check if 1.32 is available in Regular channel
gcloud container get-server-config --region us-central1 \
  --format="yaml(channels.REGULAR)"

# Critical: Check for deprecated API usage (blocks auto-upgrades)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Also check GKE recommender for deprecated API insights
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=us-central1 \
    --project=PROJECT_ID \
    --filter="category.category:RELIABILITY"
```

## Safe Control Plane Upgrade Commands

```bash
# Upgrade control plane only (leaves nodes at 1.31)
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version=1.32.X-gke.XXXX

# Note: Replace X.XXXX with the specific patch version available in Regular channel
```

## Monitor the Upgrade

```bash
# Watch upgrade progress
gcloud container operations list \
  --region us-central1 \
  --filter="targetLink:CLUSTER_NAME AND operationType:UPGRADE_MASTER" \
  --limit=1

# Test API availability during upgrade (run in separate terminal)
while true; do
  kubectl get nodes --request-timeout=5s > /dev/null && echo "$(date): API available" || echo "$(date): API unavailable"
  sleep 10
done
```

## Verify Success

After the upgrade completes (~15-30 minutes):

```bash
# Confirm control plane version
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"

# Verify system components are healthy
kubectl get pods -n kube-system

# Check cluster connectivity
kubectl get nodes
```

## Post-Upgrade: Node Pool Planning

After your control plane is at 1.32, your nodes remain at 1.31 - **this is perfectly fine**. Nodes can be up to 2 minor versions behind the control plane.

**You have three options for node upgrades:**

1. **Let auto-upgrades handle it** (recommended): Your Regular channel will auto-upgrade node pools to 1.32 within ~2-4 weeks
2. **Manual upgrade immediately**: If you want to standardize on 1.32 across all components
3. **Skip to 1.33**: Wait for control plane 1.33, then do skip-level node upgrade (1.31→1.33) to minimize node disruption

## Why Regional Clusters Are Different

| Cluster Type | Control Plane Replicas | Upgrade Behavior |
|--------------|------------------------|------------------|
| **Zonal** | Single replica | ~5-10 minutes downtime during CP upgrade |
| **Regional** | Multiple replicas | Zero downtime - rolling upgrade |

Your regional cluster's architecture eliminates the API server downtime concern that affects zonal clusters.

## Next Steps

1. **Run the pre-flight checks** to ensure no deprecated APIs will block the upgrade
2. **Execute the control plane upgrade** - it's safe and zero-downtime for regional clusters
3. **Plan node pool upgrades** separately (can be done later when convenient)

The control plane upgrade is low-risk for regional clusters. Your main considerations should be around deprecated API usage and coordinating the eventual node pool upgrades with your application teams.