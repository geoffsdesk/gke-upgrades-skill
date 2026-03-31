# Large-Scale GKE Upgrade Strategy (3,000 nodes)

## Core Issue: Upgrade Velocity vs. Window Constraints

Your 8-hour Saturday window is insufficient for a 3,000-node cluster. With GKE's ~20 node parallelism limit, you're looking at **150+ batches minimum** — potentially 12-48 hours depending on drain times and resource constraints.

## Recommended Strategy: Multi-Weekend Approach

### Option A: Sequential Pool Upgrades (Recommended)
Upgrade 1-2 node pools per maintenance window over 4-6 weeks:

**Weekend 1-2: CPU pools first**
- Lower risk, no GPU reservation constraints
- Higher `maxSurge` tolerance (5% of pool size)
- Use to validate drain/PDB settings before GPU pools

**Weekend 3-6: GPU pools individually**
- One GPU pool type per weekend
- Critical: GPU pools likely have **fixed reservations with zero surge capacity**
- Strategy: `maxSurge=0, maxUnavailable=2-4` (drain-first)

```bash
# CPU pool example (Weekend 1)
gcloud container node-pools update cpu-pool-1 \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --max-surge-upgrade 50 \
  --max-unavailable-upgrade 0

# GPU pool example (Weekend 3)
gcloud container node-pools update a100-pool \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2
```

### Option B: Extend Maintenance Window
If downtime tolerance allows, extend to 24-48 hour windows:

```bash
gcloud container clusters update YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --maintenance-window-start "2024-01-20T02:00:00Z" \
  --maintenance-window-end "2024-01-22T02:00:00Z" \
  --maintenance-window-recurrence "FREQ=MONTHLY;INTERVAL=1"
```

## GPU Pool Specific Considerations

### Verify Reservation Headroom
```bash
gcloud compute reservations describe YOUR_GPU_RESERVATION --zone YOUR_ZONE
```

**If no surge capacity exists:**
- Use `maxSurge=0, maxUnavailable=2-4` 
- Accept temporary capacity reduction during upgrade
- **Never attempt surge upgrades on GPU pools with fixed reservations**

### Training Workload Protection
For multi-day training jobs:
```bash
# Block upgrades during training campaigns
gcloud container clusters update YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "training-campaign-q1" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

### AI Host Maintenance Coordination
Your GPU nodes may also need host maintenance (~4 hours per update). Coordinate GKE upgrades with host maintenance cycles to avoid double disruption:

```bash
# Check for pending host maintenance labels
kubectl get nodes -l cloud.google.com/perform-maintenance=true
```

## Workload-Aware Sequencing

### Upgrade Order (Risk Management)
1. **Dev/staging CPU pools** (Weekend 1)
2. **Inference CPU pools** (Weekend 2) 
3. **Dev/staging GPU pools** (Weekend 3-4)
4. **Production inference GPU** (Weekend 5)
5. **Training GPU pools** (Weekend 6, during training gaps)

### PDB Review for Scale
With 3,000 nodes, overly restrictive PDBs will cascade and block the entire upgrade:

```bash
# Audit PDBs that might block at scale
kubectl get pdb -A -o json | \
  jq -r '.items[] | select(.status.disruptionsAllowed == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

**Common fixes:**
- Elasticsearch: `minAvailable: 2` (not 3) on 3-master clusters
- Inference services: `maxUnavailable: 20%` (not `minAvailable: 100%`)

## Alternative: Autoscaled Blue-Green for GPU Inference

If your GPU pools serve inference workloads, consider autoscaled blue-green to avoid eviction-caused latency spikes:

```bash
gcloud container node-pools update gpu-inference-pool \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --enable-autoscaling \
  --total-min-nodes 10 --total-max-nodes 100 \
  --enable-blue-green-upgrade \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25
```

This cordons the old pool and autoscales replacements, keeping inference serving throughout.

## Monitoring During Large Upgrades

### Track Progress
```bash
# Monitor across all pools
watch 'gcloud container node-pools list --cluster YOUR_CLUSTER --zone YOUR_ZONE --format="table(name,version,status)"'

# Check stuck operations
gcloud container operations list --cluster YOUR_CLUSTER --zone YOUR_ZONE --filter="operationType=UPGRADE_NODES AND status=RUNNING"
```

### Early Warning for Blockages
```bash
# Detect PDB violations during upgrade
gcloud logging read 'resource.type="gke_cluster" AND jsonPayload.reason="EvictionBlocked"' --limit=10
```

## Upgrade Runbook Template

### Pre-Weekend Checklist
- [ ] Current weekend target: Pool(s) ___
- [ ] Training jobs checkpointed/paused
- [ ] Inference traffic can tolerate pool capacity reduction
- [ ] PDBs reviewed for target pools
- [ ] GPU reservation headroom verified (if surge needed)
- [ ] On-call engineer assigned for 8-hour window

### Weekend Execution
```bash
# 1. Verify pre-flight
kubectl get nodes -l cloud.google.com/gke-nodepool=TARGET_POOL
kubectl get pdb -A -o wide

# 2. Configure strategy per pool type
# [CPU pools - use surge commands above]
# [GPU pools - use drain-first commands above]

# 3. Trigger upgrade
gcloud container node-pools upgrade TARGET_POOL \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --cluster-version TARGET_VERSION

# 4. Monitor for 8 hours, troubleshoot blocks immediately
```

### Success Criteria
- [ ] Target pool(s) 100% at new version
- [ ] All workloads healthy post-upgrade  
- [ ] No stuck operations
- [ ] Training/inference workloads resumed

## Timeline Expectation

**Total upgrade duration: 4-6 weekends** for full fleet upgrade using this approach. This is normal and expected for clusters of your scale. The alternative — attempting everything in one window — has high failure risk and will likely result in partial upgrades and extended troubleshooting.

**Key insight:** Large-scale upgrades are **capacity planning exercises**, not just technical ones. Your 8-hour window constraint requires breaking the work into manageable chunks rather than fighting GKE's inherent parallelism limits.