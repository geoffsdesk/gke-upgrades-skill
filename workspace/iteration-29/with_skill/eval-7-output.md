# GKE Multi-Environment Rollout Strategy

## Environment Overview
- **12 clusters total:** 4 dev + 4 staging + 4 prod
- **Current version:** 1.32 → **Target version:** 1.33
- **Channel:** Regular (all environments)
- **Cluster mode:** Standard

## Recommended Rollout Strategy

### Phase 1: Dev Environment (Week 1)
**Approach:** Manual upgrade with validation

```bash
# Dev clusters (upgrade all 4 in parallel after staging readiness)
for CLUSTER in dev-cluster-1 dev-cluster-2 dev-cluster-3 dev-cluster-4; do
  # Control plane upgrade
  gcloud container clusters upgrade $CLUSTER \
    --zone ZONE \
    --master \
    --cluster-version 1.33.x-gke.latest
  
  # Wait for CP upgrade completion, then upgrade node pools
  gcloud container node-pools upgrade default-pool \
    --cluster $CLUSTER \
    --zone ZONE \
    --cluster-version 1.33.x-gke.latest
done
```

**Validation period:** 3-5 days
- Deploy representative workloads
- Run integration tests
- Validate API compatibility
- Check deprecated API usage

### Phase 2: Staging Environment (Week 2)
**Approach:** Sequential upgrade with soak time

```bash
# Staging clusters (upgrade 1-2 at a time)
# First batch
gcloud container clusters upgrade staging-cluster-1 --zone ZONE --master --cluster-version 1.33.x-gke.latest
gcloud container clusters upgrade staging-cluster-2 --zone ZONE --master --cluster-version 1.33.x-gke.latest

# Soak 24-48 hours, then second batch
gcloud container clusters upgrade staging-cluster-3 --zone ZONE --master --cluster-version 1.33.x-gke.latest
gcloud container clusters upgrade staging-cluster-4 --zone ZONE --master --cluster-version 1.33.x-gke.latest
```

**Validation period:** 5-7 days
- Full end-to-end testing
- Load testing at production scale
- Performance regression testing
- Final go/no-go decision

### Phase 3: Production Environment (Week 3-4)
**Approach:** Conservative sequential with extended soak

```bash
# Production clusters (upgrade 1 at a time with 48h soak)
for CLUSTER in prod-cluster-1 prod-cluster-2 prod-cluster-3 prod-cluster-4; do
  # Control plane upgrade
  gcloud container clusters upgrade $CLUSTER \
    --zone ZONE \
    --master \
    --cluster-version 1.33.x-gke.latest
  
  # Wait 24h, then upgrade node pools
  gcloud container node-pools upgrade default-pool \
    --cluster $CLUSTER \
    --zone ZONE \
    --cluster-version 1.33.x-gke.latest
  
  # Soak 48h before next cluster
done
```

## Alternative: Automated Rollout Sequencing

Since all environments are on the Regular channel, you can use GKE's rollout sequencing for automated progression:

### Setup Fleet-Based Rollout Sequencing

```bash
# Configure fleet rollout sequence
gcloud container fleet clusterupgrade update \
  --project=PROJECT_ID \
  --upstream-fleet=dev-fleet-project \
  --default-upgrade-soaking=48h

# Apply "no minor upgrades" exclusion to control timing
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Sequence:** Dev fleet → (48h soak) → Staging fleet → (48h soak) → Prod fleet

## Maintenance Configuration

Apply to all clusters before starting:

```bash
# Set maintenance windows (Saturday 2-6 AM)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-02-03T02:00:00Z" \
  --maintenance-window-end "2024-02-03T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Add "no minor upgrades" exclusion to prevent auto-upgrade during manual rollout
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Rollback Plan

**If issues found in dev/staging:**
- Block progression to next environment
- All clusters can run mixed 1.32/1.33 safely (within version skew policy)
- Debug and fix issues before proceeding

**If critical issues found in production:**
- **Control plane:** Contact GKE support for emergency downgrade
- **Node pools:** Create new pools at 1.32, migrate workloads, delete 1.33 pools

## Risk Mitigation

1. **Staged progression:** Each environment validates before the next starts
2. **Extended soak times:** 48h between production clusters
3. **Maintenance windows:** Upgrades only during planned windows
4. **Version compatibility:** 1.32→1.33 is a single minor version jump (low risk)
5. **Manual control:** "No minor upgrades" exclusion prevents unexpected auto-upgrades

## Timeline Summary

| Week | Environment | Action | Soak Time |
|------|-------------|--------|-----------|
| 1 | Dev | Upgrade all 4 clusters | 3-5 days |
| 2 | Staging | Sequential upgrade (2+2) | 5-7 days |
| 3-4 | Prod | One-by-one upgrade | 48h between clusters |

**Total duration:** 3-4 weeks for complete rollout

## Key Success Metrics

- Zero production incidents during upgrade
- All workloads maintain SLA compliance
- No deprecated API usage blocking future upgrades
- All clusters reach 1.33 within the planned timeline

This strategy balances speed with safety, giving you multiple validation checkpoints while maintaining predictable upgrade timing across your fleet.