Great question! For a regional GKE cluster, you can upgrade the control plane with **zero downtime** because regional clusters run multiple API server replicas across different zones.

## What Happens During Control Plane Upgrade

**Regional Cluster (your case):**
- ✅ **Zero API server downtime**
- Multiple control plane replicas across 3 zones in us-central1
- Rolling upgrade - one replica at a time
- At least one API server always available
- Your applications continue running normally

## Pre-Upgrade Safety Steps

1. **Check available versions:**
```bash
gcloud container get-server-config --region=us-central1 \
    --format="value(validMasterVersions)" | tr ';' '\n'
```

2. **Verify cluster health:**
```bash
# Check cluster status
kubectl get nodes
kubectl get pods --all-namespaces | grep -v Running

# Check for any issues
gcloud container clusters describe YOUR_CLUSTER_NAME \
    --region=us-central1 --format="value(status)"
```

3. **Review what's changing:**
```bash
# Check current version
gcloud container clusters describe YOUR_CLUSTER_NAME \
    --region=us-central1 --format="value(currentMasterVersion)"
```

## Upgrade Commands

**Option 1: Upgrade to latest 1.32 patch version**
```bash
gcloud container clusters upgrade YOUR_CLUSTER_NAME \
    --region=us-central1 \
    --master \
    --cluster-version=1.32
```

**Option 2: Upgrade to specific 1.32 version**
```bash
# First, see available 1.32 versions
gcloud container get-server-config --region=us-central1 \
    --format="value(validMasterVersions)" | tr ';' '\n' | grep "1.32"

# Then upgrade to specific version (example)
gcloud container clusters upgrade YOUR_CLUSTER_NAME \
    --region=us-central1 \
    --master \
    --cluster-version=1.32.0-gke.1200
```

## Monitor the Upgrade

```bash
# Watch upgrade progress
gcloud container operations list --region=us-central1

# Check cluster status during upgrade
watch "gcloud container clusters describe YOUR_CLUSTER_NAME \
    --region=us-central1 --format='value(status,currentMasterVersion)'"

# Verify API server availability during upgrade
watch "kubectl get nodes"
```

## Post-Upgrade Steps

1. **Verify control plane upgrade:**
```bash
gcloud container clusters describe YOUR_CLUSTER_NAME \
    --region=us-central1 \
    --format="value(currentMasterVersion)"
```

2. **Plan node pool upgrades** (separate operation):
```bash
# Check node versions
kubectl get nodes -o wide

# Upgrade node pools when ready (this WILL cause pod disruption)
gcloud container clusters upgrade YOUR_CLUSTER_NAME \
    --region=us-central1 \
    --node-pool=NODE_POOL_NAME
```

## Key Points for Your Team

- 🟢 **Control plane upgrade**: Zero downtime for regional clusters
- 🟡 **Node pool upgrade**: Will require pod rescheduling (do this separately)
- ⏱️ **Duration**: Control plane upgrade typically takes 10-20 minutes
- 🔄 **Rollback**: Not supported - test in staging first
- 📊 **Monitoring**: Your workloads continue running during control plane upgrade

The upgrade is safe for your regional cluster's API server availability, but make sure to upgrade node pools during a maintenance window since that will disrupt running pods.