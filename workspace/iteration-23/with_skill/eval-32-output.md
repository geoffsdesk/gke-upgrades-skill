# Large-Scale GKE Upgrade Plan: 3,000-Node Multi-Pool Cluster

You're hitting GKE's upgrade parallelism ceiling (~20 nodes simultaneously) across all pools. With 3,000 nodes, this creates a **125+ hour upgrade timeline** — far exceeding your 8-hour Saturday window. Here's how to handle upgrades at your scale:

## Root Cause Analysis

- **GKE upgrade parallelism:** ~20 nodes maximum simultaneously across ALL pools (increasing to 100 in roadmap)
- **Your math:** 3,000 nodes ÷ 20 = 150 batches minimum × ~30-45 minutes per batch = 75-112 hours
- **Window constraint:** 8-hour Saturday window can only complete ~320-640 nodes maximum

## Recommended Strategy: Staggered Multi-Weekend Approach

### Weekend 1: Non-GPU Pools (Lower Risk)
```bash
# Priority order: CPU pools first (stateless, faster recovery)
gcloud container node-pools upgrade cpu-pool-web \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION

gcloud container node-pools upgrade cpu-pool-api \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

### Weekend 2-3: GPU Pools (Higher Risk, Need Longer Windows)
```bash
# GPU pools require special handling due to:
# - Fixed reservations (likely no surge capacity)
# - Driver compatibility testing required
# - Inference/training workload coordination

# For GPU pools with fixed reservations:
gcloud container node-pools update gpu-pool-a100 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2

# Then upgrade:
gcloud container node-pools upgrade gpu-pool-a100 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

## GPU Pool-Specific Considerations

### 1. Reservation Capacity Check
```bash
# Before attempting GPU upgrades, verify reservation headroom:
gcloud compute reservations describe GPU_RESERVATION_NAME --zone ZONE
```

### 2. GPU Strategy Selection
- **A100/H100 (training pools):** `maxSurge=0, maxUnavailable=1-2` — assumes no surge capacity
- **L4/T4 (inference pools):** Consider **autoscaled blue-green** to avoid inference latency spikes
- **Never use maxSurge > 0 for GPU pools unless you've confirmed surge capacity exists**

### 3. Driver Compatibility Validation
```bash
# CRITICAL: Test target GKE version + GPU driver in staging first
# Create staging node pool with target version:
gcloud container node-pools create staging-gpu-test \
  --cluster STAGING_CLUSTER \
  --zone ZONE \
  --cluster-version TARGET_VERSION \
  --machine-type n1-standard-4 \
  --accelerator type=nvidia-tesla-t4,count=1 \
  --num-nodes 1

# Deploy representative workloads and validate CUDA/driver compatibility
```

## Extended Maintenance Window Strategy

### Option A: Expand Weekend Window
- **Friday 10pm → Monday 6am:** 32-hour continuous window
- Can complete ~1,280-2,560 nodes (still may need 2 weekends for full fleet)
- Requires stakeholder buy-in for extended downtime risk

### Option B: Maintenance Exclusions + Controlled Rollout
```bash
# Block auto-upgrades, do manual upgrades in phases:
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "manual-upgrade-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Manually trigger upgrades by pool priority during planned windows
```

## Workload Coordination by Pool Type

### GPU Training Pools (A100/H100)
- **Pre-upgrade:** Checkpoint running jobs, pause new submissions 2 hours before window
- **Strategy:** `maxUnavailable=1` (conservative, preserves jobs)
- **Timeline:** Plan 12-16 hours per large training pool

### GPU Inference Pools (L4/T4)
- **Strategy:** Autoscaled blue-green to maintain serving capacity
- **Validation:** Monitor inference latency during transition
- **Fallback:** Traffic shifting to other regions if needed

### CPU Pools
- **Strategy:** `maxSurge=5%` of pool size (e.g., 750-node pool → maxSurge=38, capped at parallelism limit)
- **Timeline:** Fastest recovery, prioritize these first

## Monitoring During Large Upgrades

```bash
# Track progress across all pools:
watch 'gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE | grep -E "NAME|RUNNING"'

# Monitor stuck operations:
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES AND status=RUNNING"

# Check upgrade bottlenecks:
kubectl get events -A --field-selector reason=FailedScheduling | tail -20
kubectl get pdb -A -o wide | grep "0$"  # PDBs blocking drain
```

## Alternative: Cluster Recreation Strategy

For clusters this large with infrequent upgrades, consider:

### Blue-Green Cluster Approach
1. **Create new cluster** at target version (parallel to upgrade)
2. **Migrate workloads** pool by pool using traffic shifting
3. **Decomission old cluster** after validation
4. **Advantages:** Zero upgrade timeout risk, clean slate, can pre-validate entire stack

### When to Consider Cluster Recreation
- Version skew > 2 minors (accumulated deprecated APIs)
- Major infrastructure changes needed (networking, node types)
- Upgrade timeline exceeds 2-3 weekends

## Recommended Implementation Plan

### Phase 1: Immediate (Next Upgrade Cycle)
```bash
# Set realistic maintenance window:
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T22:00:00Z" \
  --maintenance-window-end "2024-01-08T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Use maintenance exclusion for control:
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

### Phase 2: Upgrade Execution
**Weekend 1:** Control plane + 2 CPU pools (1,200-1,500 nodes)  
**Weekend 2:** Remaining 2 CPU pools + L4/T4 inference pools  
**Weekend 3:** A100/H100 training pools (coordinate with ML team for job gaps)

### Phase 3: Long-term Architecture
- **Consider cluster splitting:** Separate inference and training clusters for independent upgrade cycles
- **Evaluate Extended release channel:** 24-month support reduces upgrade frequency
- **Implement rollout sequencing:** When you have multiple clusters, use fleet-based sequencing

## Key Success Metrics
- **Upgrade velocity:** Nodes upgraded per hour during active windows
- **Workload impact:** Zero unplanned inference downtime, training job checkpoint success rate
- **Time to completion:** Total wall-clock time from start to full fleet upgraded

Your current approach of trying to fit 3,000 nodes into 8 hours isn't viable with GKE's architecture. The staggered multi-weekend approach with pool prioritization is the most reliable path forward for your scale.