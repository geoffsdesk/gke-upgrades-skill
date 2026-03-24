Your described approach is actually **not optimal** for your specific situation. Here's why and what you should do instead:

## Problems with the Manual Approach

1. **Reservation conflicts**: Creating a new 128-node pool while the old one exists will likely fail due to quota/reservation constraints
2. **Unnecessary complexity**: Manual cordoning/draining is error-prone at scale
3. **Extended downtime**: Sequential approach takes much longer than necessary

## Better Approaches

### Option 1: Rolling Node Pool Upgrade (Recommended)
```bash
# Enable rolling upgrades on your existing pool
gcloud container node-pools update POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=ZONE \
    --node-version=1.32.x \
    --max-surge=10 \
    --max-unavailable=5
```

**Benefits:**
- Uses your existing reservations efficiently
- Automated process with built-in safety checks
- Gradual replacement minimizes service disruption
- Can tune surge/unavailable parameters based on your workload tolerance

### Option 2: Blue-Green with Smaller Batches
If you must use the new pool approach:

```bash
# Create smaller pool first (e.g., 32 nodes)
gcloud container node-pools create new-pool-batch1 \
    --cluster=CLUSTER_NAME \
    --node-version=1.32.x \
    --num-nodes=32 \
    --machine-type=a2-highgpu-1g

# Migrate workloads in batches
# Then expand new pool and shrink old pool iteratively
```

### Option 3: In-Place Upgrade (If Acceptable)
```bash
# Upgrade node pool in-place (involves recreating nodes)
gcloud container node-pools upgrade POOL_NAME \
    --cluster=CLUSTER_NAME
```

## Recommended Strategy

For your GPU workload, I'd suggest **Option 1 (Rolling Upgrade)** because:

- **Reservation efficiency**: Reuses your fixed A100 reservations
- **Workload-aware**: Respects PodDisruptionBudgets
- **Automated rollback**: Can revert if issues arise
- **Cost-effective**: No double resource allocation

## Pre-upgrade Checklist

```bash
# 1. Verify current state
kubectl get nodes -l cloud.google.com/gke-nodepool=YOUR_POOL

# 2. Check workload disruption budgets
kubectl get pdb --all-namespaces

# 3. Backup critical workload configs
kubectl get deployments,statefulsets -o yaml > workloads-backup.yaml

# 4. Set appropriate surge parameters based on your tolerance
```

Would you like me to help you implement the rolling upgrade approach, or do you have specific constraints that make the manual approach necessary?