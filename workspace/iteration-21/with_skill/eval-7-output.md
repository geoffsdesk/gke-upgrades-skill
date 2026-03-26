# GKE Fleet Upgrade Strategy: 1.32 → 1.33

## Environment Overview
- **12 clusters total:** 4 dev + 4 staging + 4 prod
- **Current:** 1.32 on Regular channel
- **Target:** 1.33
- **Mode:** Standard clusters

## Recommended Rollout Strategy

### Option A: Release Channel Minor Control (Recommended)

This approach uses GKE's automated patching while giving you manual control over minor version progression across environments.

#### Configuration Changes
```bash
# Apply to ALL 12 clusters
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "minor-control" \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

#### Rollout Sequence
1. **Dev environment** (4 clusters) - Week 1
2. **Staging environment** (4 clusters) - Week 2 (after dev validation)  
3. **Production environment** (4 clusters) - Week 3 (after staging validation)

**Key benefits:**
- All environments stay on same minor version (1.32 → 1.33)
- Patches flow automatically to all environments
- Manual control over minor version timing
- Simple to implement and maintain

### Option B: GKE Rollout Sequencing (Advanced)

For automated fleet-wide orchestration with built-in soak periods.

#### Fleet Setup
```bash
# Create fleet memberships
gcloud container fleet memberships register dev-fleet-1 \
  --cluster=projects/PROJECT/locations/ZONE/clusters/DEV_CLUSTER_1

# Configure rollout sequencing
gcloud container fleet clusterupgrade update \
  --project=PROJECT_ID \
  --upstream-fleet=dev-project-id \
  --default-upgrade-soaking=7d
```

**Sequence:** Dev fleet → (7d soak) → Staging fleet → (7d soak) → Prod fleet

## Detailed Upgrade Plan

### Pre-Rollout Setup

#### 1. Apply Minor Version Control (All Clusters)
```bash
# Template command - run for all 12 clusters
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --maintenance-window-start "2024-01-13T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

#### 2. Verify Current State
```bash
# Check all clusters are at 1.32 and exclusion is active
for cluster in $(cat cluster-list.txt); do
  echo "=== $cluster ==="
  gcloud container clusters describe $cluster \
    --format="table(name, currentMasterVersion, maintenancePolicy.window)"
done
```

### Week 1: Dev Environment

#### Day 1: Control Plane Upgrades
```bash
# Upgrade all 4 dev control planes sequentially
gcloud container clusters upgrade DEV_CLUSTER_1 \
  --zone ZONE \
  --master \
  --cluster-version 1.33.x-gke.latest
```

#### Day 2-3: Node Pool Upgrades
```bash
# Configure surge settings per cluster
gcloud container node-pools update default-pool \
  --cluster DEV_CLUSTER_1 \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# Upgrade node pools
gcloud container node-pools upgrade default-pool \
  --cluster DEV_CLUSTER_1 \
  --zone ZONE \
  --cluster-version 1.33.x-gke.latest
```

#### Day 4-7: Validation
- [ ] Application smoke tests
- [ ] Performance baseline comparison  
- [ ] Log/metric analysis for regressions
- [ ] API deprecation warnings check

### Week 2: Staging Environment

Repeat the same process after dev validation passes.

#### Prerequisites
- [ ] Dev environment stable for 7 days
- [ ] No critical issues identified
- [ ] Performance within baseline

### Week 3: Production Environment

Final production rollout with additional safeguards.

#### Additional Production Safeguards
```bash
# Conservative surge settings for production
gcloud container node-pools update PROD_NODE_POOL \
  --cluster PROD_CLUSTER \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

## Node Pool Upgrade Strategy

### Recommended Settings by Pool Type

**Standard application pools:**
- maxSurge: 5% of pool size (minimum 1)
- maxUnavailable: 0
- Strategy: Rolling surge

**Database/stateful pools:**
- maxSurge: 1
- maxUnavailable: 0  
- Strategy: Conservative one-at-a-time

**GPU pools (if any):**
- maxSurge: 0 (assume no surge capacity)
- maxUnavailable: 1
- Strategy: Drain-first

## Risk Mitigation

### Pre-Flight Checklist (Per Environment)
```bash
# Deprecated API check
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# PDB audit
kubectl get pdb -A -o wide

# Resource capacity check
kubectl top nodes
```

### Rollback Plan

**If issues found in dev/staging:**
- Stop progression to next environment
- Investigate and fix root cause
- Re-validate before continuing

**If critical issues in production:**
- Node pools can be rolled back by creating new pools at 1.32
- Control plane rollback requires GKE support

### Monitoring During Rollout

```bash
# Track upgrade progress
watch 'kubectl get nodes -o wide'

# Monitor cluster operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE

# Application health checks
kubectl get deployments -A
kubectl get pods -A | grep -v Running
```

## Timeline Summary

| Week | Environment | Activity | Validation Period |
|------|-------------|----------|-------------------|
| 1 | Dev (4 clusters) | CP + node upgrades | 7 days |
| 2 | Staging (4 clusters) | CP + node upgrades | 7 days |
| 3 | Production (4 clusters) | CP + node upgrades | Ongoing |

## Post-Rollout Cleanup

After all environments are successfully at 1.33:

```bash
# Optional: Remove minor version exclusions to resume auto-upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion "minor-control"
```

**Recommendation:** Keep the exclusions in place for continued control over future minor upgrades (1.34, 1.35, etc.).

This strategy ensures safe, controlled progression while maintaining all environments on the same minor version. The 7-day soak periods between environments provide adequate time to catch issues before they impact production.