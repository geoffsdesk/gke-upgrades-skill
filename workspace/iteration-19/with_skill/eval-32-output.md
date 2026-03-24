# Large-Scale GKE Upgrade Plan: 3,000-Node Multi-Pool Cluster

## Core Challenge Analysis

Your 8-hour maintenance window is **insufficient** for upgrading 3,000 nodes. Here's why:
- **GKE's maximum upgrade parallelism:** ~20 nodes simultaneously (increasing to 100 in roadmap)
- **3,000 nodes ÷ 20 = 150 batches minimum**
- **Each batch cycle:** 5-10 minutes (cordon → drain → delete → create → ready)
- **Total time estimate:** 12-25 hours for all pools

## Recommended Strategy: Staggered Multi-Weekend Approach

### Phase 1: Extend Maintenance Windows
```bash
# Extend to 20-hour window (Friday 6pm - Saturday 2pm)
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --maintenance-window-start "2024-01-05T18:00:00Z" \
    --maintenance-window-duration 20h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=FR"
```

### Phase 2: Pool Priority & Sequencing

**Weekend 1: CPU Pools Only (lower risk)**
```bash
# Apply exclusion to block GPU pool upgrades
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "gpu-pool-freeze" \
    --add-maintenance-exclusion-start-time "2024-01-05T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-01-05T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
```

Apply per-nodepool exclusions to GPU pools:
```bash
# Block each GPU pool individually
for POOL in gpu-a100-pool gpu-h100-pool gpu-l4-pool gpu-t4-pool; do
    gcloud container node-pools update $POOL \
        --cluster CLUSTER_NAME \
        --zone ZONE \
        --no-enable-autoupgrade
done
```

**Weekend 2: GPU Pools (planned capacity gaps)**

## GPU Pool Upgrade Strategy

**Critical constraint:** Your GPU pools likely have **fixed reservations with no surge capacity**. Use drain-first strategy:

```bash
# GPU pools configuration (no surge capacity available)
for POOL in gpu-a100-pool gpu-h100-pool gpu-l4-pool gpu-t4-pool; do
    gcloud container node-pools update $POOL \
        --cluster CLUSTER_NAME \
        --zone ZONE \
        --max-surge-upgrade 0 \
        --max-unavailable-upgrade 2  # Adjust based on training sensitivity
done
```

**GPU upgrade timing considerations:**
- **Training job coordination:** Cordon GPU pools → wait for training jobs to complete naturally → upgrade empty pools
- **Inference workload protection:** Use autoscaled blue-green if you have capacity for replacement nodes
- **Driver compatibility:** Verify target GKE version + GPU driver combination in staging first

## Optimize Upgrade Speed

### 1. Increase maxUnavailable (where workload-appropriate)
```bash
# CPU pools - stateless workloads can tolerate higher unavailability
gcloud container node-pools update cpu-pool-1 \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 5 \
    --max-unavailable-upgrade 2

# GPU pools - limited by fixed reservations
gcloud container node-pools update gpu-a100-pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 3  # Higher if training can tolerate gaps
```

### 2. Skip-Level Node Pool Upgrades
After control plane reaches target version, upgrade node pools with **skip-level jumps** (within 2-version skew):
```bash
# Example: CP at 1.33, nodes at 1.31 → upgrade directly to 1.33
gcloud container node-pools upgrade NODE_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version 1.33.x-gke.xxx  # Skip 1.32 entirely
```

### 3. Pre-upgrade Workload Optimization
**Week before upgrade:**
- Scale down non-critical dev/test workloads: `kubectl scale deployment NON_CRITICAL_APP --replicas=0`
- Pause batch job submissions 2 hours before maintenance window
- Set cluster autoscaler to conservative scaling during upgrade window

## Maintenance Exclusion Strategy

**For maximum control with your complex environment:**
```bash
# Use "no minor or node upgrades" exclusion as your primary control
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support \
    --maintenance-minor-version-disruption-interval=2592000s  # 30 days between minors
```

This gives you:
- **Control plane patches automatically applied** (security)
- **Manual control over when minor upgrades happen**
- **Manual control over when node pool upgrades happen**
- **No 30-day time limit** (tracks End of Support automatically)

## Progressive Upgrade Runbook

### Pre-Weekend Preparation
```bash
# 1. Verify staging cluster upgraded successfully
# 2. Check GPU driver compatibility with target version
# 3. Scale down non-critical workloads
kubectl scale deployment dev-app-1 dev-app-2 --replicas=0

# 4. Pause batch job submissions
# 5. Configure conservative PDBs for critical services
```

### Weekend 1: CPU Pools
```bash
# Friday 6pm: Start control plane upgrade
gcloud container clusters upgrade CLUSTER_NAME \
    --zone ZONE \
    --master \
    --cluster-version TARGET_VERSION

# Saturday 2am: CPU pools (after CP upgrade completes)
for POOL in cpu-pool-1 cpu-pool-2 cpu-pool-3 cpu-pool-4; do
    echo "Starting upgrade: $POOL"
    gcloud container node-pools upgrade $POOL \
        --cluster CLUSTER_NAME \
        --zone ZONE \
        --cluster-version TARGET_VERSION
    
    # Monitor progress before starting next pool
    watch 'kubectl get nodes -l cloud.google.com/gke-nodepool='$POOL' -o wide'
done
```

### Weekend 2: GPU Pools
```bash
# Coordinate with ML teams for training job gaps
# Wait for active training jobs to complete or checkpoint

for POOL in gpu-t4-pool gpu-l4-pool gpu-a100-pool gpu-h100-pool; do
    echo "Cordoning GPU pool: $POOL"
    kubectl cordon -l cloud.google.com/gke-nodepool=$POOL
    
    # Wait for workloads to drain naturally (respects long-running jobs)
    echo "Waiting for $POOL to drain..."
    
    # Start upgrade when pool is empty
    gcloud container node-pools upgrade $POOL \
        --cluster CLUSTER_NAME \
        --zone ZONE \
        --cluster-version TARGET_VERSION
done
```

## Alternative: Migrate to Extended Channel

For future upgrades, consider **Extended release channel** for maximum control:
```bash
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --release-channel extended
```

**Extended channel benefits for your use case:**
- **Up to 24 months of support** per version
- **No automatic minor version upgrades** (only patches auto-applied)
- **You control when minor upgrades happen** — plan around training campaigns
- **Only costs extra during the extended support period** (months 15-24)

## Monitoring During Upgrade

```bash
# Track overall progress
watch 'gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE'

# Monitor stuck pods
kubectl get pods -A | grep -E "Terminating|Pending|ContainerCreating"

# Check PDB violations
kubectl get events -A --field-selector reason=EvictionBlocked

# GPU-specific: verify driver loading on new nodes
kubectl get nodes -l accelerator=nvidia-tesla-a100 -o wide
```

## Rollback Strategy

**If upgrade fails mid-stream:**
```bash
# Cancel remaining operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE
# Note: Cannot rollback already-upgraded nodes in-place

# For GPU pools: Create new pool at previous version if needed
gcloud container node-pools create gpu-a100-rollback \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version PREVIOUS_VERSION \
    --accelerator type=nvidia-tesla-a100,count=8 \
    --machine-type a2-highgpu-8g
```

## Key Recommendations

1. **Split across 2-3 weekends** — don't attempt all 3,000 nodes in one window
2. **GPU pools need special planning** — coordinate with ML teams for training gaps
3. **Use skip-level node upgrades** — reduces total upgrade cycles
4. **Monitor PDBs closely** — your primary failure point at scale
5. **Consider Extended channel** — gives you 24 months to plan major upgrades around training schedules

**Timeline estimate with this approach:**
- Weekend 1: 4 CPU pools (~1,500 nodes) in 15-20 hours
- Weekend 2: 4 GPU pools (~1,500 nodes) in 10-15 hours (accounting for drain-first strategy)

This spreads the risk and gives you validation time between phases.