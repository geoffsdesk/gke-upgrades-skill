# GKE 1.32 → 1.33 Multi-Cluster Rollout Strategy

## Overview
- **Scope:** 12 Standard clusters across 3 environments (4 clusters each)
- **Current:** GKE 1.32 on Regular channel
- **Target:** GKE 1.33
- **Strategy:** Progressive rollout with environment-based sequencing

## Rollout Sequence

### Phase 1: Dev Environment (Week 1)
**Clusters:** dev-cluster-1, dev-cluster-2, dev-cluster-3, dev-cluster-4

**Day 1-2: Canary (1 cluster)**
- Upgrade dev-cluster-1 first
- 48h soak time for validation

**Day 3-4: Dev rollout (remaining 3 clusters)**
- Upgrade dev-cluster-2, dev-cluster-3, dev-cluster-4 in parallel
- 48h validation period

### Phase 2: Staging Environment (Week 2)
**Prerequisite:** Dev validation complete, no critical issues

**Day 1-2: Staging canary (1 cluster)**
- Upgrade staging-cluster-1
- Run full integration test suite
- 48h soak time

**Day 3-4: Staging rollout (remaining 3 clusters)**
- Upgrade staging-cluster-2, staging-cluster-3, staging-cluster-4
- Load testing and performance validation

### Phase 3: Production Environment (Week 3-4)
**Prerequisite:** Staging validation complete, performance baselines met

**Week 3: Production canary (1 cluster)**
- Upgrade prod-cluster-1 (lowest traffic cluster)
- Monitor for 7 days with real production traffic
- Validate all critical workloads

**Week 4: Production rollout (remaining 3 clusters)**
- Day 1: Upgrade prod-cluster-2
- Day 3: Upgrade prod-cluster-3  
- Day 5: Upgrade prod-cluster-4
- 48h gap between each production cluster

## Upgrade Controls Configuration

Since all clusters are on Regular channel, configure maintenance controls for predictable timing:

```bash
# Apply to all 12 clusters - maintenance window (Saturday 2-6 AM)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-window-start "2024-MM-DDTHH:MM:SSZ" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Add "no minor upgrades" exclusion to control timing
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "controlled-rollout" \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Manual Upgrade Commands

For each cluster in sequence:

### Control Plane Upgrade
```bash
# Check 1.33 availability in Regular channel first
gcloud container get-server-config --region REGION \
  --format="yaml(channels.REGULAR.validVersions)"

# Upgrade control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.33.X-gke.Y

# Verify (wait 10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="value(currentMasterVersion)"
```

### Node Pool Upgrades
```bash
# List node pools
gcloud container node-pools list --cluster CLUSTER_NAME --region REGION

# Configure surge settings per pool type
# For stateless workloads:
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# For stateful/database workloads:
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade each node pool
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.33.X-gke.Y
```

## Validation Checklist per Phase

### Dev Validation (48h)
- [ ] All nodes at 1.33: `kubectl get nodes -o wide`
- [ ] System pods healthy: `kubectl get pods -n kube-system`
- [ ] Application smoke tests passing
- [ ] No deprecated API warnings in logs
- [ ] Metric collection functioning

### Staging Validation (48h)
- [ ] Full integration test suite passes
- [ ] Load testing shows no performance regression
- [ ] Monitoring/alerting functional
- [ ] Service mesh compatibility verified (if applicable)
- [ ] Database connectivity validated

### Production Validation (7d canary, 48h per cluster)
- [ ] Error rates within baseline (±5%)
- [ ] Latency (p95) within baseline (±10%)
- [ ] No increase in 5xx errors
- [ ] Resource utilization normal
- [ ] Customer-facing features functioning
- [ ] On-call incidents not elevated

## Risk Mitigation

### Before Starting
- [ ] Verify all clusters have PDBs on critical workloads
- [ ] Confirm adequate compute quota for surge upgrades
- [ ] Test 1.33 compatibility in dev first
- [ ] Review [GKE 1.33 release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) for breaking changes
- [ ] Backup stateful workload data

### Rollback Plan
If critical issues emerge:

**Immediate mitigation:**
```bash
# Apply "no upgrades" exclusion to halt auto-upgrades
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "rollback-hold" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades
```

**Node pool rollback (requires new pool creation):**
```bash
# Create new pool at 1.32
gcloud container node-pools create rollback-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.32.X-gke.Y \
  --machine-type MACHINE_TYPE \
  --num-nodes NUM_NODES

# Migrate workloads, then delete upgraded pool
```

## Communication Plan

### Stakeholder Updates
- **Week before each phase:** Email announcement with maintenance windows
- **Day of upgrade:** Slack notification when starting each cluster
- **Post-validation:** Status update with metrics comparison

### Escalation
- **Dev issues:** Platform team handles
- **Staging issues:** Include application teams in troubleshooting
- **Production issues:** Immediate escalation, consider rollback if customer impact

## Timeline Summary

| Week | Environment | Action | Validation Period |
|------|-------------|--------|------------------|
| 1 | Dev | Upgrade all 4 clusters | 48h per cluster |
| 2 | Staging | Upgrade all 4 clusters | 48h per cluster |
| 3 | Production | Upgrade 1 canary cluster | 7 days |
| 4 | Production | Upgrade remaining 3 clusters | 48h per cluster |

**Total timeline:** 4 weeks from start to finish

This progressive approach minimizes blast radius while ensuring thorough validation at each stage. The 7-day production canary period provides confidence before rolling out to business-critical clusters.