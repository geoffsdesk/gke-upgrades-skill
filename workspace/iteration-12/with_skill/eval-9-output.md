# Large Cluster Node Pool Upgrade Optimization

## Current bottleneck analysis

For your 600-node cluster, GKE's maximum upgrade parallelism is ~20 nodes simultaneously (increasing to 100 in the roadmap). With 4 node pools upgraded sequentially, you're looking at:
- 600 nodes ÷ 20 parallel = 30 batches minimum
- ~5-10 minutes per batch = 2.5-5 hours per pool
- 4 pools × 4 hours average = 16+ hours total

This exceeds your 8-hour weekend window.

## Speed optimization strategy

### 1. Configure optimal surge settings per pool type

**CPU pools (assume 200 nodes each):**
```bash
# Pool 1 & 2: Aggressive surge for stateless workloads
gcloud container node-pools update cpu-pool-1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 10 \
  --max-unavailable-upgrade 0

# 10 = 5% of 200 nodes, within the ~20 node batch limit
# This maximizes parallelism while avoiding capacity dip
```

**GPU pools (assume 100 nodes each with A100 reservations):**
```bash
# GPU pools: Use maxUnavailable since you have fixed reservations (no surge capacity)
gcloud container node-pools update gpu-pool-1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 5

# Start conservative with 5, increase to 10 if capacity allows
# This drains first (no extra GPUs needed) but creates temporary capacity reduction
```

### 2. Skip-level upgrades where possible

If your node pools are multiple versions behind the control plane:
```bash
# Check current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Skip-level upgrade (within 2-version skew limit)
# Example: 1.28 → 1.30 instead of 1.28 → 1.29 → 1.30
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

### 3. Stagger pool upgrades across multiple maintenance windows

Don't try to upgrade all pools in one window. Prioritize by criticality:

**Weekend 1 (8-hour window):**
- CPU pools first (they're faster and have surge capacity)
- Both CPU pools can run concurrently if you have sufficient compute quota

**Weekend 2 (8-hour window):**
- GPU pools during scheduled training gaps
- Consider upgrading GPU pools when training jobs are between campaigns

### 4. Use maintenance exclusions for training protection

```bash
# Block auto-upgrades on GPU pools during active training
gcloud container node-pools update gpu-pool-1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-q1" \
  --add-maintenance-exclusion-start-time "2024-02-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-03-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### 5. Consider blue-green for GPU pools

If you can secure temporary additional GPU capacity:
```bash
# Only if you have confirmed GPU surge quota available
gcloud container node-pools update gpu-pool-1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 50 --total-max-nodes 150 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.5,blue-green-full-batch-timeout=7200s
```

**Warning:** Most customers with fixed GPU reservations don't have surge capacity. Only use this if you've confirmed additional A100 quota.

## Recommended upgrade runbook

### Pre-flight optimization
```bash
# 1. Verify current pool configurations
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# 2. Set optimal surge settings (do this before the maintenance window)
# CPU pools: maxSurge=10, maxUnavailable=0
# GPU pools: maxSurge=0, maxUnavailable=5

# 3. Check for PDB conflicts that could slow draining
kubectl get pdb -A -o wide
# Look for overly restrictive PDBs (ALLOWED DISRUPTIONS = 0)
```

### Weekend 1: CPU pools
```bash
# Upgrade both CPU pools simultaneously (if quota allows)
gcloud container node-pools upgrade cpu-pool-1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION &

gcloud container node-pools upgrade cpu-pool-2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION &

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "cpu-pool"'
```

### Weekend 2: GPU pools (during training gap)
```bash
# Checkpoint training jobs first
# Then upgrade GPU pools with maxUnavailable strategy

gcloud container node-pools upgrade gpu-pool-1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION

# Monitor for any stuck nodes due to PDB conflicts
kubectl get pods -A | grep -E "gpu-pool.*Terminating"
```

## Time reduction estimate

With these optimizations:
- **CPU pools:** 200 nodes ÷ 20 parallel = 10 batches × 5 min = ~50 minutes each (both can run concurrently)
- **GPU pools:** 100 nodes ÷ 5 unavailable = 20 batches × 8 min = ~2.5 hours each
- **Total per weekend:** 3-4 hours instead of 16+ hours

This fits comfortably within your 8-hour windows while respecting GPU capacity constraints.

## Long-term considerations

1. **Upcoming parallelism increase:** GKE is increasing maximum upgrade parallelism to 100 nodes, which will significantly speed up your large cluster upgrades
2. **Release channel + maintenance windows:** Consider moving critical pools to Stable channel with "no minor or node upgrades" exclusions for maximum control
3. **Cluster segmentation:** For future scaling, consider splitting into separate clusters by workload type (CPU inference, GPU training, GPU inference)

Would you like me to adjust this strategy based on your specific node pool sizes or training schedule?