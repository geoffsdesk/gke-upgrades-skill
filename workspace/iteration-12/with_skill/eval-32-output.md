# Large-Scale GKE Upgrade Plan for 3,000-Node Cluster

You're hitting GKE's maximum upgrade parallelism limit (~20 nodes simultaneously) combined with an insufficient maintenance window. Here's how to handle upgrades at your scale:

## Core Problem Analysis

- **3,000 nodes ÷ 20 parallel upgrades = 150 batches minimum**
- **At ~5 minutes per batch = 12.5+ hours for node upgrades alone**
- **Your 8-hour window is insufficient for completion**
- **GPU pools have additional constraints (no surge capacity, driver changes)**

## Recommended Approach: Staged Multi-Weekend Strategy

### Phase 1: Control Plane (Weekend 1)
```bash
# Upgrade control plane first (separate from node pools)
gcloud container clusters upgrade YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --master \
  --cluster-version TARGET_VERSION

# Verify CP upgrade success
gcloud container clusters describe YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --format="value(currentMasterVersion)"
```

### Phase 2: CPU Pools (Weekend 2-3)
Prioritize CPU pools — they're more flexible and less constrained:

```bash
# Configure aggressive surge for CPU pools
for pool in cpu-pool-1 cpu-pool-2 cpu-pool-3 cpu-pool-4; do
  gcloud container node-pools update $pool \
    --cluster YOUR_CLUSTER \
    --zone YOUR_ZONE \
    --max-surge-upgrade 3 \
    --max-unavailable-upgrade 0
done

# Upgrade CPU pools (can do multiple pools simultaneously)
gcloud container node-pools upgrade cpu-pool-1 \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --cluster-version TARGET_VERSION &

gcloud container node-pools upgrade cpu-pool-2 \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --cluster-version TARGET_VERSION &

# Wait for completion, then next batch
```

### Phase 3: GPU Pools (Weekend 4-5)
GPU pools require special handling:

```bash
# GPU pools: Use maxUnavailable (assume no surge capacity)
for pool in a100-pool h100-pool l4-pool t4-pool; do
  gcloud container node-pools update $pool \
    --cluster YOUR_CLUSTER \
    --zone YOUR_ZONE \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 2
done

# Upgrade GPU pools ONE AT A TIME (not parallel)
# This prevents competing for scarce GPU capacity
gcloud container node-pools upgrade a100-pool \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --cluster-version TARGET_VERSION

# Wait for A100 completion, then H100, etc.
```

## Extended Maintenance Window Strategy

### Option 1: Expand Weekend Window
```bash
# Extend to Friday 10pm - Sunday 6am (32 hours)
gcloud container clusters update YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --maintenance-window-start 2024-12-06T22:00:00Z \
  --maintenance-window-end 2024-12-08T06:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=FR"
```

### Option 2: Weeknight Gradualism
```bash
# Nightly 4-hour windows for incremental progress
gcloud container clusters update YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --maintenance-window-start 2024-12-06T02:00:00Z \
  --maintenance-window-end 2024-12-06T06:00:00Z \
  --maintenance-window-recurrence "FREQ=DAILY;BYDAY=MO,TU,WE,TH,FR"

# Use maintenance exclusions to control scope per night
gcloud container clusters update YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "limit-to-cpu-pools" \
  --add-maintenance-exclusion-start-time 2024-12-06T00:00:00Z \
  --add-maintenance-exclusion-end-time 2024-12-06T23:59:59Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

## GPU-Specific Considerations

### Driver Compatibility Check
```bash
# Test GPU driver compatibility in a staging cluster first
# GKE auto-installs drivers matching the target version
kubectl get nodes -l node.kubernetes.io/instance-type=a100-80gb -o yaml | \
  grep -E "nvidia.com|cuda"

# Verify CUDA version compatibility with your ML frameworks
nvidia-smi --query-gpu=driver_version,cuda_version --format=csv
```

### Training Job Protection
```bash
# Block upgrades during active training campaigns
gcloud container clusters update YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "training-campaign-q1" \
  --add-maintenance-exclusion-start-time 2024-12-01T00:00:00Z \
  --add-maintenance-exclusion-end-time 2025-03-31T23:59:59Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Or use per-nodepool exclusions for training-specific pools
gcloud container node-pools update h100-training-pool \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "no-upgrades-training" \
  --add-maintenance-exclusion-start-time 2024-12-01T00:00:00Z \
  --add-maintenance-exclusion-end-time 2025-01-15T23:59:59Z \
  --add-maintenance-exclusion-scope no_upgrades
```

## Monitoring Large Upgrades

### Progress Tracking
```bash
# Monitor upgrade across all pools
watch 'gcloud container node-pools list --cluster YOUR_CLUSTER --zone YOUR_ZONE --format="table(name,version,status)"'

# Track operations
gcloud container operations list --cluster YOUR_CLUSTER --zone YOUR_ZONE --limit=10

# Node readiness by pool
kubectl get nodes -L cloud.google.com/gke-nodepool -L kubernetes.io/arch
```

### Capacity Monitoring
```bash
# Ensure sufficient quota for surge operations
gcloud compute project-info describe --format="yaml(quotas)" | \
  grep -E "CPUS|NVIDIA_"

# Check GPU utilization during upgrade
kubectl top nodes -l node.kubernetes.io/instance-type=nvidia-tesla-a100
```

## Recommended Timeline

**Week 1:** Control plane upgrade  
**Week 2:** CPU pools 1-2 (high maxSurge)  
**Week 3:** CPU pools 3-4 (high maxSurge)  
**Week 4:** GPU pools L4/T4 (maxUnavailable mode)  
**Week 5:** GPU pools A100/H100 (maxUnavailable mode, one at a time)  

## Alternative: Cluster Recreation Strategy

For future upgrades, consider:
1. **Blue-green at cluster level**: Create new 3,000-node cluster at target version
2. **Workload migration**: Migrate applications pool by pool
3. **DNS cutover**: Switch traffic to new cluster
4. **Decommission old cluster**

This eliminates upgrade time constraints entirely and provides fastest rollback (DNS switch).

## Key Takeaways

- **Your 8-hour window is mathematically insufficient** for 3,000 nodes
- **Split control plane and node pool upgrades** across multiple weekends
- **GPU pools need special handling** — no surge capacity, driver changes
- **Consider cluster-level blue-green** for future large-scale upgrades
- **Use maintenance exclusions** to protect active training workloads

Would you like me to detail the cluster recreation strategy or help with specific GPU driver compatibility testing?