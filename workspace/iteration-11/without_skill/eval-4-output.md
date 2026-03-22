Great question! For a **regional Standard GKE cluster**, you'll have **zero API server downtime** during the control plane upgrade. Here's why and how to do it safely:

## Why Zero Downtime?

Regional clusters run multiple control plane replicas across different zones. During upgrades, GKE performs a **rolling upgrade** of these replicas, ensuring at least one is always available to serve API requests.

## Pre-Upgrade Checklist

1. **Check available versions**:
```bash
gcloud container get-server-config --region=us-central1 --format="yaml(channels)"
```

2. **Verify current cluster state**:
```bash
gcloud container clusters describe YOUR_CLUSTER_NAME --region=us-central1 \
  --format="value(currentMasterVersion,currentNodeVersion,status)"
```

3. **Check for any ongoing operations**:
```bash
gcloud container operations list --region=us-central1 --filter="status=RUNNING"
```

## Safe Upgrade Commands

### Option 1: Upgrade to Latest 1.32 (Recommended)
```bash
# Control plane only
gcloud container clusters upgrade YOUR_CLUSTER_NAME \
  --region=us-central1 \
  --master \
  --cluster-version=1.32 \
  --quiet
```

### Option 2: Upgrade to Specific 1.32 Patch Version
```bash
# First, find the exact version
gcloud container get-server-config --region=us-central1 \
  --format="value(validMasterVersions)" | grep "1.32"

# Then upgrade (replace with actual version)
gcloud container clusters upgrade YOUR_CLUSTER_NAME \
  --region=us-central1 \
  --master \
  --cluster-version=1.32.x-gke.xxxx \
  --quiet
```

## What Happens During Upgrade

1. **Phase 1**: Rolling upgrade of control plane replicas (5-10 minutes)
   - Each replica upgraded sequentially
   - Load balancer routes traffic to healthy replicas
   - **Zero API downtime**

2. **Phase 2**: System components update automatically
   - kube-dns, metrics-server, etc.
   - May cause brief individual component restarts

## Monitoring the Upgrade

```bash
# Watch upgrade progress
gcloud container operations list --region=us-central1 \
  --filter="operationType=UPGRADE_MASTER" \
  --format="table(name,status,startTime,endTime)"

# Check cluster status
watch 'gcloud container clusters describe YOUR_CLUSTER_NAME --region=us-central1 --format="value(status,currentMasterVersion)"'
```

## Post-Upgrade Verification

```bash
# Verify control plane version
kubectl version --short

# Check cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running

# Verify core components
kubectl get pods -n kube-system
```

## Important Notes

- **Control plane upgrade is separate** from node upgrades
- **Workloads continue running** on existing nodes during control plane upgrade
- **Node pools remain at 1.31** until you explicitly upgrade them
- **API compatibility**: 1.32 control plane supports 1.31 nodes (n-1 skew policy)

## Next Steps After Control Plane Upgrade

Plan your node pool upgrades:
```bash
# List node pools
gcloud container node-pools list --cluster=YOUR_CLUSTER_NAME --region=us-central1

# Upgrade node pools (do this after control plane is stable)
gcloud container clusters upgrade YOUR_CLUSTER_NAME \
  --region=us-central1 \
  --node-pool=NODE_POOL_NAME
```

The upgrade typically takes 5-15 minutes with zero API server downtime for regional clusters. Your team can proceed with confidence!