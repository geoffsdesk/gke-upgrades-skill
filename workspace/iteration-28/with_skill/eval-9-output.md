# Optimizing Large Standard Cluster Upgrades

## Current bottlenecks analysis

With 600 nodes and 24+ hour upgrade times, you're hitting GKE's **maximum upgrade parallelism of ~20 nodes simultaneously**. At this rate, 600 nodes = ~30 batches minimum, explaining the extended duration.

## Recommended optimization strategy

### 1. Parallel node pool upgrades (immediate improvement)

Instead of sequential pool upgrades, trigger all pools simultaneously:

```bash
# Start all node pool upgrades in parallel
gcloud container node-pools upgrade cpu-pool-1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade cpu-pool-2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade gpu-pool-1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade gpu-pool-2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &

# Monitor all pools
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "NAME|Ready"'
```

**Expected improvement:** Reduces wall-clock time by ~75% since pools upgrade concurrently instead of sequentially.

### 2. GPU pool optimization (critical for your A100 reservations)

Since your GPU pools have **fixed reservations with no surge capacity**, use the drain-first strategy:

```bash
# Configure GPU pools for maximum safe parallelism
gcloud container node-pools update gpu-pool-1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4

gcloud container node-pools update gpu-pool-2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4
```

**Key insight:** With fixed GPU reservations, `maxUnavailable` is your **only effective lever**. Setting it to 4 allows 4 nodes to drain simultaneously per pool, significantly speeding up the process while staying within your reservation limits.

### 3. CPU pool aggressive surge settings

For CPU pools (assuming you have surge capacity):

```bash
# Calculate 5% of pool size for maxSurge
# Example: 200-node pool → maxSurge=10
gcloud container node-pools update cpu-pool-1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 10 \
  --max-unavailable-upgrade 0

gcloud container node-pools update cpu-pool-2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 10 \
  --max-unavailable-upgrade 0
```

### 4. Extended maintenance window approach

Since your upgrades will likely still exceed 8 hours, consider:

```bash
# Set 48-hour maintenance window (Friday night → Sunday night)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-26T22:00:00Z" \
  --maintenance-window-end "2024-01-28T22:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=FR"
```

### 5. Pre-upgrade preparation for speed

**Week before upgrade:**
```bash
# Identify and fix potential blocking issues
kubectl get pdb -A -o wide | grep "ALLOWED DISRUPTIONS.*0"
kubectl get pods -A -o json | jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Check for resource constraints
kubectl top nodes
kubectl describe nodes | grep -A 5 "Allocated resources"
```

## Complete upgrade runbook

### Pre-flight (30 minutes before)
```bash
# Pause non-critical workloads to free resources
kubectl scale deployment non-critical-app --replicas=0 -n namespace

# Verify cluster health
kubectl get nodes | grep -v Ready
kubectl get pods -A | grep -v Running | grep -v Completed

# Configure all pools for optimized settings (run once)
# CPU pools - aggressive surge
gcloud container node-pools update cpu-pool-1 --cluster CLUSTER_NAME --zone ZONE --max-surge-upgrade 10 --max-unavailable-upgrade 0
gcloud container node-pools update cpu-pool-2 --cluster CLUSTER_NAME --zone ZONE --max-surge-upgrade 10 --max-unavailable-upgrade 0

# GPU pools - drain-first with higher parallelism
gcloud container node-pools update gpu-pool-1 --cluster CLUSTER_NAME --zone ZONE --max-surge-upgrade 0 --max-unavailable-upgrade 4
gcloud container node-pools update gpu-pool-2 --cluster CLUSTER_NAME --zone ZONE --max-surge-upgrade 0 --max-unavailable-upgrade 4
```

### Upgrade execution
```bash
# Control plane first (15-20 minutes)
gcloud container clusters upgrade CLUSTER_NAME --zone ZONE --master --cluster-version TARGET_VERSION

# Parallel node pool upgrades (start all simultaneously)
gcloud container node-pools upgrade cpu-pool-1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade cpu-pool-2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade gpu-pool-1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &
gcloud container node-pools upgrade gpu-pool-2 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION &

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

## Expected timeline improvement

**Before optimization:** 24+ hours (sequential pools)
**After optimization:** 6-8 hours (parallel pools with optimized settings)

**Breakdown:**
- Control plane: 15-20 minutes
- CPU pools (parallel): 4-6 hours with aggressive surge
- GPU pools (parallel): 5-7 hours with maxUnavailable=4
- **Total:** Fits within extended weekend window

## Additional considerations

### For future optimization
- **Nodepool upgrade concurrency (Preview, April 2026):** GKE will support concurrent node pool auto-upgrades, eliminating the need for manual parallel triggering
- **AI Host Maintenance:** If your GPU workloads require host maintenance, coordinate with GKE support for parallel host maintenance strategy

### Monitoring during upgrade
```bash
# Track upgrade progress per pool
kubectl get nodes -o custom-columns=NAME:.metadata.name,POOL:.metadata.labels.cloud\\.google\\.com/gke-nodepool,VERSION:.status.nodeInfo.kubeletVersion

# Check for stuck operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES AND status=RUNNING"
```

This approach should reduce your upgrade time to fit within an extended weekend maintenance window while maximizing safety for your GPU workloads.