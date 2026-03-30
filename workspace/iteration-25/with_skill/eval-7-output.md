# GKE Rollout Strategy: 1.32 → 1.33 Upgrade

## Environment Overview
- **12 clusters total:** 4 dev + 4 staging + 4 prod
- **Current version:** 1.32
- **Target version:** 1.33 
- **Cluster mode:** Standard
- **Release channel:** Regular (all environments)

## Recommended Rollout Strategy

### Option 1: Progressive Environment Rollout (Recommended)

**Phase 1: Dev Environment (Week 1)**
- Upgrade all 4 dev clusters simultaneously
- Fast validation cycle (2-3 days)
- Catch breaking changes early

**Phase 2: Staging Environment (Week 2)**  
- Upgrade all 4 staging clusters after dev validation
- Full integration testing (3-5 days)
- Production-like workload validation

**Phase 3: Production Environment (Week 3)**
- Upgrade 2 production clusters first (canary)
- Wait 2-3 days, monitor metrics
- Upgrade remaining 2 production clusters

### Option 2: Automated Fleet Rollout with GKE Rollout Sequencing

Since all clusters are on the same Regular channel, you can use GKE's native rollout sequencing:

```bash
# Configure fleet rollout sequencing
gcloud container fleet clusterupgrade update \
    --project=PROJECT_ID \
    --upstream-fleet=dev-fleet-project \
    --default-upgrade-soaking=7d

# Fleet progression: dev → staging → prod with 7-day soak between stages
```

**Benefits:** Automated orchestration, built-in soak periods, works for both patches and minor versions.

## Pre-Rollout Configuration

### 1. Minor Version Control (Critical)
Add "no minor upgrades" exclusion to prevent auto-upgrade to 1.33 before you're ready:

```bash
# Apply to all 12 clusters
for cluster in cluster1 cluster2 cluster3 cluster4; do
  gcloud container clusters update $cluster \
    --zone ZONE \
    --add-maintenance-exclusion-name "manual-133-rollout" \
    --add-maintenance-exclusion-scope no_minor_upgrades \
    --add-maintenance-exclusion-until-end-of-support
done
```

### 2. Maintenance Windows
Configure off-peak upgrade windows per environment:

```bash
# Dev clusters: Tuesday 2-6 AM
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2026-01-07T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=TU"

# Staging clusters: Wednesday 2-6 AM  
# Production clusters: Saturday 2-6 AM
```

## Upgrade Execution Plan

### Phase 1: Dev Environment (January 7-10)

```bash
# 1. Remove minor exclusion and upgrade control plane
gcloud container clusters update dev-cluster-1 \
  --zone us-central1-a \
  --remove-maintenance-exclusion-name "manual-133-rollout"

gcloud container clusters upgrade dev-cluster-1 \
  --zone us-central1-a \
  --master \
  --cluster-version 1.33

# 2. Upgrade node pools (after CP upgrade completes)
gcloud container node-pools upgrade default-pool \
  --cluster dev-cluster-1 \
  --zone us-central1-a \
  --cluster-version 1.33
```

**Validation (2-3 days):**
- [ ] All applications healthy
- [ ] No deprecated API warnings
- [ ] Admission webhooks functioning
- [ ] Performance metrics within baseline
- [ ] Integration tests passing

### Phase 2: Staging Environment (January 14-17)

Repeat upgrade process for 4 staging clusters after dev validation passes.

**Extended validation (3-5 days):**
- [ ] Full regression test suite
- [ ] Load testing at production scale
- [ ] Database operator compatibility
- [ ] Third-party integrations verified

### Phase 3: Production Canary (January 21-24)

**Canary clusters (2 out of 4):**
```bash
# Upgrade prod-cluster-1 and prod-cluster-2 first
# Monitor for 72 hours before proceeding
```

**Monitoring checklist:**
- [ ] Error rates < baseline
- [ ] Latency (p95/p99) within SLA
- [ ] No workload disruptions
- [ ] Customer-facing services stable

### Phase 4: Production Completion (January 28)

Upgrade remaining production clusters after canary validation.

## Pre-Upgrade Checklist (Run for each environment)

```bash
# Check for deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Verify GKE insights for deprecations
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=us-central1 \
    --project=PROJECT_ID \
    --filter="category:RELIABILITY"

# Confirm 1.33 availability in Regular channel
gcloud container get-server-config --zone us-central1-a \
  --format="yaml(channels.REGULAR.validVersions)"
```

**Critical pre-flight items:**
- [ ] PDBs configured (not overly restrictive)
- [ ] No bare pods
- [ ] Admission webhooks compatible with 1.33
- [ ] Sufficient compute quota for surge nodes
- [ ] Backup verification for stateful workloads

## Node Pool Strategy Recommendations

**Standard approach for most pools:**
- `maxSurge=1, maxUnavailable=0` (zero-downtime rolling)
- For larger pools (20+ nodes): `maxSurge=5%` (percentage-based)

**GPU pools (if any):**
- `maxSurge=0, maxUnavailable=1` (no surge capacity assumption)
- Schedule during training job gaps

**Database pools:**
- `maxSurge=1, maxUnavailable=0` (conservative)
- Coordinate with database maintenance windows

## Rollback Plan

**If issues discovered in dev/staging:**
1. Apply "no upgrades" exclusion to block progression
2. Fix issues before proceeding to next environment

**If issues discovered in production canary:**
1. Block remaining production clusters with exclusions
2. Investigate on canary clusters
3. Consider creating new node pools at 1.32 if rollback needed

## Timeline Summary

| Week | Environment | Action | Duration |
|------|------------|--------|-----------|
| Week 1 | Dev | Upgrade all 4 clusters | 2-3 days validation |
| Week 2 | Staging | Upgrade all 4 clusters | 3-5 days validation |
| Week 3 | Production | Upgrade 2 canary clusters | 3-day soak |
| Week 4 | Production | Complete remaining 2 clusters | 1 day |

**Total timeline:** ~4 weeks with proper validation gates.

## Key Benefits of This Approach

1. **Risk mitigation:** Environment progression catches issues early
2. **Validation gates:** Each phase must pass before proceeding
3. **Canary production:** Reduces blast radius in production
4. **Same channel advantage:** All clusters get same 1.33 version, enabling rollout sequencing
5. **Controlled timing:** Manual triggers prevent unexpected auto-upgrades

This strategy balances speed with safety, ensuring thorough validation while maintaining a predictable rollout schedule.