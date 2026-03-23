# GKE Large Cluster Upgrade Optimization Plan

Based on your 600-node Standard cluster (2 CPU + 2 GPU pools), here's how to significantly reduce your upgrade time from 24+ hours to fit within your 8-hour maintenance window.

## Current bottleneck analysis

With GKE's maximum upgrade parallelism of ~20 nodes simultaneously, your 600-node cluster requires ~30 batches minimum. At 24+ hours total, you're averaging 45+ minutes per batch — indicating resource constraints, conservative surge settings, or PDB blocking.

## Optimization strategy

### 1. GPU pools: Switch to maxUnavailable mode (highest impact)
Your A100 pools with fixed reservations likely can't provision surge nodes. Switch to drain-first mode:

```bash
# Configure GPU pools for faster drain-first upgrades
gcloud container node-pools update GPU_POOL_1_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 3

gcloud container node-pools update GPU_POOL_2_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 3
```

**Rationale:** `maxUnavailable=3` upgrades 3 GPU nodes in parallel instead of 1. Since you have fixed reservations with no surge capacity, this is your primary speed lever. The temporary capacity dip is acceptable during maintenance windows.

### 2. CPU pools: Aggressive surge settings
Increase parallelism dramatically for your CPU pools:

```bash
# Configure CPU pools for maximum surge parallelism
gcloud container node-pools update CPU_POOL_1_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 10 \
  --max-unavailable-upgrade 0

gcloud container node-pools update CPU_POOL_2_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 10 \
  --max-unavailable-upgrade 0
```

**Rationale:** `maxSurge=10` per pool enables up to 20 CPU nodes upgrading simultaneously (hitting GKE's current parallelism limit). No capacity dip since maxUnavailable=0.

### 3. Use skip-level (N+2) node pool upgrades
When possible, upgrade node pools directly from version X to X+2, skipping the intermediate version:

```bash
# Example: skip from 1.31 → 1.33, bypassing 1.32
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.33.x-gke.xxxx
```

**Benefit:** Reduces total upgrade time by eliminating intermediate steps while maintaining version compatibility (nodes can be up to 2 minor versions behind control plane).

### 4. Stagger node pool upgrades strategically
Don't upgrade all 4 pools simultaneously. Sequence them to optimize resource utilization:

**Recommended sequence:**
1. **Start both CPU pools simultaneously** (they can handle surge)
2. **After CPU pools complete, start both GPU pools simultaneously** (during training gap)

### 5. Address PDB constraints
Check for overly restrictive PDBs that slow drain operations:

```bash
# Audit PDBs
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# Temporarily relax during maintenance (example)
kubectl patch pdb RESTRICTIVE_PDB -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"25%"}}'
```

### 6. Pre-upgrade workload preparation
**For GPU workloads:** Coordinate with ML teams to:
- Complete training runs before the maintenance window
- Apply "no minor or node upgrades" exclusion during active training campaigns
- Use checkpointing so jobs can resume post-upgrade

**For long-running services:** Ensure graceful termination:
- Set appropriate `terminationGracePeriodSeconds` (≤120s for most workloads)
- Remove bare pods that can't be rescheduled

## Expected time reduction

With these optimizations:
- **CPU pools:** ~300 nodes with maxSurge=10 each = 15 batches total (vs. 30 previously)
- **GPU pools:** ~300 nodes with maxUnavailable=3 each = 50 batches total (vs. 300 previously)
- **Estimated total time:** 4-6 hours (assuming 5-7 minutes per batch with optimized settings)

## Implementation runbook

```bash
# 1. Configure surge settings (do this before maintenance window)
gcloud container node-pools update CPU_POOL_1 --cluster CLUSTER --zone ZONE --max-surge-upgrade 10 --max-unavailable-upgrade 0
gcloud container node-pools update CPU_POOL_2 --cluster CLUSTER --zone ZONE --max-surge-upgrade 10 --max-unavailable-upgrade 0
gcloud container node-pools update GPU_POOL_1 --cluster CLUSTER --zone ZONE --max-surge-upgrade 0 --max-unavailable-upgrade 3
gcloud container node-pools update GPU_POOL_2 --cluster CLUSTER --zone ZONE --max-surge-upgrade 0 --max-unavailable-upgrade 3

# 2. During maintenance window - upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME --zone ZONE --master --cluster-version TARGET_VERSION

# 3. Start CPU pool upgrades simultaneously
gcloud container node-pools upgrade CPU_POOL_1 --cluster CLUSTER --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade CPU_POOL_2 --cluster CLUSTER --zone ZONE --cluster-version TARGET_VERSION &

# 4. Monitor CPU pool progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "CPU_POOL"'

# 5. After CPU pools complete, start GPU pools
gcloud container node-pools upgrade GPU_POOL_1 --cluster CLUSTER --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade GPU_POOL_2 --cluster CLUSTER --zone ZONE --cluster-version TARGET_VERSION &

# 6. Monitor overall progress
watch 'kubectl get nodes -o wide'
```

## Long-term considerations

**Future roadmap benefit:** GKE is increasing maximum node upgrade parallelism from ~20 to 100 nodes simultaneously. When this lands, your GPU pools with `maxUnavailable=10+` will see dramatic improvement.

**Alternative for critical speed:** Consider GKE's **autoscaled blue-green upgrade** strategy for GPU pools — it cordons the old pool and auto-scales replacement nodes, but requires 2x GPU capacity temporarily.

This optimization should bring your 600-node cluster upgrade well within your 8-hour maintenance window while maintaining workload availability.