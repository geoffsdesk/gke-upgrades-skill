# Multi-Environment GKE Upgrade Strategy

**Cluster Fleet:** 12 Standard clusters across 3 environments  
**Version Path:** 1.28 → 1.29 → 1.30 (sequential minor upgrades recommended)  
**Channel Strategy:** Dev (Rapid) → Staging (Regular) → Prod (Stable)

## Overview

This strategy leverages your existing channel staggering to create natural gates between environments. Sequential minor version upgrades (1.28→1.29→1.30) provide safer compatibility validation than jumping directly to 1.30.

## Phase 1: Dev Environment (Rapid channel)
**Timeline:** Week 1-2  
**Target:** 1.28 → 1.29

### Preparation
- [ ] Verify 1.29 is available in Rapid channel:
```bash
gcloud container get-server-config --zone ZONE --format="yaml(channels.RAPID)"
```
- [ ] Configure maintenance windows for each dev cluster (off-peak hours)
- [ ] Set up monitoring baselines

### Rollout sequence
**Day 1:** Upgrade dev clusters 1-2
**Day 3:** Upgrade dev clusters 3-4 (48h soak time)
**Day 5:** Validation and 1.29→1.30 preparation

### Validation gates
- [ ] All system pods healthy
- [ ] Application smoke tests pass
- [ ] No deprecated API warnings for 1.30
- [ ] Performance within baseline (±10%)

## Phase 2: Dev 1.30 Upgrade
**Timeline:** Week 3  
**Prerequisites:** Phase 1 complete, 1.30 available in Rapid

**Day 1:** Dev clusters 1-2 (1.29→1.30)  
**Day 3:** Dev clusters 3-4 (1.29→1.30)  

### Critical validation for 1.30
- [ ] GKE 1.30 breaking changes tested (check release notes)
- [ ] Third-party operators compatible with K8s 1.30
- [ ] GPU drivers compatible (if applicable)
- [ ] StatefulSet behavior unchanged

## Phase 3: Staging Environment (Regular channel)
**Timeline:** Week 4-5  
**Prerequisites:** Dev validation complete, 1.29 available in Regular

### Sequence
**Week 4:** Staging 1.28→1.29 (all 4 clusters, 2-day intervals)  
**Week 5:** Staging 1.29→1.30 (after 1.30 appears in Regular channel)

### Enhanced validation
- [ ] Load testing at staging scale
- [ ] Database migration compatibility (if applicable)
- [ ] End-to-end integration tests
- [ ] Performance regression analysis

## Phase 4: Production Environment (Stable channel)
**Timeline:** Week 6-8  
**Prerequisites:** Staging validation complete, versions available in Stable

### Conservative rollout
**Production cluster sequencing (1.28→1.29):**
- Day 1: Prod cluster 1 (lowest risk)
- Day 4: Prod cluster 2 (72h soak)
- Day 7: Prod cluster 3
- Day 10: Prod cluster 4

**Production cluster sequencing (1.29→1.30):**
- Week 2 of production phase, same 3-day intervals

### Production-specific precautions
```bash
# Configure "no minor or node upgrades" exclusion as escape hatch
gcloud container clusters update PROD_CLUSTER \
  --zone ZONE \
  --add-maintenance-exclusion-name "emergency-hold" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time "2025-06-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

## Node Pool Upgrade Strategy (All Environments)

### Recommended surge settings by workload type:
```bash
# Stateless application pools
gcloud container node-pools update app-pool \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# Database/stateful pools  
gcloud container node-pools update db-pool \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# GPU pools (if applicable)
gcloud container node-pools update gpu-pool \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### Per-cluster upgrade order:
1. Control plane first
2. Utility/monitoring node pools
3. Application node pools  
4. Database/stateful node pools last

## Risk Mitigation

### Maintenance windows
```bash
# Example: Saturday 2-6 AM UTC maintenance window
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2025-01-11T02:00:00Z" \
  --maintenance-window-end "2025-01-11T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### Emergency brake
Each production cluster has a pre-configured "no minor or node upgrades" maintenance exclusion that can be activated to halt auto-upgrades if issues arise.

### Rollback strategy
- Control plane rollback requires GKE support engagement
- Node pool rollback: create new pool at previous version, migrate workloads
- Database workloads: ensure backups before each phase

## Timeline Summary

| Week | Activity | Environment | Version | Gate |
|------|----------|-------------|---------|------|
| 1-2  | Phase 1  | Dev        | 1.28→1.29 | Smoke tests |
| 3    | Phase 2  | Dev        | 1.29→1.30 | Full validation |
| 4    | Phase 3a | Staging    | 1.28→1.29 | Load testing |
| 5    | Phase 3b | Staging    | 1.29→1.30 | Integration tests |
| 6-7  | Phase 4a | Prod       | 1.28→1.29 | Business validation |
| 7-8  | Phase 4b | Prod       | 1.29→1.30 | Final deployment |

## Success Criteria

**Dev gates:** No crashes, basic functionality
**Staging gates:** Performance within 5% of baseline, all integration tests pass  
**Prod gates:** Zero customer impact, all SLIs maintained

**Abort criteria:** >1% error rate increase, >50ms p95 latency regression, any data corruption signals

This strategy provides multiple validation gates while respecting your channel-based environment separation. The 6-8 week timeline allows for thorough validation at each stage.