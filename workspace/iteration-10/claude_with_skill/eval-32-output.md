# GKE Large-Scale Upgrade Plan: 3,000-Node Multi-GPU Cluster

## Current Challenge Analysis

Your 8-hour maintenance window is insufficient for a 3,000-node cluster. With GKE's maximum upgrade parallelism of ~20 nodes simultaneously, you're looking at **150+ batches minimum**, which typically requires **24-72 hours** for completion — not 8 hours.

## Recommended Approach: Extended Maintenance Windows + Staggered Pool Upgrades

### 1. Extend Your Maintenance Window

```bash
# Set a 48-hour maintenance window (Friday 10pm - Sunday 10pm)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-05T22:00:00Z" \
  --maintenance-window-end "2024-01-07T22:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=FR"
```

**Why 48 hours?** Large GPU clusters often take 2-3 days to fully upgrade. This gives you buffer time and eliminates the timeout issue.

### 2. Stagger Node Pool Upgrades (Don't Upgrade All Pools Simultaneously)

**Priority Order:**
1. **CPU pools first** (faster, less disruptive)
2. **Training GPU pools during gaps between jobs**
3. **Inference GPU pools last** (maintain serving capacity)

```bash
# Upgrade CPU pools immediately when window opens
gcloud container node-pools upgrade cpu-pool-1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION

# Wait for CPU completion, then GPU pools
gcloud container node-pools upgrade gpu-a100-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

### 3. GPU Pool Upgrade Strategy

**For GPU pools, use `maxUnavailable` mode (not surge):**

```bash
# GPU pools: assume no surge capacity available
gcloud container node-pools update gpu-a100-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 3

# Increase maxUnavailable for faster completion
# H100 pool (most expensive): maxUnavailable=1 (cautious)
# A100 pool: maxUnavailable=3
# L4/T4 pools: maxUnavailable=5
```

**Key insight:** GPU VMs don't support live migration, so every upgrade requires pod restart. `maxUnavailable` is your primary speed lever, not `maxSurge`.

### 4. Training Job Protection

For active training runs, apply maintenance exclusions:

```bash
# Block all node upgrades during training campaigns
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-q1" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-03-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**Training-specific approach:**
- Cordon training node pools when jobs complete
- Wait for natural job completion (don't force-kill multi-day runs)
- Upgrade empty training pools between campaigns

### 5. Skip-Level Upgrades for Speed

Use skip-level (N+2) node pool upgrades when possible:

```bash
# Instead of 1.28 → 1.29 → 1.30 (two upgrade cycles)
# Go directly 1.28 → 1.30 (one upgrade cycle)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30.x-gke.xxxx
```

This **halves** your total upgrade time and maintenance windows.

### 6. Monitor Progress and Intervention

```bash
# Real-time upgrade monitoring
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "NotReady|SchedulingDisabled"'

# Check for stuck pods blocking drain
kubectl get pods -A | grep Terminating
kubectl get pdb -A -o wide | grep "0.*0"
```

**Intervention commands for common blocks:**
```bash
# Temporarily relax PDBs if blocking drain
kubectl patch pdb RESTRICTIVE_PDB -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'

# Delete bare pods (won't reschedule anyway)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

## Pre-Upgrade Checklist for Large GPU Clusters

```markdown
- [ ] Control plane upgraded first (required order)
- [ ] 48+ hour maintenance window configured
- [ ] Node pool upgrade order planned: CPU → training GPU → inference GPU
- [ ] GPU driver compatibility verified for target GKE version
- [ ] Training jobs checkpointed or scheduled to complete before upgrade
- [ ] PDBs reviewed — none overly restrictive (allow ≥25% disruption)
- [ ] Skip-level upgrade path confirmed (e.g., 1.28 → 1.30 directly)
- [ ] maxUnavailable tuned per pool:
  - H100: maxUnavailable=1 (expensive, cautious)
  - A100: maxUnavailable=3 
  - L4/T4: maxUnavailable=5
  - CPU: maxSurge=10, maxUnavailable=0
- [ ] On-call team available for 48+ hours
- [ ] Rollback plan: recreate node pools at previous version if needed
```

## Timeline Expectation

**Realistic timeline for your cluster:**
- **CPU pools (1,500 nodes):** 8-16 hours
- **GPU pools (1,500 nodes):** 24-48 hours  
- **Total:** 2-3 days

**Friday 10pm - Sunday 10pm window breakdown:**
- Friday night: Control plane + CPU pools
- Saturday: Training GPU pools (if jobs complete)
- Sunday: Inference GPU pools + validation

## Alternative: Blue-Green for Critical Inference Pools

For GPU inference pools that can't tolerate capacity dips:

```bash
# Create replacement pool at target version
gcloud container node-pools create gpu-l4-inference-v2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION \
  --num-nodes 100 \
  --machine-type g2-standard-24 \
  --accelerator type=nvidia-l4,count=2

# Cordon old pool, wait for workloads to migrate
kubectl cordon -l cloud.google.com/gke-nodepool=gpu-l4-inference-v1

# Delete old pool after validation
gcloud container node-pools delete gpu-l4-inference-v1 \
  --cluster CLUSTER_NAME \
  --zone ZONE
```

**Caveat:** This requires **doubling** your GPU quota temporarily — verify with your account team first.

---

The key insight: **Don't fight the 8-hour window; expand it.** Large GPU clusters need large maintenance windows. Your current timeout issue will disappear with proper time allocation and staggered pool upgrades.