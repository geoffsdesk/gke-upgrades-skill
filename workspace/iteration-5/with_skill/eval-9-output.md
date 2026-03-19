# GKE Large Cluster Upgrade Optimization

**Current situation:** 600-node Standard cluster, 24+ hour upgrade duration, 8-hour weekend maintenance window

## Root cause analysis

Your upgrade duration problem stems from GKE's maximum upgrade parallelism of ~20 nodes simultaneously, regardless of `maxSurge` settings. With 600 nodes, you're looking at minimum 30 batches of upgrades, each taking time for pod eviction, node recreation, and pod rescheduling.

**Calculation:** 600 nodes ÷ 20 parallel = 30 batches × ~30-45 minutes per batch = 15-22.5 hours minimum

## Speed optimization strategies

### 1. Aggressive surge settings

```bash
# Apply to all non-GPU pools
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 20 \
  --max-unavailable-upgrade 0

# For GPU pools (if any) - more conservative due to capacity constraints
gcloud container node-pools update GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

**Note:** Even with `maxSurge=20`, GKE's internal limit caps actual parallelism at ~20 nodes cluster-wide.

### 2. Staggered pool upgrade strategy

Don't upgrade all pools simultaneously. Sequence them to avoid resource contention:

```bash
# Weekend 1: Non-critical pools (assuming ~300 nodes)
gcloud container node-pools upgrade NON_CRITICAL_POOL_1 \
  --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &

gcloud container node-pools upgrade NON_CRITICAL_POOL_2 \
  --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &

# Weekend 2: Critical/GPU pools (assuming ~300 nodes)
gcloud container node-pools upgrade CRITICAL_POOL \
  --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &

gcloud container node-pools upgrade GPU_POOL \
  --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
```

### 3. Blue-green for speed-critical pools

For pools that must complete within your 8-hour window:

```bash
# Create replacement pool at target version
gcloud container node-pools create POOL_NAME-new \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION \
  --num-nodes ORIGINAL_NODE_COUNT \
  --machine-type ORIGINAL_MACHINE_TYPE \
  --max-surge-upgrade 20

# Migrate workloads (faster than surge upgrade)
kubectl cordon -l cloud.google.com/gke-nodepool=POOL_NAME
kubectl drain NODENAME --ignore-daemonsets --delete-emptydir-data

# Delete old pool once migration complete
gcloud container node-pools delete POOL_NAME \
  --cluster CLUSTER_NAME --zone ZONE --quiet
```

**Tradeoff:** Blue-green requires 2x compute quota temporarily but can complete pool replacement in 2-4 hours vs 8-12 hours for surge.

### 4. Pre-upgrade workload optimization

Reduce upgrade friction to speed node transitions:

```bash
# Identify pods with long termination grace periods
kubectl get pods -A -o json | \
  jq '.items[] | select(.spec.terminationGracePeriodSeconds > 60) | {ns:.metadata.namespace, name:.metadata.name, grace:.spec.terminationGracePeriodSeconds}'

# Check for overly restrictive PDBs
kubectl get pdb -A -o wide | awk '$4 == "0" {print $0}'
```

**Fixes:**
- Reduce `terminationGracePeriodSeconds` to 30-60s where possible
- Temporarily relax PDBs during upgrade window
- Ensure no bare pods (they block drain)

### 5. Extended maintenance window approach

Since 8 hours isn't sufficient for atomic completion, structure as a controlled rolling upgrade:

```bash
# Configure maintenance window for extended period
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start 2024-01-13T02:00:00Z \
  --maintenance-window-end 2024-01-14T02:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

Start upgrades Friday night, let them run through Sunday.

## Resource requirements

**For surge upgrades with maxSurge=20:**
- Need +20 nodes worth of compute quota
- Network capacity for rapid pod rescheduling
- Monitor quota usage: `gcloud compute project-info describe --project PROJECT_ID`

**For blue-green approach:**
- Need 2x quota for the largest pool
- Higher burst network bandwidth
- Storage I/O capacity for rapid PV reattachment

## Monitoring upgrade progress

```bash
# Real-time node status
watch 'kubectl get nodes -o wide | grep -v Ready | wc -l; echo "--- Upgrading nodes ---"; kubectl get nodes | grep -v Ready'

# Upgrade operation progress
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=3

# Pod eviction backlog
kubectl get pods -A | grep Terminating | wc -l
```

## Recommended approach for your cluster

**Phase 1 (Immediate):** Optimize current surge strategy
- Set `maxSurge=20, maxUnavailable=0` on all non-GPU pools
- `maxSurge=3, maxUnavailable=0` on GPU pools
- Relax PDBs during upgrade window
- Target: reduce to 16-18 hours

**Phase 2 (Next upgrade cycle):** Implement staggered approach
- Weekend 1: 300 nodes (non-critical pools)
- Weekend 2: 300 nodes (critical/GPU pools)
- Target: 6-8 hours per weekend

**Phase 3 (Long-term):** Consider cluster architecture changes
- Split into multiple smaller clusters (300 nodes each)
- Regional cluster with node pools spread across zones
- Dedicated pools for different workload types

This approach should get your largest pools upgraded within your 8-hour window while maintaining workload availability.