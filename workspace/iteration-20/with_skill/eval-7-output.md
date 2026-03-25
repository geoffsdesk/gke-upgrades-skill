# GKE Fleet Rollout Strategy: 1.32 → 1.33 Upgrade

## Environment Overview
- **12 clusters total:** 4 dev + 4 staging + 4 prod
- **Current version:** 1.32
- **Target version:** 1.33
- **Channel:** Regular (all environments)
- **Mode:** Standard clusters

## Rollout Sequencing Strategy

Since all environments are on the **same release channel** (Regular), you have two primary options for coordinated rollout:

### Option A: GKE Native Rollout Sequencing (Recommended)

Configure GKE's built-in fleet rollout sequencing for automated, ordered upgrades with soak periods:

```bash
# Create fleet memberships for each environment
gcloud container fleet memberships register dev-fleet \
    --project=PROJECT_ID \
    --cluster=DEV_CLUSTER_1 --cluster-location=ZONE

# Configure rollout sequence: dev → staging → prod
gcloud container fleet clusterupgrade update \
    --project=PROJECT_ID \
    --upstream-fleet=dev-fleet \
    --default-upgrade-soaking=48h
```

**Advantages:**
- Automated sequencing — GKE waits for dev completion + soak before starting staging
- Built-in failure stops — if dev upgrades fail, staging/prod are blocked
- No manual coordination required

### Option B: Manual Coordination with Release Channel Controls (Interim Solution)

Use maintenance exclusions to control minor version progression manually:

```bash
# Apply "no minor upgrades" exclusion to ALL clusters initially
for cluster in dev-1 dev-2 dev-3 dev-4 staging-1 staging-2 staging-3 staging-4 prod-1 prod-2 prod-3 prod-4; do
    gcloud container clusters update $cluster \
        --zone ZONE \
        --add-maintenance-exclusion-name "manual-minor-control" \
        --add-maintenance-exclusion-scope no_minor_upgrades \
        --add-maintenance-exclusion-until-end-of-support
done
```

## Detailed Rollout Plan

### Phase 1: Development Environment (Week 1)
**Target:** 4 dev clusters

**Pre-flight checks:**
```bash
# Verify 1.33 available in Regular channel
gcloud container get-server-config --zone ZONE \
    --format="yaml(channels.REGULAR.validVersions)"

# Check deprecated API usage across dev clusters
for cluster in dev-1 dev-2 dev-3 dev-4; do
    echo "=== $cluster ==="
    kubectl --context=$cluster get --raw /metrics | grep deprecated || echo "No deprecated APIs"
done
```

**Upgrade sequence:**
1. **Dev-1** (canary) — upgrade first, validate 24h
2. **Dev-2 & Dev-3** (parallel) — upgrade after dev-1 validation
3. **Dev-4** (final) — upgrade after dev-2/3 success

**Commands:**
```bash
# Remove exclusion from dev clusters only
gcloud container clusters update dev-1 \
    --zone ZONE \
    --remove-maintenance-exclusion "manual-minor-control"

# Manual trigger for immediate upgrade
gcloud container clusters upgrade dev-1 \
    --zone ZONE \
    --master \
    --cluster-version 1.33
```

### Phase 2: Staging Environment (Week 2)
**Target:** 4 staging clusters
**Prerequisites:** All dev clusters successfully at 1.33, workloads validated

**Validation gates from dev:**
- [ ] All applications deploy successfully on 1.33
- [ ] Performance metrics within baseline
- [ ] No new errors/crashes in logs
- [ ] Load testing passed on dev-4

**Upgrade staging clusters in pairs:**
```bash
# Remove exclusion from staging-1 & staging-2
gcloud container clusters update staging-1 \
    --zone ZONE \
    --remove-maintenance-exclusion "manual-minor-control"
    
# Trigger upgrades
gcloud container clusters upgrade staging-1 \
    --zone ZONE \
    --master \
    --cluster-version 1.33
```

**48-hour soak period** between staging-1/2 and staging-3/4.

### Phase 3: Production Environment (Week 3-4)
**Target:** 4 prod clusters
**Prerequisites:** All staging clusters at 1.33, full integration testing passed

**Production-specific preparations:**
- [ ] Maintenance window scheduled (weekend, off-peak)
- [ ] On-call team notified and available
- [ ] Rollback plan documented and tested
- [ ] Customer communication sent (if external-facing)

**Conservative prod sequence:**
1. **Prod-1** (single canary) — upgrade during maintenance window, validate 72h
2. **Prod-2** — upgrade after prod-1 validation
3. **Prod-3 & Prod-4** — final pair, staggered by 12h

## Node Pool Upgrade Strategy

For each cluster's node pools, use **skip-level upgrades** where possible:

```bash
# After control plane reaches 1.33, upgrade node pools directly from 1.32 → 1.33
gcloud container node-pools update default-pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 5% \  # Percentage-based for scalability
    --max-unavailable-upgrade 0

gcloud container node-pools upgrade default-pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version 1.33
```

**Per-pool settings by workload type:**
- **Stateless pools:** `maxSurge=5%`, `maxUnavailable=0`
- **Stateful/database pools:** `maxSurge=1`, `maxUnavailable=0`
- **Spot pools:** `maxSurge=5%`, `maxUnavailable=1` (higher tolerance)

## Maintenance Windows & Timing

```bash
# Configure weekend maintenance windows for production
gcloud container clusters update PROD_CLUSTER \
    --zone ZONE \
    --maintenance-window-start "2024-01-06T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Recommended schedule:**
- **Dev clusters:** Weekday upgrades, business hours (fast feedback)
- **Staging clusters:** Thursday evenings (validation before prod weekend)
- **Prod clusters:** Saturday 2-6 AM (minimal traffic)

## Monitoring & Validation

**Per-phase validation checklist:**
```bash
# Cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed

# Version confirmation
gcloud container clusters describe CLUSTER \
    --zone ZONE \
    --format="table(name, currentMasterVersion, nodePools[].version)"

# Application smoke tests
kubectl run test-pod --image=nginx --rm -it --restart=Never -- curl -I http://your-app/health
```

**Rollback triggers:**
- Control plane upgrade fails
- >10% increase in application error rates
- Critical workload failures
- Performance degradation >20% from baseline

## Risk Mitigation

### Before starting any upgrades:
1. **Backup critical stateful workloads:**
   ```bash
   kubectl get pv -o yaml > pv-backup-$(date +%Y%m%d).yaml
   # Application-level backups for databases
   ```

2. **Verify PDBs are properly configured:**
   ```bash
   kubectl get pdb -A -o wide
   # Ensure no PDBs with minAvailable=100% blocking drain
   ```

3. **Test upgrade on a dev clone first** (if possible)

### Emergency procedures:
- **Stop further rollout:** Re-apply maintenance exclusions to remaining clusters
- **Rollback individual cluster:** Create new node pool at 1.32, migrate workloads
- **Escalation:** GKE support with cluster names, zones, and operation IDs

## Timeline Summary

| Week | Phase | Clusters | Key Activities |
|------|-------|----------|----------------|
| 1 | Dev | 4 clusters | Canary → parallel → validation |
| 2 | Staging | 4 clusters | Integration testing, performance validation |
| 3 | Prod (canary) | 1 cluster | Conservative production validation |
| 4 | Prod (remaining) | 3 clusters | Final production rollout |

**Total duration:** ~4 weeks with proper soak periods and validation gates.

This approach balances speed with safety — dev environment provides fast feedback, staging validates integration, and production gets the most conservative treatment with multiple validation gates.