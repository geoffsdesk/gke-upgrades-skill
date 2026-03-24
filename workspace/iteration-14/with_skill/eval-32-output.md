# Large-Scale GKE Upgrade Strategy (3,000 nodes)

## Core issue analysis

Your upgrades are timing out because **GKE's maximum upgrade parallelism is ~20 nodes simultaneously** regardless of `maxSurge` settings. With 3,000 nodes, you're looking at ~150 batches minimum — far exceeding your 8-hour window.

**Calculation:** 3,000 nodes ÷ 20 nodes/batch × ~5-10 min/batch = 12.5-25 hours minimum upgrade time

Your Saturday 2am-10am window (8 hours) is fundamentally insufficient for this cluster size.

## Recommended solution: Staggered multi-weekend approach

### Weekend 1: CPU pools only
**Saturday 2am-10am:** Upgrade all 4 CPU node pools first. CPU pools upgrade faster than GPU pools (no driver concerns, typically more surge capacity available).

**Commands:**
```bash
# Configure CPU pools for optimal surge (assuming surge capacity exists)
for POOL in cpu-pool-1 cpu-pool-2 cpu-pool-3 cpu-pool-4; do
  gcloud container node-pools update $POOL \
    --cluster YOUR_CLUSTER_NAME \
    --zone YOUR_ZONE \
    --max-surge-upgrade 5% \
    --max-unavailable-upgrade 0
done

# Upgrade CPU pools sequentially (not simultaneously)
gcloud container node-pools upgrade cpu-pool-1 --cluster YOUR_CLUSTER_NAME --zone YOUR_ZONE --cluster-version TARGET_VERSION
# Wait for completion, then next pool...
```

### Weekend 2: GPU pools (critical considerations)
**Saturday 2am:** Start with L4/T4 pools (easier to get surge capacity)  
**Saturday 6am:** H100/A100 pools (most constrained)

**GPU-specific strategy:**
```bash
# GPU pools likely have NO surge capacity — use drain-first approach
for GPU_POOL in l4-pool t4-pool h100-pool a100-pool; do
  gcloud container node-pools update $GPU_POOL \
    --cluster YOUR_CLUSTER_NAME \
    --zone YOUR_ZONE \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 2
done
```

**Key insight:** `maxUnavailable` is your PRIMARY lever for GPU pools. Increase to 2-4 nodes if your training/inference workloads can tolerate temporary capacity loss.

## GPU pool upgrade constraints

Your GPU pools face unique challenges:
- **No surge capacity:** A100/H100 reservations typically have zero headroom
- **Driver coupling:** GKE auto-installs GPU drivers matching the target version — this can change CUDA versions
- **Longer restart times:** GPU VMs don't support live migration

**Pre-upgrade validation:**
```bash
# Check if GPU reservation has any available headroom
gcloud compute reservations describe YOUR_GPU_RESERVATION --zone YOUR_ZONE

# Test GPU driver compatibility in a staging cluster first
# Target GKE version may ship different CUDA version than current
```

## Training job protection strategy

For your GPU clusters, you likely have long-running training jobs that cannot tolerate mid-job eviction:

### Option A: Maintenance exclusions during training campaigns
```bash
# Block ALL node pool upgrades while preserving control plane patches
gcloud container clusters update YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "training-campaign-Q1" \
  --add-maintenance-exclusion-start-time 2024-01-15T00:00:00Z \
  --add-maintenance-exclusion-end-time 2024-03-31T23:59:59Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### Option B: Dedicated training pools with per-nodepool exclusions
```bash
# Block upgrades on training-specific pools only
gcloud container node-pools update a100-training-pool \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Maintenance window expansion

**Extend your window to 16+ hours:**
```bash
gcloud container clusters update YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --maintenance-window-start 2024-01-06T02:00:00Z \
  --maintenance-window-end 2024-01-06T18:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

Or use **Friday night → Sunday morning** for maximum time:
```bash
--maintenance-window-start 2024-01-05T22:00:00Z \
--maintenance-window-end 2024-01-07T06:00:00Z
```

## Alternative: Custom blue-green for GPU pools

If your GPU reservations have 2x capacity available, use GKE's blue-green upgrade strategy:

```bash
# Only if you have capacity for 2x GPU nodes temporarily
gcloud container node-pools update h100-pool \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --blue-green-upgrade
```

This keeps old nodes available during upgrade, enabling faster rollback but requires doubling your GPU reservation temporarily.

## Monitoring large upgrades

**Track progress across all pools:**
```bash
# Monitor upgrade operations
watch 'gcloud container operations list --cluster YOUR_CLUSTER_NAME --zone YOUR_ZONE --filter="operationType=UPGRADE_NODES"'

# Node version distribution
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | sort -k6'

# Pods affected by drain
kubectl get pods -A | grep -E "Terminating|Pending"
```

## Summary approach

1. **Weekend 1:** CPU pools only (4 pools, ~8 hours)
2. **Weekend 2:** GPU pools with drain-first strategy (`maxUnavailable=2-4`)
3. **Expand maintenance windows** to 16+ hours
4. **Use maintenance exclusions** to protect active training campaigns
5. **Test GPU driver compatibility** in staging before production GPU upgrades

This splits your 25-hour upgrade across two weekends while respecting GPU constraints and training job protection.

Would you like me to detail the specific commands for your GPU reservation setup or training job protection strategy?