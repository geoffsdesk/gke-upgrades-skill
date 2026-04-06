# Large-Scale GKE Cluster Upgrade Strategy (3,000 nodes)

Your 8-hour Saturday window is **insufficient** for a 3,000-node cluster. With GKE's maximum upgrade parallelism of ~20 nodes simultaneously, you're looking at **150+ batches minimum** — that's 15-30+ hours of upgrade time depending on node startup, drain times, and workload characteristics.

## Immediate solutions for your scale

### 1. **Extend your maintenance window significantly**

**Recommended window:** Saturday 12am - Sunday 11pm (47 hours) or **split across multiple consecutive weekends**.

```bash
# Configure extended weekend maintenance window
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-window-start "2024-01-06T00:00:00Z" \
  --maintenance-window-duration 47h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Key insight:** Large cluster upgrades routinely take days to weeks. Your 8-hour window works for ~500 nodes maximum.

### 2. **Stagger node pool upgrades across multiple weekends**

Don't upgrade all 8 pools simultaneously. Sequence them by criticality and workload tolerance:

**Weekend 1:** CPU pools (lower risk, stateless workloads)
```bash
# Upgrade CPU pools first
gcloud container node-pools upgrade cpu-pool-1 --cluster CLUSTER_NAME --region REGION --cluster-version TARGET_VERSION
gcloud container node-pools upgrade cpu-pool-2 --cluster CLUSTER_NAME --region REGION --cluster-version TARGET_VERSION
# Let these complete before touching GPU pools
```

**Weekend 2:** GPU inference pools (L4, T4)
**Weekend 3:** GPU training pools (A100, H100) during training gaps

### 3. **GPU-specific strategy — leverage maxUnavailable, not maxSurge**

Your GPU pools likely have **fixed reservations with no surge capacity**. Configure accordingly:

```bash
# For GPU pools: maxUnavailable is your ONLY lever
gcloud container node-pools update a100-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 3

gcloud container node-pools update h100-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2

# For CPU pools: use surge if quota permits
gcloud container node-pools update cpu-pool-1 \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 0
```

**Why this matters:** Setting `maxUnavailable=3` on a 500-node A100 pool means ~17 batches per upgrade cycle instead of 25 batches at maxUnavailable=1. Still significant time, but faster.

### 4. **Use maintenance exclusions for training protection**

Block upgrades during active training campaigns:

```bash
# Block node upgrades during training (allows CP patches)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "training-campaign-q1" \
  --add-maintenance-exclusion-start-time "2024-01-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-03-15T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

Only upgrade GPU pools during scheduled gaps between training runs.

## Advanced strategies for your scale

### 5. **Consider cluster splitting (architectural)**

3,000 nodes in a single cluster pushes operational limits. Consider splitting by workload type:

- **Training cluster:** A100/H100 pools only (500-1000 nodes)
- **Inference cluster:** L4/T4 pools + CPU (1000-1500 nodes)  
- **General compute cluster:** CPU pools only (500-1000 nodes)

**Benefits:**
- Smaller upgrade blast radius per cluster
- Independent maintenance windows
- Training clusters can use longer exclusions without affecting inference
- Faster individual upgrades (8 hours becomes feasible for 1000-node clusters)

### 6. **Use Extended release channel for training clusters**

```bash
gcloud container clusters update TRAINING_CLUSTER \
  --region REGION \
  --release-channel extended
```

**Extended channel advantages for large GPU clusters:**
- Up to 24 months support (vs 14 months)
- **Minor versions are NOT auto-upgraded** — you control when they happen
- Only patches auto-apply (at Regular channel timing)
- Perfect for training workloads that need stability

### 7. **Autoscaled blue-green for GPU inference pools**

For GPU inference workloads sensitive to restart latency:

```bash
gcloud container node-pools update l4-inference-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --enable-autoscaling \
  --total-min-nodes 20 --total-max-nodes 200 \
  --strategy AUTOSCALED_BLUE_GREEN \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25
```

This scales up replacement nodes gradually while keeping old nodes serving, avoiding inference downtime spikes.

## Timeline planning

**Conservative timeline for your 3,000-node cluster:**

- **Control plane upgrade:** 15-30 minutes
- **8 node pools sequentially:** 15-30 hours total (assuming 2-4 hours per pool)
- **Buffer for failures/retries:** +50% time

**Total realistic upgrade time:** 20-45 hours

## Immediate action plan

1. **This weekend:** Extend your maintenance window to 47 hours OR split the upgrade
2. **Configure maxUnavailable for GPU pools** (maxSurge likely won't work)
3. **Upgrade CPU pools first** (lower risk, faster validation)
4. **Next weekend:** GPU pools during training gaps
5. **Monitor upgrade progress:** `watch 'kubectl get nodes | grep -c "Ready\|NotReady"'`

## Long-term architectural recommendation

Split this into 2-3 smaller clusters:
- Training (GPU): 500-1000 nodes, Extended channel, long exclusions
- Inference (mixed): 1000-1500 nodes, Regular channel, blue-green for GPU
- General compute: 500-1000 nodes, Regular channel, standard surge

Each cluster becomes manageable within an 8-hour weekend window.

**Would you like me to produce a detailed runbook for your first CPU pool upgrade this weekend, or help you design the cluster split architecture?**