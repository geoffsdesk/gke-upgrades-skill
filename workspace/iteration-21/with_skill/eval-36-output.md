Since you have no H100 surge capacity available, you need to use a **drain-first upgrade strategy** that doesn't require additional GPU nodes. Here are your options:

## Option 1: Surge with maxUnavailable (Recommended)

Switch to `maxUnavailable` mode - this drains nodes first, then creates replacements, requiring zero extra GPU capacity:

```bash
# Configure drain-first strategy
gcloud container node-pools update YOUR_NODE_POOL_NAME \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2

# Resume the upgrade
gcloud container node-pools upgrade YOUR_NODE_POOL_NAME \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --cluster-version TARGET_VERSION
```

**Key settings:**
- `maxSurge=0` - No additional nodes created
- `maxUnavailable=2` - Upgrade 2 nodes at a time (adjust based on workload tolerance)
- **Trade-off:** Temporary capacity reduction during upgrade, but zero extra quota needed

For your 64-node pool, `maxUnavailable=2` means you'll temporarily run at 62 nodes during each upgrade batch.

## Option 2: Autoscaled Blue-Green (If you have autoscaling enabled)

If your node pool has autoscaling enabled, use autoscaled blue-green which scales down the old pool as the new one scales up:

```bash
gcloud container node-pools update YOUR_NODE_POOL_NAME \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --enable-autoscaling \
  --total-min-nodes 64 --total-max-nodes 64 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.1,blue-green-full-batch-timeout=3600s
```

This creates only ~6 initial green nodes (10% of 64), then scales down blue as workloads migrate.

## Option 3: Scale Down Before Upgrade

Temporarily reduce your pool size to create headroom for surge:

```bash
# Scale down to 32 nodes temporarily
gcloud container node-pools resize YOUR_NODE_POOL_NAME \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --num-nodes 32

# Use standard surge upgrade (now has room for surge nodes)
gcloud container node-pools update YOUR_NODE_POOL_NAME \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# Upgrade
gcloud container node-pools upgrade YOUR_NODE_POOL_NAME \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --cluster-version TARGET_VERSION

# Scale back up after upgrade completes
gcloud container node-pools resize YOUR_NODE_POOL_NAME \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --num-nodes 64
```

## Recommendation for A3-mega specifically

**Go with Option 1** (`maxSurge=0, maxUnavailable=2`) because:

1. **A3-mega workloads** (multi-host training) typically checkpoint regularly and can tolerate brief capacity reductions
2. **TPU multislice behavior** - A3-mega slices are recreated atomically anyway, so surge vs drain-first makes little difference
3. **Zero additional quota needed** - works within your existing reservation
4. **Predictable timing** - with GKE's ~20-node upgrade parallelism, your 64-node pool will take roughly 32 upgrade cycles at maxUnavailable=2

## Before proceeding

1. **Checkpoint running training jobs** - ensure workloads can resume after node restart
2. **Verify compact placement policy** - confirm replacement nodes will land in the same placement group to preserve RDMA topology
3. **Plan for ~2-4 hours** - large GPU pools take time even with drain-first approach

Would you like me to provide the specific commands with your cluster details, or do you need guidance on checkpointing your training workloads before the upgrade?