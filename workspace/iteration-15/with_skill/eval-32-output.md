# Large-Scale GKE Upgrade Plan: 3,000-Node Cluster

Your 8-hour maintenance window is insufficient for a 3,000-node cluster. With GKE's maximum upgrade parallelism of ~20 nodes simultaneously, you're looking at 150 batches minimum — potentially 15-30+ hours depending on your surge settings and pool distribution.

## Immediate Solutions

### 1. Extend Maintenance Windows
```bash
# Expand to 24-hour weekend windows
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --maintenance-window-start "2024-02-03T02:00:00Z" \
    --maintenance-window-end "2024-02-04T02:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### 2. Use "No Minor or Node Upgrades" Exclusions for Control
Instead of relying on short maintenance windows, use maintenance exclusions to control upgrade timing:

```bash
# Block auto-upgrades with persistent exclusion
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "controlled-upgrades" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

Then manually trigger upgrades during planned maintenance periods when you have adequate time.

### 3. Optimize Node Pool Upgrade Strategy

**For GPU pools** (A100, H100, L4, T4):
- **Critical:** Use `maxSurge=0, maxUnavailable=2-4` (GPU reservations typically have no surge capacity)
- GPU pools are your bottleneck — they take longest and have the most constraints

```bash
# Configure GPU pool for faster upgrades
gcloud container node-pools update a100-pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 3
```

**For CPU pools:**
- Use percentage-based surge: `maxSurge=5%, maxUnavailable=0`
- CPU pools typically have surge capacity available

```bash
# Example for 500-node CPU pool: 5% = 25 nodes surge (capped at ~20 by GKE parallelism)
gcloud container node-pools update cpu-general-pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 25 \
    --max-unavailable-upgrade 0
```

## Staggered Upgrade Strategy

Don't upgrade all 8 pools simultaneously. Sequence them to reduce total load:

### Phase 1: CPU Pools (Lower Risk)
- Upgrade 4 CPU pools first
- They typically complete faster and validate your surge settings
- Duration estimate: 8-12 hours

### Phase 2: GPU Pools (Higher Risk/Complexity)
- Upgrade GPU pools during dedicated maintenance window
- Consider training job coordination
- Duration estimate: 12-24 hours for all GPU pools

```bash
# Manual sequencing - upgrade CPU pools first
for pool in cpu-pool-1 cpu-pool-2 cpu-pool-3 cpu-pool-4; do
    gcloud container node-pools upgrade $pool \
        --cluster CLUSTER_NAME \
        --zone ZONE \
        --cluster-version TARGET_VERSION
    # Monitor completion before proceeding to next pool
done
```

## GPU Pool Specific Considerations

### Training Job Protection
```bash
# Add per-nodepool exclusions for active training pools
gcloud container node-pools update h100-training-pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "training-campaign" \
    --add-maintenance-exclusion-scope no_upgrades \
    --add-maintenance-exclusion-start-time "2024-01-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-02-15T00:00:00Z"
```

### GPU Driver Compatibility Check
Before any GPU upgrade, verify driver compatibility:
```bash
# Test target version in staging cluster first
# Check CUDA version changes in GKE release notes
# Validate ML framework compatibility (TensorFlow, PyTorch)
```

## Recommended Weekly Upgrade Process

### Week 1: Control Plane + CPU Pools
```bash
# Saturday 2am: Control plane upgrade (15-30 min)
gcloud container clusters upgrade CLUSTER_NAME \
    --zone ZONE \
    --master \
    --cluster-version TARGET_VERSION

# Saturday 3am-2pm: CPU node pools (staggered)
# Upgrade 1-2 CPU pools per weekend to spread load
```

### Week 2: GPU Pools
```bash
# Coordinate with ML teams for training gaps
# Saturday 2am-Sunday 2am: GPU pools upgrade
# Use maxUnavailable mode to avoid surge capacity issues
```

## Monitoring During Large Upgrades

### Track Progress
```bash
# Monitor across all pools
watch 'gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE --format="table(name,version,status)"'

# Check upgrade operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES"
```

### Resource Monitoring
```bash
# Check for quota/capacity issues
kubectl get events -A --field-selector reason=FailedScheduling | tail -20
kubectl top nodes | grep -E "cpu|memory" | sort -k3 -nr
```

## Alternative: Multi-Weekend Approach

For maximum safety, split upgrades across multiple weekends:

**Weekend 1:** Control plane + 2 CPU pools  
**Weekend 2:** Remaining 2 CPU pools + inference GPU pools (L4, T4)  
**Weekend 3:** Training GPU pools (A100, H100) during training gaps  

## Timeline Estimates

| Component | Duration Estimate |
|-----------|------------------|
| Control plane | 15-30 minutes |
| CPU pool (500 nodes) | 6-8 hours |
| GPU pool (300 nodes) | 8-12 hours |
| **Total cluster** | **24-36 hours** |

## Next Steps Checklist

- [ ] Extend maintenance windows to 24+ hours
- [ ] Configure persistent maintenance exclusions for manual control
- [ ] Optimize surge settings per pool type
- [ ] Coordinate with ML teams for GPU upgrade timing
- [ ] Test surge settings on smallest pool first
- [ ] Set up monitoring dashboards for large upgrade tracking
- [ ] Document the multi-weekend upgrade sequence

Your cluster is at the scale where standard maintenance windows don't work. The combination of extended windows + manual upgrade control + staggered pool upgrades will give you reliable, predictable upgrades without timing out.