# Multi-Environment GKE Upgrade Strategy
**12 Standard clusters (4 per environment) | Regular channel | 1.32 → 1.33**

## Recommended Strategy: Channel-Based Sequential Rollout

Since all environments are currently on Regular channel, I recommend a **channel differentiation strategy** combined with manual minor upgrade control for predictable sequencing:

### Channel & Control Strategy
```
Dev (4 clusters)     → Stay on Regular channel
Staging (4 clusters) → Stay on Regular channel  
Prod (4 clusters)    → Regular + "no minor or node upgrades" exclusion
```

**Why this approach:**
- Dev gets 1.33 first when it arrives in Regular (~2-4 weeks from now)
- Staging gets 1.33 automatically after dev validation
- Prod is protected by exclusion - you manually trigger after staging validation
- All clusters stay on same channel (no version drift risk)
- Simpler than rollout sequencing for 12-cluster fleet

## Detailed Rollout Plan

### Phase 1: Configure Production Protection
Apply exclusions to all 4 prod clusters to prevent auto-upgrade:

```bash
for PROD_CLUSTER in prod-cluster-1 prod-cluster-2 prod-cluster-3 prod-cluster-4; do
  gcloud container clusters update $PROD_CLUSTER \
    --zone ZONE \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
done
```

### Phase 2: Dev Environment (Week 1)
**Target:** First 1-2 dev clusters as canaries

```bash
# When 1.33 becomes available in Regular channel
# Upgrade 2 dev clusters first
gcloud container clusters upgrade dev-cluster-1 \
  --zone ZONE --master --cluster-version 1.33.X-gke.Y

# After control plane: upgrade node pools
gcloud container node-pools upgrade default-pool \
  --cluster dev-cluster-1 --zone ZONE --cluster-version 1.33.X-gke.Y

# Wait 24-48h, monitor health, then upgrade remaining dev clusters
```

### Phase 3: Staging Environment (Week 2)
**Trigger:** After dev clusters stable for 3+ days

```bash
# Upgrade all 4 staging clusters in parallel (they're not prod-critical)
for STAGING_CLUSTER in staging-cluster-1 staging-cluster-2 staging-cluster-3 staging-cluster-4; do
  gcloud container clusters upgrade $STAGING_CLUSTER \
    --zone ZONE --master --cluster-version 1.33.X-gke.Y &
done

# After control planes complete, upgrade node pools
for STAGING_CLUSTER in staging-cluster-1 staging-cluster-2 staging-cluster-3 staging-cluster-4; do
  gcloud container node-pools upgrade default-pool \
    --cluster $STAGING_CLUSTER --zone ZONE --cluster-version 1.33.X-gke.Y &
done
```

### Phase 4: Production Environment (Week 3)
**Trigger:** After staging validation complete

```bash
# Remove exclusions and upgrade 1 prod cluster first
gcloud container clusters update prod-cluster-1 \
  --zone ZONE \
  --remove-maintenance-exclusion-name "no minor or node upgrades"

# Manual upgrade (bypasses maintenance windows)
gcloud container clusters upgrade prod-cluster-1 \
  --zone ZONE --master --cluster-version 1.33.X-gke.Y

# After 24h soak, continue with remaining prod clusters
for PROD_CLUSTER in prod-cluster-2 prod-cluster-3 prod-cluster-4; do
  gcloud container clusters update $PROD_CLUSTER \
    --zone ZONE \
    --remove-maintenance-exclusion-name "no minor or node upgrades"
  
  gcloud container clusters upgrade $PROD_CLUSTER \
    --zone ZONE --master --cluster-version 1.33.X-gke.Y
done
```

## Node Pool Upgrade Strategy

For all Standard clusters, recommend **surge upgrades** with environment-specific settings:

### Dev Clusters
```bash
# Aggressive settings for faster feedback
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

### Staging Clusters  
```bash
# Balanced settings
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

### Production Clusters
```bash
# Conservative settings
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

## Timeline & Milestones

| Week | Environment | Action | Success Criteria |
|------|-------------|--------|------------------|
| 1 | Dev | Upgrade 2 clusters | No critical issues for 48h |
| 1 | Dev | Upgrade remaining 2 | All dev workloads healthy |
| 2 | Staging | Upgrade all 4 clusters | Integration tests pass, 72h soak |
| 3 | Prod | Upgrade 1 cluster (canary) | Production metrics stable 24h |
| 3-4 | Prod | Upgrade remaining 3 | All production services healthy |

## Pre-Upgrade Checklist (Apply to All 12 Clusters)

```bash
# Check 1.33 availability in Regular channel
gcloud container get-server-config --zone ZONE --format="yaml(channels.regular)"

# Verify no deprecated APIs
for CLUSTER in cluster-list; do
  echo "Checking $CLUSTER..."
  kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
done

# Configure maintenance windows (off-peak)
for CLUSTER in all-clusters; do
  gcloud container clusters update $CLUSTER --zone ZONE \
    --maintenance-window-start "2024-12-01T02:00:00Z" \
    --maintenance-window-end "2024-12-01T06:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
done
```

## Validation Commands

```bash
# Monitor upgrade progress across all clusters
for CLUSTER in all-12-clusters; do
  echo "=== $CLUSTER ==="
  gcloud container clusters describe $CLUSTER --zone ZONE \
    --format="table(name, currentMasterVersion, nodePools[].version)"
done

# Health check after each phase
kubectl get nodes --all-namespaces=false
kubectl get pods -A | grep -v Running | grep -v Completed
```

## Rollback Strategy

- **Dev/Staging:** Accept risk, fix forward
- **Production:** 
  - During upgrade: can cancel in-progress operations
  - After upgrade: requires new node pool creation at 1.32 + workload migration
  - Control plane rollback: requires GKE support involvement

## Alternative: GKE Rollout Sequencing

If you want **fully automated** fleet coordination instead of manual triggers:

```bash
# Configure fleet-based rollout sequencing
# Dev fleet → Staging fleet → Prod fleet
# With 48h soak between environments
```

However, the manual approach above gives you **more control** and is recommended for production environments where you want explicit validation gates between environments.

Would you like me to detail the commands for any specific phase, or adjust the timeline based on your constraints?