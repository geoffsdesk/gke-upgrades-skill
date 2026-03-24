# GKE Upgrade Acceleration Plan for Large Standard Cluster

## Current Situation Analysis

**Cluster profile:**
- 600 nodes across 4 node pools (2 CPU, 2 A100 GPU)
- Current upgrade time: 24+ hours
- Available maintenance window: 8 hours (weekends)
- GPU pools have fixed reservations (limited surge capacity)

**Root cause of slow upgrades:**
- GKE's maximum upgrade parallelism is ~20 nodes simultaneously regardless of `maxSurge` setting
- For 600 nodes at 20 nodes/batch = 30 batches minimum
- At ~15-20 minutes per batch = 7.5-10 hours just for batching, plus drain time
- Sequential node pool upgrades (GKE default) multiply this by 4 pools

## Acceleration Strategy

### 1. Parallel Node Pool Upgrades (Primary Speed Gain)

**Current:** Node pools upgrade sequentially (Pool1 → Pool2 → Pool3 → Pool4)
**Optimized:** Trigger all node pool upgrades simultaneously

```bash
# After control plane upgrade, trigger all pools in parallel
gcloud container node-pools upgrade cpu-pool-1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION --async &
gcloud container node-pools upgrade cpu-pool-2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION --async &
gcloud container node-pools upgrade gpu-pool-1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION --async &
gcloud container node-pools upgrade gpu-pool-2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION --async &
```

**Expected time savings:** 75% reduction (24 hours → ~6-8 hours)

### 2. GPU Pool Strategy (Fixed Reservation Constraints)

Since your GPU pools have fixed reservations with no surge capacity:

```bash
# GPU pools: maxUnavailable is the PRIMARY lever (no surge capacity available)
gcloud container node-pools update gpu-pool-1 \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2

gcloud container node-pools update gpu-pool-2 \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2
```

**Key insight:** With fixed GPU reservations, `maxSurge=0` is required. Increase `maxUnavailable` (2-4 nodes) to speed up drain cycles, but this creates temporary GPU capacity loss. Only use higher values if GPU workloads can tolerate capacity dips.

### 3. CPU Pool Strategy (Optimized Surge)

```bash
# CPU pools: Use percentage-based surge (scales with pool size)
# Assuming ~150 nodes per CPU pool, 5% = 7-8 nodes surge
gcloud container node-pools update cpu-pool-1 \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 8 \
  --max-unavailable-upgrade 0

gcloud container node-pools update cpu-pool-2 \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 8 \
  --max-unavailable-upgrade 0
```

### 4. Skip-Level Node Pool Upgrades

**Before:** Control plane 1.31→1.32→1.33, then nodes 1.31→1.32→1.33
**Optimized:** Control plane 1.31→1.32→1.33, then nodes 1.31→1.33 (single jump)

```bash
# Upgrade control plane sequentially (required)
gcloud container clusters upgrade CLUSTER_NAME --zone ZONE --master --cluster-version 1.32.x
gcloud container clusters upgrade CLUSTER_NAME --zone ZONE --master --cluster-version 1.33.x

# Skip-level node upgrade (all pools to 1.33 directly)
# This reduces total drain cycles from 8 (4 pools × 2 versions) to 4 (4 pools × 1 version)
```

**Time savings:** 50% reduction in node pool upgrade cycles

### 5. Workload Optimization for Faster Drain

```bash
# Pre-upgrade: Scale down non-critical workloads during maintenance window
kubectl scale deployment non-critical-app --replicas=0 -n default

# Verify PDBs aren't overly restrictive
kubectl get pdb -A -o wide
# Look for minAvailable that blocks multiple pod evictions

# Temporary PDB relaxation for faster drain (restore after upgrade)
kubectl patch pdb critical-app-pdb -n production \
  -p '{"spec":{"minAvailable":"50%"}}'  # vs. previous stricter setting
```

## Complete 8-Hour Upgrade Runbook

### Hour 0-1: Pre-flight and Control Plane
```bash
# Pre-flight checks
kubectl get nodes --no-headers | wc -l  # Confirm 600 nodes
kubectl get pods -A | grep -v Running | grep -v Completed  # No stuck pods

# Scale down non-critical workloads
kubectl scale deployment batch-jobs --replicas=0 -n batch
kubectl scale deployment dev-services --replicas=0 -n development

# Sequential control plane upgrades (if multiple minor versions)
gcloud container clusters upgrade CLUSTER_NAME --zone ZONE --master --cluster-version 1.32.x
# Wait ~15 minutes, verify
gcloud container clusters upgrade CLUSTER_NAME --zone ZONE --master --cluster-version 1.33.x
```

### Hour 1-7: Parallel Node Pool Upgrades
```bash
# Configure surge settings for all pools
gcloud container node-pools update cpu-pool-1 --cluster CLUSTER_NAME --zone ZONE --max-surge-upgrade 8 --max-unavailable-upgrade 0
gcloud container node-pools update cpu-pool-2 --cluster CLUSTER_NAME --zone ZONE --max-surge-upgrade 8 --max-unavailable-upgrade 0
gcloud container node-pools update gpu-pool-1 --cluster CLUSTER_NAME --zone ZONE --max-surge-upgrade 0 --max-unavailable-upgrade 2
gcloud container node-pools update gpu-pool-2 --cluster CLUSTER_NAME --zone ZONE --max-surge-upgrade 0 --max-unavailable-upgrade 2

# Trigger all node pool upgrades simultaneously
gcloud container node-pools upgrade cpu-pool-1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION --async &
gcloud container node-pools upgrade cpu-pool-2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION --async &
gcloud container node-pools upgrade gpu-pool-1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION --async &
gcloud container node-pools upgrade gpu-pool-2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION --async &

# Monitor all operations
watch 'gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES" --format="table(name,operationType,status,startTime)"'
```

### Hour 7-8: Validation and Cleanup
```bash
# Verify all pools at target version
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE --format="table(name,version)"

# Restore workloads
kubectl scale deployment batch-jobs --replicas=ORIGINAL_COUNT -n batch
kubectl scale deployment dev-services --replicas=ORIGINAL_COUNT -n development

# Health check
kubectl get pods -A | grep -v Running | grep -v Completed
```

## GPU-Specific Considerations

**For A100 fixed reservations:**
- Confirm your reservation has NO headroom for surge capacity before using `maxSurge=0`
- Check reservation utilization: `gcloud compute reservations describe RESERVATION_NAME --zone ZONE`
- **Driver compatibility:** Test target GKE version + GPU driver in staging first — new versions may change CUDA versions silently
- Consider autoscaled blue-green as alternative if you need zero GPU capacity loss during upgrade

## Expected Results

**Time reduction:**
- From 24+ hours → 6-8 hours (fits your maintenance window)
- Parallel node pools: 75% time savings
- Skip-level upgrades: Additional 50% cycle reduction
- Optimized surge settings: 20-30% per-pool speedup

**Trade-offs:**
- Higher resource consumption during upgrade (more surge nodes)
- GPU pools experience temporary capacity loss with `maxUnavailable>1`
- More complex monitoring (4 simultaneous operations)

This approach should reliably complete your 600-node upgrade within your 8-hour weekend maintenance window while respecting your GPU reservation constraints.