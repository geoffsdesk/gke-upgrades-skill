# Large-Scale GKE Upgrade Plan: 3,000-Node Multi-Pool Cluster

Your 8-hour Saturday window is insufficient for a 3,000-node cluster. At GKE's maximum parallelism of ~20 nodes simultaneously, you're looking at 150+ batches minimum, which can take **days to weeks** depending on your surge settings and pod eviction times.

## Immediate Solutions

### 1. Extend your maintenance window
```bash
# Configure a 48-hour weekend window (Friday 10pm - Sunday 10pm)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start 2024-12-06T22:00:00Z \
  --maintenance-window-end 2024-12-08T22:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=FR"
```

### 2. Stagger node pool upgrades (don't upgrade all pools simultaneously)

**Phase 1: CPU pools only (Weekends 1-2)**
```bash
# Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# Upgrade CPU pools with aggressive surge settings
for pool in cpu-pool-1 cpu-pool-2 cpu-pool-3 cpu-pool-4; do
  gcloud container node-pools update $pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 20 \
    --max-unavailable-upgrade 0
  
  gcloud container node-pools upgrade $pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version TARGET_VERSION
done
```

**Phase 2: GPU pools (Weekends 3-4, during training gaps)**
```bash
# Conservative settings for GPU pools due to capacity constraints
for pool in a100-pool h100-pool l4-pool t4-pool; do
  gcloud container node-pools update $pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 1 \
    --max-unavailable-upgrade 0  # Safer for GPU workloads
  
  gcloud container node-pools upgrade $pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version TARGET_VERSION
done
```

### 3. GPU-specific considerations

Your GPU pools face unique constraints:

- **Capacity scarcity**: A100/H100 surge nodes may not be available, causing upgrades to stall
- **Training job protection**: Multi-day training runs can't tolerate mid-job eviction
- **Driver coupling**: Target GKE version may change CUDA versions

**For training-active GPU pools:**
```bash
# Apply maintenance exclusion to protect running training jobs
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-q1" \
  --add-maintenance-exclusion-start-time 2024-12-01T00:00:00Z \
  --add-maintenance-exclusion-end-time 2025-03-01T00:00:00Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**Alternative for GPU pools with scarce capacity:**
```bash
# Use maxUnavailable mode (drains first, no extra GPUs needed)
gcloud container node-pools update h100-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1  # Causes temporary capacity dip
```

## Long-term Architecture Fixes

### 1. Split into smaller clusters
Consider breaking your 3,000-node monolith into:
- **CPU cluster**: 1,500 nodes for general workloads
- **Training cluster**: 800 GPU nodes for ML workloads  
- **Inference cluster**: 700 mixed GPU nodes for serving

Smaller clusters upgrade faster and with less blast radius.

### 2. Dedicated training node pools with auto-upgrade disabled
```bash
# Create training pool with manual control
gcloud container node-pools create training-h100 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoupgrade=false \
  --machine-type a3-highgpu-8g \
  --num-nodes 50

# Upgrade only during scheduled training gaps
```

### 3. Use rollout sequencing for phased upgrades
```bash
# Configure fleet-wide sequencing (requires multiple clusters)
gcloud container fleet update \
  --project PROJECT_ID \
  --set-rollout-sequencing-enabled \
  --rollout-sequencing-soak-time 72h
```

## Immediate Remediation Plan

**Week 1: Assess and prepare**
- [ ] Check current upgrade operation status
- [ ] Extend maintenance window to 48 hours (Friday night → Sunday night)
- [ ] Identify which pools have active training jobs
- [ ] Apply maintenance exclusions to training pools if needed

**Week 2: CPU pools upgrade**
- [ ] Upgrade control plane during extended window
- [ ] Upgrade CPU pools with `maxSurge=20, maxUnavailable=0`
- [ ] Monitor and validate CPU workloads

**Week 3: Plan GPU strategy**
- [ ] Test target GKE version GPU driver compatibility in staging
- [ ] Schedule training job checkpoints/gaps
- [ ] Confirm GPU quota availability for surge nodes

**Week 4: GPU pools upgrade**
- [ ] Upgrade GPU pools during training gaps
- [ ] Use conservative surge settings or `maxUnavailable` mode
- [ ] Validate GPU driver + CUDA + framework compatibility

## Monitoring Commands

```bash
# Track overall progress across all pools
watch 'gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE --format="table(name,version,status)"'

# Monitor upgrade operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES" --limit=5

# Check for stuck pods across the cluster
kubectl get pods -A | grep -E "Terminating|Pending|CrashLoop" | wc -l
```

## Risk Mitigation

- **PDB review**: Ensure your PDBs aren't overly restrictive (common cause of timeouts)
- **Resource requests**: Verify all containers have requests — missing requests cause scheduling failures
- **Backup strategy**: Snapshot critical data before GPU pool upgrades
- **Rollback plan**: Document node pool recreation procedures for emergency rollback

At your scale, the **key insight** is that 8 hours simply isn't enough time. You need either longer windows, phased upgrades across multiple weekends, or cluster segmentation to make this manageable.