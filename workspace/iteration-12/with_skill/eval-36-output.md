You have several options to upgrade without additional GPU quota. Here's your best path forward:

## Recommended: Use maxUnavailable mode (no surge capacity needed)

This is the most common approach for GPU pools with fixed reservations:

```bash
# Configure the node pool for drain-first upgrades
gcloud container node-pools update YOUR_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4

# Then retry the upgrade
gcloud container node-pools upgrade YOUR_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

**How this works:**
- `maxSurge=0` means no extra nodes are created
- `maxUnavailable=4` means 4 nodes at a time are cordoned, drained, and replaced
- No additional quota needed — uses your existing 64-node allocation

**Trade-offs:**
- **Capacity dip:** You'll temporarily have 60 nodes available instead of 64 during each batch
- **Slower:** Processes 4 nodes at a time instead of creating surge capacity
- **Zero extra cost:** No temporary GPU charges

## Alternative: Autoscaled Blue-Green (if you can tolerate the capacity requirements)

If your reservation actually has headroom or you can temporarily expand:

```bash
gcloud container node-pools update YOUR_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 64 --total-max-nodes 128 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

This creates replacement nodes gradually as workloads are drained, but still requires capacity for replacement nodes.

## For large training workloads: Consider timing

Given your 64-node cluster size, this is likely a training environment. Consider:

1. **Checkpoint current training jobs** before starting the upgrade
2. **Use a larger maxUnavailable** (8-16 nodes) to complete faster if your workloads can tolerate the capacity reduction
3. **Apply a maintenance exclusion** to delay auto-upgrades until your next planned training gap:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time "2024-12-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

## Fastest option: Parallel maintenance during training gap

If you can schedule downtime for all nodes:

1. Scale training workloads to zero or checkpoint
2. Apply the host maintenance label to all nodes simultaneously:
```bash
kubectl label nodes -l cloud.google.com/gke-nodepool=YOUR_POOL_NAME \
  cloud.google.com/perform-maintenance=true
```
3. Wait ~4 hours for host maintenance to complete
4. All nodes upgraded in parallel (fastest wall-clock time)

**Recommendation:** Start with `maxSurge=0, maxUnavailable=4` for your first attempt. Increase `maxUnavailable` to 8 if the 4-node capacity dip is acceptable to your workloads. This is the standard pattern for GPU pools with fixed reservations.