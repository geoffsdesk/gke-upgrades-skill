# Large-Scale GKE Upgrade Strategy for 3,000-Node Cluster

Your upgrade timeouts are expected behavior at this scale. GKE upgrades ~20 nodes simultaneously regardless of `maxSurge` settings, so your 3,000-node cluster requires **150+ upgrade batches minimum**. An 8-hour Saturday window cannot accommodate this.

## Root cause analysis

**Current bottlenecks:**
- **Upgrade parallelism:** ~20 nodes max concurrency = 150+ batches for 3,000 nodes
- **Time per batch:** 10-15 minutes including drain, provision, and validate
- **Total duration estimate:** 25-40 hours minimum (well beyond your 8-hour window)
- **Mixed workload complexity:** GPU and CPU pools have different upgrade constraints

## Recommended multi-weekend strategy

### Phase 1: CPU pools (Weekend 1)
Upgrade non-GPU pools first during your maintenance window. These typically upgrade faster and have more surge capacity available.

```bash
# Configure CPU pools for maximum safe parallelism
for POOL in cpu-pool-1 cpu-pool-2 cpu-pool-3 cpu-pool-4; do
  gcloud container node-pools update $POOL \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 3 \
    --max-unavailable-upgrade 0
done

# Stagger CPU pool upgrades by 30 minutes each
gcloud container node-pools upgrade cpu-pool-1 --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION
# Wait 30 minutes, then start next pool...
```

### Phase 2: GPU pools (Weekend 2-3)
GPU pools need special handling due to capacity constraints and workload sensitivity.

**For GPU pools with reservations (assumed no surge capacity):**
```bash
# GPU-optimized settings: maxUnavailable is the primary lever
gcloud container node-pools update a100-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2  # Adjust based on pool size

# Consider autoscaled blue-green for mission-critical GPU workloads
gcloud container node-pools update h100-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaled-blue-green-upgrade
```

## Extended maintenance windows

**Expand your maintenance windows for this upgrade:**
```bash
# Temporary extended window during upgrade weekends
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start 2024-MM-DDTHH:MM:SSZ \
  --maintenance-window-end 2024-MM-DDTHH:MM:SSZ \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA,SU"  # Both weekend days
```

Or create a single long window:
```bash
# 20-hour window (Friday 6pm - Saturday 2pm)
--maintenance-window-start 2024-MM-DDTFRIDAY_18:00:00Z \
--maintenance-window-end 2024-MM-DDTSATURDAY_14:00:00Z
```

## Node pool sequencing strategy

**Priority order (avoid parallel upgrades of different pool types):**
1. **L4/T4 pools first** — smaller, inference workloads, more resilient
2. **CPU pools** — largest count, most straightforward
3. **A100 pools** — training workloads, coordinate with ML team
4. **H100 pools last** — most critical, highest value workloads

**Anti-pattern:** Don't upgrade GPU and CPU pools simultaneously. GPU failures are harder to debug and GPU surge capacity is constrained.

## GPU-specific considerations

**Driver compatibility check:**
```bash
# Test target version in a staging cluster first
# GKE auto-installs drivers matching target version — CUDA version may change
kubectl describe node GPU_NODE | grep nvidia
```

**Long-running training protection:**
```bash
# Apply maintenance exclusion during active training campaigns
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-q1" \
  --add-maintenance-exclusion-start-time START_TIME \
  --add-maintenance-exclusion-end-time END_TIME \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**Coordinated upgrade approach for training pools:**
1. **Checkpoint active training jobs**
2. **Cordon training node pool** (let jobs complete naturally)
3. **Upgrade empty pool**
4. **Restart training from checkpoints**

## Alternative: Cluster recreation strategy

For clusters this large with mixed GPU/CPU workloads, consider **recreating the cluster** instead of in-place upgrades:

**Benefits:**
- **Predictable timeline** — create new cluster at target version (1-2 hours)
- **No surge capacity needed** — use existing quota more efficiently  
- **Clean state** — eliminates accumulated node drift and potential issues
- **Workload validation** — test everything on new cluster before cutover

**Drawback:** Requires workload migration planning and temporary duplicate capacity.

## Monitoring and validation

**Track upgrade progress:**
```bash
# Monitor completion across pools
watch 'gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE --format="table(name,version,status)"'

# Check for stuck pods during upgrade
kubectl get pods -A | grep -E "Terminating|Pending|CrashLoop"
```

**Upgrade duration estimates per pool (rough):**
- **CPU pools (1,000 nodes):** 15-20 hours each
- **GPU pools (500 nodes each):** 8-12 hours each  
- **Total sequential:** 60-80 hours across 3-4 weekends

## Future scaling improvements

**Coming in 2026:**
- **Nodepool upgrade concurrency:** Multiple pools can upgrade simultaneously during auto-upgrades
- **Increased node parallelism:** Roadmap to support 100 nodes concurrently (vs current ~20)

**For now:** Plan multi-weekend upgrades and consider cluster recreation for major version jumps.

## Immediate action plan

1. **This weekend:** Start with L4/T4 pools (smallest, test the process)
2. **Next weekend:** CPU pools with `maxSurge=3`
3. **Weekend 3:** A100 pools during training gap
4. **Weekend 4:** H100 pools with full coordination

**Key insight:** At your scale, upgrades are infrastructure projects, not maintenance tasks. Plan accordingly with extended windows and multi-phase execution.