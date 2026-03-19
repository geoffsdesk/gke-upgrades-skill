# Large Cluster Upgrade Optimization Plan

## Current bottleneck analysis

With 600 nodes and 24+ hour upgrades, you're likely hitting the default conservative surge settings. GKE's default `maxSurge=1, maxUnavailable=0` means upgrading one node at a time per pool - that's your bottleneck.

## Recommended surge optimization

Configure aggressive surge settings tailored to your 8-hour window:

```bash
# High-throughput pools (stateless workloads)
gcloud container node-pools update STATELESS_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 20 \
  --max-unavailable-upgrade 0

# Database/stateful pools (more conservative)
gcloud container node-pools update DATABASE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 0

# GPU pools (expensive, moderate surge)
gcloud container node-pools update GPU_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

## Time calculation

With optimized settings, expect these upgrade times per 150-node pool:
- **Stateless pools**: ~45-60 minutes (20 nodes upgrading in parallel)
- **Stateful pools**: ~2.5-3 hours (5 nodes in parallel) 
- **GPU pools**: ~4-5 hours (3 nodes in parallel)

**Total estimated time**: 4-6 hours for all pools - fits your 8-hour window.

## Pre-upgrade preparations

### 1. Verify compute quota
```bash
# Check current quota vs. surge needs
gcloud compute regions describe YOUR_REGION \
  --format="table(quotas.metric,quotas.usage,quotas.limit)" \
  --filter="quotas.metric:CPUS"

# You'll need quota for ~100+ additional nodes during peak surge
```

### 2. Optimize PDBs for fast draining
```bash
# Audit current PDBs - look for overly restrictive ones
kubectl get pdb -A -o custom-columns="NAMESPACE:.metadata.namespace,NAME:.metadata.name,MIN-AVAILABLE:.spec.minAvailable,MAX-UNAVAILABLE:.spec.maxUnavailable,ALLOWED:.status.disruptionsAllowed"

# Temporarily relax restrictive PDBs during upgrade window
kubectl patch pdb RESTRICTIVE_PDB -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"25%"}}'
```

### 3. Parallel pool upgrade strategy
Upgrade pools in parallel rather than sequentially:

```bash
# Start all pools simultaneously (run in parallel terminals/scripts)
gcloud container node-pools upgrade POOL_1 --cluster CLUSTER --zone ZONE --cluster-version TARGET &
gcloud container node-pools upgrade POOL_2 --cluster CLUSTER --zone ZONE --cluster-version TARGET &
gcloud container node-pools upgrade POOL_3 --cluster CLUSTER --zone ZONE --cluster-version TARGET &
gcloud container node-pools upgrade POOL_4 --cluster CLUSTER --zone ZONE --cluster-version TARGET &
```

## Monitoring during upgrade

```bash
# Real-time node status across all pools
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "NAME|NotReady|SchedulingDisabled"'

# Track upgrade operations
watch 'gcloud container operations list --cluster CLUSTER --zone ZONE --filter="operationType=UPGRADE_NODES" --format="table(name,operationType,status,startTime)"'

# Pod scheduling issues
kubectl get events -A --field-selector reason=FailedScheduling -w
```

## Rollback plan for 8-hour window

If upgrade isn't completing by hour 6:

```bash
# Check remaining nodes per pool
for pool in POOL_1 POOL_2 POOL_3 POOL_4; do
  echo "=== $pool ==="
  kubectl get nodes -l cloud.google.com/gke-nodepool=$pool -o wide | grep -E "NAME|NotReady|v1\."
done

# Cancel slowest pool if needed (finishes current nodes, stops new ones)
# Operations auto-resume on next maintenance window
```

## Long-term optimization strategies

### Blue-green alternative for critical pools
For your most sensitive workloads, consider blue-green deployment:

```bash
# Create new pool at target version
gcloud container node-pools create POOL_NAME-new \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION \
  --num-nodes CURRENT_POOL_SIZE

# Migrate workloads, then delete old pool
# Total time: ~30 minutes for workload migration
```

### Multi-cluster strategy
Consider splitting the 600-node cluster into 2-3 smaller clusters:
- Faster individual upgrades (200 nodes × 20 surge = 2-3 hours each)
- Rolling upgrades across clusters
- Reduced blast radius

## Expected outcome

With these optimizations:
- **Total upgrade time**: 4-6 hours (fits 8-hour window)
- **Peak additional cost**: ~15-20% for surge nodes during upgrade
- **Risk mitigation**: PDB management prevents service disruption

The key is matching surge settings to workload type - be aggressive with stateless apps, conservative with databases, and the upgrade will complete within your maintenance window.