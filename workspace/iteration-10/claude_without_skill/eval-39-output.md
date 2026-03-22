Your described approach is **not optimal** for GPU nodes with fixed reservations. Here's why and what you should do instead:

## Problems with the Manual Approach

1. **Reservation conflicts**: You can't run both old and new node pools simultaneously if they share the same reservation
2. **GPU waste**: Creating a new pool means temporarily doubling your GPU allocation (expensive!)
3. **Complex orchestration**: Manual cordoning/draining is error-prone and time-consuming

## Better Approaches

### Option 1: In-Place Node Pool Upgrade (Recommended)
```bash
# Enable auto-upgrade temporarily for controlled upgrade
gcloud container node-pools update GPU_POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=ZONE \
    --enable-autoupgrade

# Or trigger manual upgrade
gcloud container node-pools upgrade GPU_POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=ZONE \
    --node-version=1.32
```

**Benefits:**
- Uses existing reservations
- GKE handles cordoning/draining automatically
- Rolling upgrade maintains some capacity
- No additional costs

### Option 2: Blue-Green with Reservation Management
If you must use the new pool approach:

```bash
# 1. Modify reservation to increase capacity temporarily
gcloud compute reservations update RESERVATION_NAME \
    --zone=ZONE \
    --vm-count=256  # Double your current capacity

# 2. Create new node pool
gcloud container node-pools create new-gpu-pool-132 \
    --cluster=CLUSTER_NAME \
    --machine-type=a2-highgpu-1g \
    --node-version=1.32 \
    --reservation-affinity=specific \
    --reservation=RESERVATION_NAME

# 3. Migrate workloads
kubectl cordon -l node-pool=old-gpu-pool
# Drain nodes in batches
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data

# 4. Delete old pool and resize reservation back
```

### Option 3: Staged Upgrade (Best for Large Clusters)
```bash
# Upgrade in smaller batches
gcloud container node-pools upgrade GPU_POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=ZONE \
    --node-version=1.32 \
    --max-surge-upgrade=8 \
    --max-unavailable-upgrade=4
```

## Recommendations

1. **Use Option 1** unless you have specific requirements preventing in-place upgrades
2. **Test first** on a smaller subset if possible
3. **Plan for downtime** - GPU workloads often can't be easily rescheduled
4. **Monitor carefully** - GPU node upgrades take longer than CPU nodes
5. **Consider maintenance windows** - 128 A100s likely serve critical workloads

## Pre-upgrade Checklist
- [ ] Backup any local storage/models
- [ ] Verify workload tolerance for restarts
- [ ] Check if any pods use `hostNetwork` or local storage
- [ ] Ensure adequate PodDisruptionBudgets
- [ ] Plan communication to users about potential interruptions

The in-place upgrade is almost always better for reserved GPU nodes unless you have specific constraints requiring the blue-green approach.