For GPU node pools with fixed reservations and no surge capacity, your **primary lever is `maxUnavailable`**, not `maxSurge`. Here are your options:

## Option 1: Drain-first upgrade (recommended)

This avoids needing any surge capacity by draining nodes before creating replacements:

```bash
# Configure drain-first strategy
gcloud container node-pools update YOUR_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

# Resume the upgrade
gcloud container node-pools upgrade YOUR_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

**Trade-offs:**
- ✅ No extra GPU quota needed
- ✅ Uses your existing reservation slots
- ❌ Temporary capacity dip (63/64 nodes during each batch)
- ⏱️ Slower: ~64 batches with GKE's ~20-node parallelism limit = ~3.2 cycles

## Option 2: Increase drain parallelism (faster but more capacity loss)

If your workloads can tolerate larger temporary capacity reduction:

```bash
# Drain 2-4 nodes simultaneously
gcloud container node-pools update YOUR_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4
```

**Trade-offs:**
- ✅ Faster completion (60/64 nodes available during batches)
- ❌ More capacity loss during upgrade
- Consider your training/inference workload's fault tolerance

## Option 3: Use autoscaled blue-green (if workload-appropriate)

For inference workloads or when you need controlled transition:

```bash
# Enable autoscaling first
gcloud container node-pools update YOUR_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 0 \
  --total-max-nodes 64

# Configure autoscaled blue-green
gcloud container node-pools update YOUR_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

**When to use:** Inference workloads that benefit from gradual transition. **Avoid for training:** multi-day training jobs will be disrupted.

## Option 4: Manual blue-green (maximum control)

For mission-critical workloads needing the most careful transition:

```bash
# 1. Create new pool at target version
gcloud container node-pools create gpu-pool-new \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --machine-type a3-megagpu-8g \
  --num-nodes 64 \
  --accelerator type=nvidia-h100-mega-80gb,count=8,gpu-driver-version=LATEST \
  --cluster-version TARGET_VERSION

# 2. Cordon old pool
kubectl cordon -l cloud.google.com/gke-nodepool=YOUR_POOL_NAME

# 3. Wait for training jobs to complete naturally, then drain
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data

# 4. Delete old pool once migration complete
gcloud container node-pools delete YOUR_POOL_NAME --cluster CLUSTER_NAME --zone ZONE
```

## For A3-mega specifically

A3-mega nodes have special considerations:
- **RDMA topology:** Verify replacement nodes maintain compact placement for multi-node training
- **GPUDirect-TCPX:** Ensure your target GKE version supports your interconnect requirements
- **Extended termination:** Training workloads may need >1 hour graceful termination

## Recommendation

**Start with Option 1** (`maxSurge=0, maxUnavailable=1`). It's the safest approach that works within your existing reservation. If the upgrade pace is too slow for your maintenance window, increase `maxUnavailable` to 2-4 based on your workload's capacity requirements.

**Before proceeding:** If you have active multi-day training runs, set a maintenance exclusion first:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time "2024-XX-XXTXX:XX:XXZ" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

Would you like me to provide the specific commands for your environment once you share your cluster/pool names?