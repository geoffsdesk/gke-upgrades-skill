# GKE Large Cluster Upgrade Optimization Plan

## Current State Analysis

**Cluster:** 600 nodes across 4 pools (Standard mode)  
**Challenge:** 24+ hour upgrade duration vs 8-hour weekend maintenance window  
**Constraint:** GPU pools have fixed reservations (no surge capacity)

## Root Cause: GKE's ~20 Node Parallelism Limit

GKE upgrades approximately **20 nodes simultaneously** regardless of your `maxSurge` setting. With 600 nodes, this means ~30 batches minimum, which explains your 24+ hour duration.

**Math:** 600 nodes ÷ 20 concurrent = 30 batches × ~5-10 minutes per batch = 2.5-5 hours minimum (plus drain time, pod scheduling delays, resource contention)

## Optimization Strategy

### 1. Pool-Specific Upgrade Strategies

**CPU Pools (assuming ~400 nodes total):**
```bash
# Pool 1 & 2: Aggressive surge settings
gcloud container node-pools update CPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 10 \
  --max-unavailable-upgrade 0

# This creates 10 surge nodes per batch, but GKE still processes ~20 nodes total
# Benefit: Reduces scheduling delays and "musical chairs" effects
```

**GPU Pools (assuming ~200 A100 nodes total):**
```bash
# GPU pools with fixed reservations: maxUnavailable is your ONLY lever
gcloud container node-pools update GPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4

# Allows 4 GPU nodes to drain simultaneously per batch
# Higher maxUnavailable = faster upgrade but temporary capacity loss
```

### 2. Parallel Node Pool Upgrades (Manual Coordination)

Instead of GKE's sequential pool upgrades, trigger multiple pools simultaneously:

```bash
# Start all pools at once (requires separate terminals or background jobs)
gcloud container node-pools upgrade CPU_POOL_1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade CPU_POOL_2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade GPU_POOL_1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade GPU_POOL_2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &

# Monitor all operations
watch 'gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES"'
```

**Expected improvement:** 4x faster total upgrade time (6-8 hours instead of 24+ hours)

### 3. Upgrade Sequencing Priority

**Order:** GPU pools first, then CPU pools
- GPU pools are more constrained (fixed reservations, no surge)
- Validates drain settings on lower-risk workloads
- CPU pools can absorb evicted workload from GPU pools

### 4. Pre-Upgrade Optimization

**Scale down non-critical workloads:**
```bash
# Temporarily reduce replica counts to free up resources
kubectl scale deployment NON_CRITICAL_APP --replicas=0
# Do this for dev/test workloads running on the cluster
```

**Pause cluster autoscaler during upgrade:**
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --no-enable-autoscaling
  
# Re-enable after upgrade
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling
```

This prevents the autoscaler from creating new nodes at the old version during the upgrade.

### 5. Weekend Maintenance Window Strategy

**Split across 2 weekends** if single weekend isn't sufficient:

**Weekend 1:** Control plane + GPU pools only
```bash
# Saturday AM: Control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# Saturday PM: GPU pools (parallel)
# Expected duration: 4-6 hours
```

**Weekend 2:** CPU pools
```bash
# Both CPU pools in parallel
# Expected duration: 4-6 hours
```

### 6. Extended Maintenance Window (Recommended)

**Expand to 12-hour weekend window:**
- Friday 8 PM → Saturday 8 AM (12 hours)
- Allows single-weekend completion with parallel pool upgrades
- More predictable than cross-weekend coordination

## Expected Results

| Current | Optimized |
|---------|-----------|
| 24+ hours | 6-8 hours |
| Sequential pools | Parallel pools |
| Weekend spillover | Single weekend window |

## Monitoring During Upgrade

```bash
# Real-time node upgrade progress
watch 'kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,POOL:.metadata.labels.cloud\.google\.com/gke-nodepool | sort -k3,3'

# Pool-specific progress
watch 'gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE --format="table(name,version,status)"'

# Check for stuck pods
kubectl get pods -A | grep -E "Terminating|Pending|ContainerCreating"
```

## Risk Mitigation

**GPU Pool Considerations:**
- `maxUnavailable=4` means temporary 4-node capacity loss per pool
- Ensure inference/training workloads can tolerate this
- Consider `maxUnavailable=2` if 4 is too aggressive

**Resource Validation:**
- Ensure CPU pools have sufficient quota for surge nodes
- Monitor for pods stuck in Pending state during upgrade
- Have rollback plan ready

## Next Steps

1. **Test in staging first** with the same pool structure and parallel upgrade approach
2. **Configure optimized surge settings** 2 weeks before production upgrade
3. **Coordinate with stakeholders** on 12-hour maintenance window
4. **Prepare monitoring dashboards** for real-time upgrade tracking
5. **Document lessons learned** for future large cluster upgrades

This approach should reduce your upgrade time from 24+ hours to 6-8 hours, fitting within an extended weekend maintenance window.