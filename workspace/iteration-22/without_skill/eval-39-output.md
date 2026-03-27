Your proposed approach is actually **not ideal** for this scenario. Given that you have 128 A100 nodes with fixed reservations, here are better alternatives:

## Better Approaches

### 1. **In-Place Node Pool Upgrade (Recommended)**
```bash
gcloud container node-pools upgrade GPU_POOL_NAME \
  --cluster=CLUSTER_NAME \
  --zone=ZONE \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=0
```

**Why this is better:**
- Preserves your fixed reservations
- No risk of losing reserved capacity
- Automated process with built-in safety checks
- Can control upgrade pace with surge/unavailable settings

### 2. **Rolling Node Pool Replacement (If in-place fails)**
If you must create a new pool:

```bash
# 1. Create new pool with same reservation
gcloud container node-pools create gpu-pool-v132 \
  --cluster=CLUSTER_NAME \
  --machine-type=a2-highgpu-1g \
  --accelerator=type=nvidia-tesla-a100,count=1 \
  --reservation-affinity=specific \
  --reservation=YOUR_RESERVATION_NAME \
  --node-version=1.32.x

# 2. Gradually cordon and drain old nodes
kubectl cordon NODE_NAME
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --force
```

## Key Considerations for A100 Nodes

1. **Reservation Management**: Coordinate with your GCP account team to ensure reservations transfer properly
2. **Workload Disruption**: A100 workloads are typically long-running ML jobs - plan maintenance windows
3. **Resource Constraints**: You likely can't double your A100 allocation, so staged replacement is necessary
4. **Cost Impact**: Creating a parallel pool temporarily doubles costs

## Recommended Strategy

```bash
# Start with in-place upgrade with conservative settings
gcloud container node-pools upgrade gpu-pool \
  --cluster=my-cluster \
  --zone=us-central1-a \
  --max-surge-upgrade=2 \
  --max-unavailable-upgrade=0 \
  --node-pool-soak-duration=300s
```

This approach:
- Upgrades 2 nodes at a time
- Ensures no unavailable nodes during upgrade
- Includes soak time for validation
- Preserves your valuable A100 reservations

Only fall back to the new pool approach if in-place upgrades fail or if you need zero-downtime guarantees that require parallel pools.