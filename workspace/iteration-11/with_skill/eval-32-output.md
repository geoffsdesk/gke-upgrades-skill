# Large-Scale GKE Upgrade Plan: 3,000-Node Multi-GPU Cluster

Your upgrade timeouts are expected behavior for this scale. A 3,000-node cluster will take **days to weeks** to upgrade completely, not hours. Here's how to handle this properly:

## Core Issue Analysis

**GKE's upgrade parallelism limit:** ~20 nodes simultaneously regardless of `maxSurge` settings
- Your 3,000 nodes = ~150 batches minimum
- At 10-15 minutes per batch = 25-37 hours of pure upgrade time
- Plus GPU node constraints (no live migration, driver changes)
- Your 8-hour window can't accommodate this scale

## Recommended Strategy

### 1. Extend Your Maintenance Window (Primary Fix)

```bash
# Set 48-hour weekend maintenance window (Fri 6pm - Sun 6pm)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start 2025-01-17T18:00:00Z \
  --maintenance-window-end 2025-01-19T18:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=FR"
```

**Why 48 hours:** Large clusters routinely take 24-48 hours to upgrade. Weekend windows minimize business impact.

### 2. Staggered Node Pool Upgrade Sequence

Don't upgrade all pools simultaneously. Sequence them by priority and complexity:

**Phase 1: CPU pools first (lower risk)**
```bash
# Upgrade CPU pools with high parallelism
for POOL in cpu-pool-1 cpu-pool-2 cpu-pool-3 cpu-pool-4; do
  gcloud container node-pools update $POOL \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 5 \
    --max-unavailable-upgrade 0
  
  gcloud container node-pools upgrade $POOL \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version TARGET_VERSION
  
  echo "Started upgrade for $POOL - waiting 4 hours before next pool"
  sleep 14400  # 4 hour spacing
done
```

**Phase 2: GPU pools during training gaps**
```bash
# GPU pools with conservative settings (assume no surge capacity)
for POOL in t4-pool l4-pool a100-pool h100-pool; do
  gcloud container node-pools update $POOL \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 2  # Increase for faster completion
  
  gcloud container node-pools upgrade $POOL \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version TARGET_VERSION
  
  echo "Started upgrade for $POOL - waiting 6 hours before next GPU pool"
  sleep 21600  # 6 hour spacing
done
```

### 3. GPU-Specific Protections

**For active training workloads:**
```bash
# Add "no minor or node upgrades" exclusion during training campaigns
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-q1" \
  --add-maintenance-exclusion-start-time 2025-02-01T00:00:00Z \
  --add-maintenance-exclusion-end-time 2025-04-01T00:00:00Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**Dedicated training pool strategy:**
- Consider separate node pools for long-running training vs. inference
- Training pools: auto-upgrade disabled, manual upgrade during scheduled gaps
- Inference pools: auto-upgrade enabled with surge settings

### 4. Monitoring Large Upgrades

```bash
# Real-time upgrade progress tracking
watch 'echo "=== Node Status ===" && kubectl get nodes -L cloud.google.com/gke-nodepool | grep -E "(NotReady|SchedulingDisabled)" | wc -l && echo "=== Pool Status ===" && gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE --format="table(name,version,status)"'

# Check for stuck operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES AND status=RUNNING"
```

## Alternative: Blue-Green for GPU Pools (If You Have Capacity)

If you have sufficient GPU quota for 2x capacity:

```bash
# Use GKE's autoscaled blue-green upgrade for GPU pools
gcloud container node-pools update H100_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaled-blue-green-upgrade
```

This cordons the old pool and auto-scales replacement nodes, but requires doubling your H100/A100 capacity temporarily.

## Immediate Action Plan

1. **This weekend:** Extend your maintenance window to 48 hours (Friday 6pm - Sunday 6pm)

2. **Control plane first:**
   ```bash
   gcloud container clusters upgrade CLUSTER_NAME \
     --zone ZONE \
     --master \
     --cluster-version TARGET_VERSION
   ```

3. **Stagger node pools:** Start with CPU pools, wait for completion, then GPU pools

4. **Set realistic expectations:** Brief stakeholders that large-scale upgrades take days, not hours

## Long-Term Optimizations

- **Consider cluster sharding:** 3,000 nodes approaches GKE's practical limits. Consider splitting into 2-3 smaller clusters (1,000 nodes each) for faster, more manageable upgrades
- **Evaluate Extended release channel:** For more control over upgrade timing and 24-month support periods
- **Implement rollout sequencing:** For multi-cluster environments to automate the upgrade orchestration

## Key Takeaway

**Your 8-hour window is the constraint, not GKE.** Large GPU clusters fundamentally require extended maintenance windows. This is normal and expected behavior at your scale.

Would you like me to create specific runbooks for the CPU-first, GPU-second sequencing strategy?