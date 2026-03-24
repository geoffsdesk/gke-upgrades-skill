Great question! For a **regional GKE cluster**, you'll have **zero API server downtime** during the control plane upgrade. Here's why and how to do it safely:

## Why No Downtime?

Regional GKE clusters run multiple control plane replicas across different zones. During an upgrade, GKE performs a **rolling upgrade** of these replicas, ensuring at least one is always available to serve API requests.

## Pre-Upgrade Checks

First, verify your current setup and available versions:

```bash
# Check current cluster version
kubectl version --short

# List available master versions
gcloud container get-server-config --region=us-central1 --format="value(validMasterVersions[0:5])"

# Check cluster details
gcloud container clusters describe YOUR_CLUSTER_NAME --region=us-central1
```

## Safe Upgrade Process

### 1. Upgrade Control Plane Only
```bash
# Upgrade just the control plane to 1.32 (latest patch version)
gcloud container clusters upgrade YOUR_CLUSTER_NAME \
    --region=us-central1 \
    --master \
    --cluster-version=1.32 \
    --quiet
```

**Note:** The `--master` flag ensures only the control plane upgrades, leaving nodes untouched.

### 2. Monitor the Upgrade
```bash
# Check upgrade status
gcloud container operations list --region=us-central1

# Watch cluster status
watch "gcloud container clusters describe YOUR_CLUSTER_NAME --region=us-central1 --format='value(status,currentMasterVersion)'"
```

### 3. Verify API Server Availability
During the upgrade, test API connectivity:
```bash
# This should work throughout the upgrade
kubectl get nodes
kubectl get pods --all-namespaces
```

## What to Expect

- **Duration**: 10-20 minutes typically
- **API Server**: Remains responsive throughout
- **Workloads**: Continue running normally
- **Node Pools**: Remain on 1.31 until you separately upgrade them

## Post-Upgrade Node Pool Upgrade

After control plane upgrade completes:

```bash
# List node pools
gcloud container node-pools list --cluster=YOUR_CLUSTER_NAME --region=us-central1

# Upgrade each node pool (this WILL cause pod disruption)
gcloud container clusters upgrade YOUR_CLUSTER_NAME \
    --region=us-central1 \
    --node-pool=NODE_POOL_NAME \
    --cluster-version=1.32
```

## Best Practices

1. **Test in staging first**
2. **Upgrade during low-traffic periods**
3. **Ensure PodDisruptionBudgets are configured** for node pool upgrades later
4. **Monitor your applications** during and after the upgrade
5. **Have rollback plan ready** (though control plane rollbacks aren't supported)

The control plane upgrade itself is very safe for regional clusters - your team shouldn't worry about API server downtime!