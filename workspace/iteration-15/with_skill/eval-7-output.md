# Multi-Environment GKE Upgrade Strategy: 1.32 → 1.33

## Environment Overview
- **12 Standard clusters** across 3 environments (4 clusters each)
- **Current version:** 1.32 (all clusters)
- **Target version:** 1.33
- **Release channel:** Regular (all environments)
- **Upgrade type:** Minor version upgrade (1 step)

## Recommended Rollout Strategy

### Option A: Sequential Environment Rollout (Recommended)
**Best for:** Risk-averse organizations with clear environment boundaries

```
Phase 1: Dev (Week 1)
├── Dev clusters 1-4 (parallel)
├── Soak period: 3-5 days
└── Validation checkpoint

Phase 2: Staging (Week 2) 
├── Staging clusters 1-4 (parallel)
├── Soak period: 5-7 days  
└── Validation checkpoint

Phase 3: Production (Week 3)
├── Prod cluster 1
├── Soak period: 24-48 hours
├── Prod clusters 2-3 (parallel)
├── Soak period: 24 hours
└── Prod cluster 4 (final)
```

### Option B: Wave-Based Rollout
**Best for:** Organizations with mixed-criticality workloads across environments

```
Wave 1: Low-risk clusters (Week 1)
├── Dev clusters 1-4 + Staging cluster 1
├── Soak: 3-5 days

Wave 2: Medium-risk clusters (Week 2)
├── Staging clusters 2-4 + Prod cluster 1 (canary)
├── Soak: 5-7 days

Wave 3: High-criticality production (Week 3)
├── Prod clusters 2-4
├── Soak: 24-48 hours between clusters
```

## Implementation Plan

### Pre-Upgrade Setup (Week 0)

1. **Configure maintenance windows** (off-peak hours for each environment):
```bash
# Example: Saturday 2-6 AM local time
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "YYYY-MM-DDTSAT02:00:00Z" \
  --maintenance-window-end "YYYY-MM-DDTSAT06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

2. **Set up maintenance exclusions for controlled timing**:
```bash
# Block auto-upgrades until manual initiation
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "manual-upgrade-control" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-03-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

3. **Verify 1.33 availability in Regular channel**:
```bash
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels.regular.validVersions)" | grep 1.33
```

### Phase 1: Development Environment (Week 1)

**Target:** All 4 dev clusters in parallel

**Pre-flight checks:**
- [ ] Deprecated API usage scan across all dev clusters
- [ ] Third-party operator compatibility verified for 1.33
- [ ] Development team notified of upgrade window

**Execution (parallel across dev clusters):**
```bash
# For each dev cluster
# 1. Control plane upgrade
gcloud container clusters upgrade DEV_CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.33.x-gke.latest

# 2. Node pool upgrade (configure surge first)
gcloud container node-pools update default-pool \
  --cluster DEV_CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade default-pool \
  --cluster DEV_CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.33.x-gke.latest
```

**Validation criteria:**
- All system pods healthy
- Application smoke tests pass
- No deprecated API warnings
- Performance within baseline (3-5 days soak)

### Phase 2: Staging Environment (Week 2)

**Target:** All 4 staging clusters in parallel (after dev validation)

**Pre-flight checks:**
- [ ] Dev environment lessons learned applied
- [ ] Load testing environment prepared
- [ ] Staging workload owners notified

**Execution:** Same command pattern as dev, but with staging cluster names

**Validation criteria:**
- Full integration test suite passes
- Load testing validates performance
- Security scans complete
- Extended soak period (5-7 days)

### Phase 3: Production Environment (Week 3)

**Target:** Staged production rollout (1 → 2-3 → 4)

**Cluster prioritization:**
1. **First:** Least critical prod cluster or designated canary
2. **Second batch:** Core production clusters (parallel)
3. **Final:** Most critical/highest-traffic cluster

**Pre-flight checks per production cluster:**
- [ ] Business stakeholders notified
- [ ] On-call team briefed and available  
- [ ] Rollback plan reviewed
- [ ] Monitoring dashboards ready

**Conservative production settings:**
```bash
# More conservative surge settings for production
gcloud container node-pools update PROD_NODE_POOL \
  --cluster PROD_CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

## Alternative: Release Channel + Auto-Upgrade Strategy

For teams preferring less manual orchestration, consider this approach:

**Setup:**
- **Dev:** Migrate to Rapid channel (gets 1.33 first)
- **Staging:** Keep Regular channel  
- **Prod:** Consider Stable channel (gets 1.33 after additional validation)

**Control mechanism:** Use "no minor" maintenance exclusions to control timing:
```bash
# Remove exclusion when ready for each environment to auto-upgrade
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "manual-upgrade-control"
```

## Risk Mitigation

### Rollback Strategy
- **Control plane:** Minor version rollback requires GKE support (not customer-initiated)
- **Node pools:** Can be rolled back by creating new pools at 1.32 and migrating workloads
- **Two-step upgrade option:** Use `--control-plane-soak-duration=24h` for 1-day rollback window on control plane

### Monitoring & Validation
Set up alerts for:
- Pod crash loops or restarts
- API server latency increases  
- Webhook failures (common cause of post-upgrade issues)
- Application error rate spikes

### Emergency Procedures
- **Pause rollout:** Apply immediate "no upgrades" exclusion to remaining clusters
- **Escalation path:** GKE support for control plane issues
- **Communication plan:** Stakeholder notification templates prepared

## Timeline Summary

| Week | Environment | Action | Validation Period |
|------|-------------|--------|-------------------|
| 0 | All | Setup windows, exclusions | - |
| 1 | Dev (4 clusters) | Parallel upgrade | 3-5 days |
| 2 | Staging (4 clusters) | Parallel upgrade | 5-7 days |  
| 3 | Prod cluster 1 | Canary upgrade | 24-48 hours |
| 3 | Prod clusters 2-3 | Parallel upgrade | 24 hours |
| 3-4 | Prod cluster 4 | Final upgrade | Ongoing monitoring |

**Total duration:** ~4 weeks from start to completion
**Risk level:** Low (staged approach with validation gates)

This strategy provides controlled rollout with validation gates while minimizing business disruption. The maintenance exclusions give you full control over timing while still leveraging GKE's automated upgrade capabilities.