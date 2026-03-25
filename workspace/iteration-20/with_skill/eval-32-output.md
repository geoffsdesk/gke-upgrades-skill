# Large-Scale GKE Cluster Upgrade Plan (3,000 nodes)

Your upgrade timeout issue is expected at this scale. With GKE's maximum upgrade parallelism of ~20 nodes simultaneously, a 3,000-node cluster would take **150+ batches minimum** — far exceeding an 8-hour window. Here's a comprehensive approach:

## Understanding the Scale Challenge

**Current constraint:** GKE upgrades ~20 nodes simultaneously regardless of `maxSurge` settings. For your 3,000 nodes:
- **Minimum upgrade time:** 150 batches × 5-10 minutes per batch = **12-25 hours**
- **Your 8-hour window:** Insufficient for full cluster upgrade
- **Upgrade behavior:** GKE **continues past maintenance windows** once started — it doesn't pause mid-upgrade

## Recommended Strategy: Phased Pool Upgrades

### Phase 1: Non-GPU Pools (Weekends 1-2)
Upgrade CPU pools first — they're less risky and validate your upgrade process:

```bash
# Weekend 1: Upgrade 2 CPU pools
gcloud container node-pools upgrade CPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION

# Weekend 2: Upgrade remaining 2 CPU pools
gcloud container node-pools upgrade CPU_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

### Phase 2: GPU Pools (Weekends 3-6)
GPU pools require special handling due to capacity constraints:

```bash
# For each GPU pool with fixed reservations
gcloud container node-pools update GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2

# Then upgrade
gcloud container node-pools upgrade GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

**GPU-specific considerations:**
- **No surge capacity assumed:** Most GPU customers have fixed reservations with no extra capacity
- **Use maxUnavailable mode:** `maxSurge=0, maxUnavailable=2-4` depending on workload tolerance
- **Upgrade GPU inference pools during training gaps:** Coordinate with ML teams on job scheduling

## Maintenance Window Strategy

### Option A: Extended Windows (Recommended)
```bash
# Extend to 24-hour weekend windows
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-02-03T02:00:00Z" \
  --maintenance-window-end "2024-02-04T02:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### Option B: Multi-Day Windows
```bash
# Friday night through Sunday morning
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-02-02T22:00:00Z" \
  --maintenance-window-end "2024-02-04T10:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=FR"
```

## Upgrade Optimization Settings

### Control Plane First (Sequential Minor Upgrades)
```bash
# Step 1: Upgrade control plane only
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# Step 2: Skip-level node pool upgrades (within 2-minor-version skew)
# If CP goes 1.29→1.30→1.31, nodes can go 1.29→1.31 directly
```

### Per-Pool Surge Settings
```bash
# CPU pools (stateless workloads)
gcloud container node-pools update CPU_POOL \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 0

# GPU pools (capacity-constrained)
gcloud container node-pools update GPU_POOL \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2

# Database/stateful pools
gcloud container node-pools update DB_POOL \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

## Workload Protection Strategy

### Critical GPU Workload Protection
```bash
# Add "no minor or node upgrades" exclusion during active training
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-q1" \
  --add-maintenance-exclusion-start-time "2024-02-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-04-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### PDBs for Distributed Systems
```bash
# Example: Elasticsearch cluster
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-master-pdb
spec:
  minAvailable: 2  # Maintain quorum
  selector:
    matchLabels:
      app: elasticsearch
      role: master
```

## Monitoring and Validation

### Real-time Progress Monitoring
```bash
# Track node versions across pools
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "NODEPOOL|A100|H100|L4|T4|cpu"'

# Monitor operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=5
```

### Upgrade Duration Estimation
```bash
# Check current operation status
gcloud container operations describe OPERATION_ID \
  --zone ZONE \
  --format="table(operationType,status,startTime,endTime)"
```

## Pre-Upgrade Checklist (Scale-Specific)

```markdown
Large Cluster Pre-Upgrade Checklist
- [ ] **Upgrade strategy:** Phased by pool type (CPU → GPU)
- [ ] **Maintenance windows:** Extended to 24+ hours or multi-day
- [ ] **GPU driver compatibility:** Target version tested with A100/H100/L4/T4 workloads
- [ ] **Training job coordination:** ML teams notified, checkpoints saved
- [ ] **Surge settings optimized:** Per-pool based on capacity constraints
- [ ] **Skip-level upgrades planned:** Nodes 1.29→1.31 after CP reaches 1.31
- [ ] **PDBs configured:** For distributed GPU workloads (Ray, Horovod, etc.)
- [ ] **Monitoring active:** Real-time progress tracking setup
- [ ] **Rollback plan:** New pool creation tested in dev cluster
```

## Alternative: Cluster Recreation Strategy

For future major upgrades (e.g., 1.29→1.32), consider:

1. **Blue-green at cluster level:** Create new 3,000-node cluster
2. **Workload migration:** Use GitOps to redeploy applications
3. **Data migration:** PV snapshots → restore on new cluster
4. **DNS cutover:** Update ingress to point to new cluster

This avoids the multi-week upgrade cycle but requires mature CI/CD and stateful data migration planning.

## Timeline Recommendation

- **Week 1:** Control plane upgrade only
- **Week 2-3:** CPU pools (2 pools per weekend)
- **Week 4-7:** GPU pools (1 pool per weekend, coordinate with ML teams)
- **Week 8:** Final validation and cleanup

**Expected total duration:** 8 weeks for a controlled, low-risk upgrade of your scale cluster.

Would you like me to detail the GPU-specific upgrade procedures or help you set up the phased maintenance windows?