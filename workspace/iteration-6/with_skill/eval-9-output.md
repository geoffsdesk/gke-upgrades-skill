# GKE Large Cluster Upgrade Optimization Plan

## Current State Analysis

**Cluster:** 600 nodes, 4 node pools, Standard mode  
**Problem:** 24+ hour upgrade duration vs. 8-hour maintenance window  
**Root cause:** GKE's default surge settings and maximum upgrade parallelism limitations

## Key Constraints for Large Clusters

**GKE upgrade parallelism limit:** ~20 nodes simultaneously regardless of `maxSurge` setting
- Your 600-node cluster = minimum 30 batches (600 ÷ 20)
- At ~3-5 minutes per batch = 1.5-2.5 hours minimum (best case)
- Real-world: 4-8 hours with coordination overhead, pod scheduling delays

**Current bottlenecks likely:**
- Conservative surge settings (`maxSurge=1`)
- Sequential node pool upgrades
- PDB-induced drain delays
- Resource constraints during pod rescheduling

## Immediate Optimization Strategy

### 1. Aggressive Surge Settings Per Pool

Configure high surge for speed, zero unavailable for safety:

```bash
# For stateless workload pools
gcloud container node-pools update STATELESS_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 20 \
  --max-unavailable-upgrade 0

# For stateful workload pools (more conservative)
gcloud container node-pools update STATEFUL_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 0

# For GPU pools (if any) - quota permitting
gcloud container node-pools update GPU_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

**Rationale:** `maxSurge=20` leverages GKE's full parallelism. Higher values don't help due to the ~20-node limit.

### 2. Parallel Node Pool Upgrades

Instead of upgrading pools sequentially, run them in parallel (separate terminals/scripts):

```bash
# Terminal 1
gcloud container node-pools upgrade POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION &

# Terminal 2  
gcloud container node-pools upgrade POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION &

# Continue for remaining pools
wait # Wait for all background jobs
```

**Expected improvement:** 4x faster if resource constraints don't bottleneck.

### 3. Pre-upgrade PDB Audit and Relaxation

Overly restrictive PDBs are the #1 cause of slow drains:

```bash
# Find restrictive PDBs
kubectl get pdb -A -o json | jq -r '
  .items[] | 
  select(.status.disruptionsAllowed == 0) | 
  "\(.metadata.namespace)/\(.metadata.name): \(.spec.minAvailable // .spec.maxUnavailable)"'
```

**Temporarily relax during upgrade:**
```bash
# Back up current PDB settings
kubectl get pdb -A -o yaml > pdb-backup.yaml

# Increase disruption allowance for upgrade window
kubectl patch pdb RESTRICTIVE_PDB -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

Restore original settings post-upgrade.

### 4. Resource Pre-provisioning

Ensure surge capacity isn't resource-constrained:

```bash
# Check current utilization
kubectl top nodes

# Verify compute quota headroom for surge
gcloud compute regions describe REGION \
  --format="table(quotas.metric,quotas.usage,quotas.limit)"
```

If CPU/memory quota is tight, temporarily scale down non-critical workloads during the upgrade window.

## Alternative: Weekend Split Strategy

If single-window completion remains challenging:

### Approach A: Two-Phase Weekend Upgrade
- **Saturday 8-hour window:** Control plane + 2 node pools
- **Sunday 8-hour window:** Remaining 2 node pools

### Approach B: Blue-Green for Critical Pools
For pools with strict availability requirements:
```bash
# Create replacement pool
gcloud container node-pools create POOL_NAME-v2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION \
  --num-nodes NUM_NODES

# Migrate workloads (manual scheduling or taints)
# Delete old pool after validation
```

**Trade-off:** Requires 2x temporary capacity but enables instant rollback.

## Expected Timeline Improvement

**Before optimization:** 24+ hours
**After optimization:** 4-8 hours (fits in maintenance window)

**Breakdown with optimized settings:**
- Control plane upgrade: 10-15 minutes
- 4 node pools × 150 nodes avg = 600 nodes total
- Parallel upgrade: 600 ÷ 20 = 30 batches
- 30 batches × 5 minutes = 2.5 hours (aggressive estimate)
- Coordination overhead: +1-2 hours
- **Total: 3.5-4.5 hours**

## Pre-Upgrade Checklist Additions

```
Large Cluster Optimization
- [ ] Surge settings configured: stateless pools maxSurge=20, stateful maxSurge=5
- [ ] PDBs audited and relaxed for upgrade window
- [ ] Compute quota verified for surge capacity (need ~120 extra nodes temporarily)
- [ ] Parallel upgrade scripts prepared for all 4 node pools
- [ ] Non-critical workloads identified for temporary scale-down if needed
- [ ] Resource monitoring dashboards ready to track surge node provisioning
```

## Monitoring During Upgrade

```bash
# Track upgrade progress across all pools
watch 'gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES" --format="table(name,operationType,status,startTime)"'

# Monitor node provisioning
watch 'kubectl get nodes | grep -c "Ready\|NotReady"'

# Watch for resource bottlenecks
kubectl get events -A --field-selector reason=FailedScheduling -w
```

This optimization should bring your upgrade time well within the 8-hour maintenance window while maintaining safety through zero unavailable settings.