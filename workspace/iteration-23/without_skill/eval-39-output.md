Your described approach is actually **not optimal** for your scenario. Here's why and what you should do instead:

## Problems with the Manual Approach

1. **Breaks reservation affinity** - Creating a new node pool may not honor your existing fixed reservations
2. **Potential quota issues** - Temporarily doubling your A100 allocation (256 GPUs) may exceed quotas
3. **Unnecessary complexity** - Manual draining of 128 GPU nodes is time-consuming and error-prone
4. **Workload disruption** - Longer downtime during the manual process

## Better Approaches

### Option 1: In-Place Node Pool Upgrade (Recommended)
```bash
# Check if your node pool supports in-place upgrades
gcloud container node-pools describe GPU_POOL_NAME \
  --cluster=CLUSTER_NAME --zone=ZONE

# Perform rolling upgrade (maintains reservations)
gcloud container node-pools upgrade GPU_POOL_NAME \
  --cluster=CLUSTER_NAME \
  --zone=ZONE \
  --node-version=1.32.x-gke.xxx
```

### Option 2: Controlled Rolling Update
If in-place upgrade isn't available:
```bash
# Update node pool configuration to trigger rolling replacement
gcloud container node-pools update GPU_POOL_NAME \
  --cluster=CLUSTER_NAME \
  --zone=ZONE \
  --node-version=1.32.x-gke.xxx
```

### Option 3: Blue-Green with Reservation Management
If you must use the blue-green approach:

1. **Before starting** - Contact Google Cloud Support to:
   - Temporarily increase your A100 quota
   - Ensure new node pool will use your reservations

2. **Create new pool with reservation targeting**:
```bash
gcloud container node-pools create gpu-pool-v132 \
  --cluster=CLUSTER_NAME \
  --reservation-affinity=specific \
  --reservation=YOUR_RESERVATION_NAME \
  --node-version=1.32.x-gke.xxx
```

## Recommendations

1. **Start with Option 1** - Most node pools support in-place upgrades
2. **Test first** - Try with a small subset if possible
3. **Monitor closely** - GPU workloads can be sensitive to node restarts
4. **Plan maintenance windows** - Even rolling updates cause some disruption

The key insight is that GKE's built-in upgrade mechanisms are designed to handle exactly your scenario while preserving reservations and minimizing disruption.