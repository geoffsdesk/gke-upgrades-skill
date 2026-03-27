# GKE Large Cluster Upgrade Optimization Plan

## Current Bottlenecks

Your 600-node cluster is hitting GKE's **maximum upgrade parallelism of ~20 nodes simultaneously** (increasing to 100 in the roadmap). At this rate, your minimum upgrade time is:
- 600 nodes ÷ 20 nodes/batch = 30 batches minimum
- Each batch takes 5-15 minutes (drain + provision + ready)
- **Total: 2.5-7.5 hours minimum** under ideal conditions

Your >24 hour reality suggests additional bottlenecks beyond parallelism limits.

## Optimization Strategy

### 1. GPU Pool Optimization (Critical)

**Current issue:** GPU pools with fixed A100 reservations have **no surge capacity**. If you're using `maxSurge>0`, surge nodes fail to provision and the upgrade stalls.

**Fix — GPU-specific settings:**
```bash
# For both GPU pools - maxUnavailable is the PRIMARY lever
gcloud container node-pools update GPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2

gcloud container node-pools update GPU_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2
```

**Why this helps:**
- `maxSurge=0` prevents failed surge node provisioning
- `maxUnavailable=2` allows 2 nodes per batch to drain simultaneously 
- No extra GPU quota needed (drain-first strategy)
- **Trade-off:** Temporary capacity dip during each batch

### 2. CPU Pool Acceleration

**Optimize surge settings:**
```bash
# For CPU pools - use percentage-based maxSurge
gcloud container node-pools update CPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 15 \  # ~5% of 300 nodes, capped at parallelism limit
  --max-unavailable-upgrade 0

gcloud container node-pools update CPU_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 15 \
  --max-unavailable-upgrade 0
```

### 3. Skip-Level Node Upgrades

**Major time saver:** If your control plane is multiple versions ahead of nodes, use skip-level upgrades within the 2-version skew limit.

**Example:** If control plane is at 1.33 and nodes are at 1.31:
```bash
# Skip 1.32, go directly 1.31→1.33
gcloud container node-pools upgrade POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.33.x-gke.xxx
```

This **halves your upgrade cycles** compared to sequential upgrades.

### 4. Upgrade Sequencing Strategy

**Parallel pool upgrades (Manual):**
```bash
# Start all CPU pools simultaneously (they don't compete for GPU quota)
gcloud container node-pools upgrade CPU_POOL_1 --cluster CLUSTER --zone ZONE --cluster-version TARGET &
gcloud container node-pools upgrade CPU_POOL_2 --cluster CLUSTER --zone ZONE --cluster-version TARGET &

# Monitor progress
watch 'kubectl get nodes -L cloud.google.com/gke-nodepool'
```

**Sequential order (recommended):**
1. **CPU pools first** (parallel) — higher risk tolerance, validate drain/surge settings
2. **GPU pools during training gaps** — schedule when no active training runs

### 5. Maintenance Window Strategy

**Option A — Split across multiple weekends:**
```bash
# Weekend 1: Control plane + CPU pools only
gcloud container clusters upgrade CLUSTER --master --cluster-version TARGET
# Then CPU pools...

# Weekend 2: GPU pools during training downtime
# GPU pool upgrades...
```

**Option B — Extend maintenance window:**
```bash
# Longer weekend window (Friday night → Sunday)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-05T22:00:00Z" \  # Friday 10 PM
  --maintenance-window-end "2024-01-07T14:00:00Z" \    # Sunday 2 PM
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=FR"
```

### 6. Pre-Upgrade Optimization

**Cluster autoscaler interaction:** During upgrades, autoscaler may create NEW nodes at the OLD version, slowing convergence.

**Mitigation:**
```bash
# Pause autoscaling during upgrade window
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --no-enable-autoscaling

# Or set min=max temporarily
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --min-nodes CURRENT_SIZE \
  --max-nodes CURRENT_SIZE
```

**Resource cleanup:**
```bash
# Scale down non-critical workloads to free capacity
kubectl scale deployment NON_CRITICAL_APP --replicas=0
```

### 7. Monitor and Diagnose Bottlenecks

**Check for common stalls:**
```bash
# PDBs blocking drain (most common cause of >24h upgrades)
kubectl get pdb -A -o wide | grep "0$"

# Resource constraints
kubectl get pods -A | grep Pending
kubectl describe nodes | grep -A 5 "Allocated resources"

# Long-running pods preventing drain
kubectl get pods -A --sort-by='.metadata.creationTimestamp' | head -10
```

## Expected Results

**After optimization:**
- **CPU pools:** ~3-4 hours (2x300 nodes with optimized surge)
- **GPU pools:** ~2-3 hours (2x GPU pools with drain-first strategy)
- **Total:** 6-8 hours — fits your weekend window

**Timeline:**
```
Friday 10 PM:  Start control plane upgrade
Saturday 12 AM: Start CPU pool upgrades (parallel)
Saturday 4 AM:  CPU pools complete, start GPU pools
Saturday 8 AM:  All upgrades complete
```

## Action Items

1. **Immediately** verify GPU pools are using `maxSurge=0, maxUnavailable=2`
2. Check if control plane is multiple versions ahead — plan skip-level upgrades
3. Test the optimized settings on a single node pool first
4. Extend maintenance window to Friday night → Sunday
5. Set up monitoring for PDB violations and resource constraints

This should bring your upgrade time from 24+ hours down to 6-8 hours, fitting your weekend maintenance window.