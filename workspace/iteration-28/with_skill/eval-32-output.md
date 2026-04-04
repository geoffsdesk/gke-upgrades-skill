# Large-Scale GKE Upgrade Strategy (3,000 Nodes)

You're hitting GKE's inherent upgrade parallelism limits. With 3,000 nodes and an 8-hour window, you need a fundamentally different approach than standard small-cluster upgrades.

## Core Problem

- **GKE upgrades ~20 nodes simultaneously** regardless of `maxSurge` settings
- **3,000 nodes ÷ 20 = ~150 batches minimum**
- **At 5-10 min per batch = 12-25 hours minimum** (exceeds your 8h window)
- **GPU pools can't use surge** (fixed reservations have no extra capacity)

## Recommended Multi-Weekend Strategy

### Weekend 1: Control Plane + CPU Pools

**Saturday 2-10am: Control plane + non-GPU pools only**

```bash
# 1. Control plane upgrade (15-30 min)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# 2. CPU pools only (prioritize largest pools first)
# Configure for maximum safe parallelism
for POOL in cpu-pool-1 cpu-pool-2 cpu-pool-3 cpu-pool-4; do
  gcloud container node-pools update $POOL \
    --cluster CLUSTER_NAME --zone ZONE \
    --max-surge-upgrade 5% --max-unavailable-upgrade 0
  
  gcloud container node-pools upgrade $POOL \
    --cluster CLUSTER_NAME --zone ZONE \
    --cluster-version TARGET_VERSION &
done
wait
```

**Why CPU first:** No reservation constraints, surge capacity available, lower risk workloads.

### Weekend 2: GPU Pools

**Saturday 2-10am: GPU pools with drain-first strategy**

```bash
# GPU pools: maxSurge=0, use maxUnavailable as the lever
for POOL in a100-pool h100-pool l4-pool t4-pool; do
  gcloud container node-pools update $POOL \
    --cluster CLUSTER_NAME --zone ZONE \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 2  # Increase for faster upgrades
  
  gcloud container node-pools upgrade $POOL \
    --cluster CLUSTER_NAME --zone ZONE \
    --cluster-version TARGET_VERSION &
done
```

**GPU pool considerations:**
- **maxUnavailable=2-4** for larger pools (faster but more capacity loss)
- **Stagger T4/L4 before A100/H100** (inference before training)
- **Coordinate with training teams** — pause long-running jobs

## Alternative: Extended Maintenance Windows

**Option A: 24-hour window**
```bash
# Friday 10pm - Saturday 10pm
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-05T22:00:00Z" \
  --maintenance-window-end "2024-01-06T22:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=FR"
```

**Option B: Multi-day progression with exclusions**
```bash
# Block auto-upgrades, do manual staged upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_upgrades \
  --add-maintenance-exclusion-start-time YYYY-MM-DDTHH:MM:SSZ \
  --add-maintenance-exclusion-end-time YYYY-MM-DDTHH:MM:SSZ

# Then manually upgrade pools across multiple weekends
```

## GPU-Specific Optimizations

### For Training Workloads (A100/H100)
```bash
# Use maintenance exclusions to protect active training
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Upgrade only during planned training gaps
```

### For Inference Workloads (L4/T4)
```bash
# Consider autoscaled blue-green for zero-downtime inference
gcloud container node-pools update l4-inference-pool \
  --cluster CLUSTER_NAME --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 10 --total-max-nodes 50 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25
```

## Monitoring Large Upgrades

**Track progress across all pools:**
```bash
#!/bin/bash
while true; do
  echo "=== $(date) ==="
  kubectl get nodes -o wide | grep -E "NAME|Ready" | \
    awk '{print $1, $5}' | sort | uniq -c
  echo ""
  gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=10
  sleep 300  # Check every 5 minutes
done
```

**Set up alerts for stuck upgrades:**
```bash
# Monitor for nodes stuck in NotReady > 30 minutes
kubectl get nodes --no-headers | \
  awk '$2 != "Ready" {print $1}' | \
  xargs kubectl describe nodes | \
  grep -A5 -B5 "NotReady"
```

## Preventing Future Timeouts

### 1. Use Smaller Node Pools
- **Split large pools** — 8 pools of 375 nodes vs 4 pools of 750 nodes
- **Upgrade smaller pools in parallel** instead of sequential large pools

### 2. Implement Disruption Intervals
```bash
# Slow down auto-upgrades to spread across multiple windows
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-minor-version-disruption-interval=7776000s  # 90 days
  --maintenance-patch-version-disruption-interval=2592000s   # 30 days
```

### 3. Use "No Minor or Node" Exclusions for Control
```bash
# Block auto-upgrades, do planned manual upgrades quarterly
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Risk Mitigation

**Before each upgrade weekend:**
- [ ] GPU driver compatibility tested in staging cluster
- [ ] Training checkpoints completed and verified
- [ ] Inference model warmup time measured
- [ ] PDBs reviewed for overly restrictive settings
- [ ] On-call team expanded for multi-pool monitoring

**During upgrades:**
- [ ] Monitor each pool's progress independently
- [ ] Ready to cancel individual pool upgrades if issues arise
- [ ] GPU reservation headroom confirmed before starting

**Emergency rollback plan:**
- Create new pools at previous version
- Cordon upgraded pools experiencing issues
- Migrate critical workloads back

## Summary

Your 8-hour window is physically insufficient for 3,000 nodes. Use either:
1. **Split across 2 weekends** (CPU then GPU)
2. **Extend to 24+ hour windows**
3. **Block auto-upgrades + quarterly manual campaigns**

The split-weekend approach is most practical — it respects your team's availability while working within GKE's technical constraints.