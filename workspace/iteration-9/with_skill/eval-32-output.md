# Large-Scale GKE Upgrade Strategy for 3,000-Node Cluster

Your 8-hour maintenance window is insufficient for a 3,000-node cluster. GKE's maximum upgrade parallelism is ~20 nodes simultaneously, requiring **150+ batches minimum**. At 5-10 minutes per batch, you're looking at **15-25+ hours** of upgrade time.

## Immediate Solutions

### 1. **Extend Your Maintenance Window**
```bash
# Set 36-hour weekend window (Fri 6pm - Sun 6am)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-12-06T18:00:00Z" \
  --maintenance-window-end "2024-12-08T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=FR"
```

### 2. **Stagger Node Pool Upgrades**
Don't upgrade all pools simultaneously. Sequence them:

**Phase 1: CPU pools (lower risk)**
```bash
# Upgrade CPU pools first with aggressive surge settings
gcloud container node-pools update CPU-POOL-1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade CPU-POOL-1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

**Phase 2: GPU pools (higher risk, needs careful planning)**
```bash
# GPU pools: maxUnavailable is your primary lever (not maxSurge)
# Most GPU customers have fixed reservations with no surge capacity
gcloud container node-pools update GPU-POOL-A100 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2  # Increase for faster completion

gcloud container node-pools upgrade GPU-POOL-A100 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

## Long-term Architecture Changes

### **Split Large Cluster into Smaller Ones**
Consider breaking your 3,000-node cluster into 4-6 smaller clusters:
- **GPU-focused clusters**: A100 cluster, H100 cluster
- **Workload-focused clusters**: Training cluster, inference cluster, batch cluster
- **Environment-focused clusters**: Dev, staging, prod

**Benefits:**
- Each cluster upgrades independently (parallel operations)
- Smaller blast radius for failures
- Different maintenance windows per cluster
- GPU reservations can be cluster-specific

## GPU-Specific Upgrade Strategy

### **GPU Pool Constraints**
- **No live migration**: Every GPU upgrade requires pod restart
- **Limited surge capacity**: A100/H100 machines are scarce
- **Driver coupling**: GKE auto-installs GPU drivers matching the target version — verify CUDA compatibility in staging first

### **Training Job Protection**
```bash
# Block upgrades during training campaigns
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-run-q4-2024" \
  --add-maintenance-exclusion-start-time "2024-12-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-01-15T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### **Recommended GPU Pool Settings**
```bash
# For A100/H100 pools (assume no surge capacity available)
--max-surge-upgrade 0 \
--max-unavailable-upgrade 2

# For L4/T4 pools (may have more surge flexibility)
--max-surge-upgrade 1 \
--max-unavailable-upgrade 0
```

## Monitoring Large Upgrades

```bash
# Track upgrade progress across all pools
watch 'gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE --format="table(name,version,status)"'

# Monitor stuck pods during upgrade
kubectl get pods -A | grep -E "Terminating|Pending" | wc -l

# Check PDB blockages (common cause of timeouts)
kubectl get pdb -A -o wide | grep -E "ALLOWED.*0"
```

## Alternative: Auto-Scale Blue-Green Upgrade

For GPU pools where surge capacity is unavailable, consider GKE's **autoscaled blue-green upgrade** strategy:

```bash
gcloud container node-pools update GPU-POOL-NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --node-pool-soak-duration 300s \
  --standard-rollout-policy-batch-node-count 1 \
  --standard-rollout-policy-batch-soak-duration 300s
```

This cordons the old pool while auto-scaling replacement nodes — better for GPU pools with capacity constraints.

## Release Channel Strategy

Consider moving GPU clusters to **Extended channel**:
- Up to 24 months support per version
- Manual control over minor upgrades
- Auto-patches only (less frequent disruption)
- Extra cost only during extended support period

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

## Pre-Upgrade Checklist for Your Scale

```
Large Cluster Pre-Upgrade Checklist
- [ ] Maintenance window extended to 36+ hours
- [ ] Node pool upgrade sequence planned (CPU first, then GPU)
- [ ] GPU surge capacity confirmed OR maxUnavailable strategy selected
- [ ] Training workloads checkpointed and protected with maintenance exclusions
- [ ] PDBs reviewed for overly restrictive settings (will block 3,000-node drain)
- [ ] Target GPU driver version tested in staging cluster
- [ ] Monitoring dashboards configured for upgrade progress tracking
- [ ] Consider cluster splitting for future upgrades
```

**Bottom line:** Your current setup requires either a much longer maintenance window (36+ hours) or architectural changes (cluster splitting). The 8-hour window works for ~400-500 node clusters, not 3,000.