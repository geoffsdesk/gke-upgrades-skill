# GKE Multi-Environment Rollout Strategy

**Scope:** 12 Standard clusters across 3 environments → GKE 1.32 → 1.33  
**Channel:** All on Regular release channel  
**Timeline:** ~2-3 weeks total with validation gates

## Rollout Sequence

### Phase 1: Development (Week 1)
- **Clusters:** 4 dev clusters
- **Schedule:** Monday-Tuesday
- **Strategy:** Parallel upgrades within dev environment
- **Validation window:** 48 hours minimum

### Phase 2: Staging (Week 2) 
- **Clusters:** 4 staging clusters  
- **Schedule:** Wednesday-Thursday (after dev validation passes)
- **Strategy:** Parallel upgrades within staging environment
- **Validation window:** 72 hours minimum

### Phase 3: Production (Week 2-3)
- **Clusters:** 4 production clusters
- **Schedule:** Monday-Tuesday of following week (after staging validation passes)  
- **Strategy:** Sequential upgrades with 24-48h soak time between clusters
- **Validation window:** 1 week per cluster

## Upgrade Configuration

### Maintenance Windows
Configure staggered windows to prevent simultaneous upgrades:
```bash
# Dev clusters (parallel is OK)
gcloud container clusters update dev-cluster-1 \
  --maintenance-window-start "2024-01-08T02:00:00Z" \
  --maintenance-window-duration 6h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=MO"

# Staging clusters (parallel is OK) 
gcloud container clusters update staging-cluster-1 \
  --maintenance-window-start "2024-01-10T02:00:00Z" \
  --maintenance-window-duration 6h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=WE"

# Production clusters (sequential with 24h gaps)
gcloud container clusters update prod-cluster-1 \
  --maintenance-window-start "2024-01-15T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=MO"

gcloud container clusters update prod-cluster-2 \
  --maintenance-window-start "2024-01-16T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=TU"
# Continue pattern for prod-cluster-3,4
```

### Version Control Strategy
Use maintenance exclusions to control when minor upgrades happen:

```bash
# Apply "no minor or node" exclusion to all clusters initially
for cluster in dev-1 dev-2 dev-3 dev-4 staging-1 staging-2 staging-3 staging-4 prod-1 prod-2 prod-3 prod-4; do
  gcloud container clusters update $cluster \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
done
```

This prevents auto-upgrades to 1.33 until you manually trigger them, ensuring controlled progression.

## Detailed Week-by-Week Plan

### Week 1: Development Environment

**Monday (Day 1):**
- Remove minor exclusions from dev clusters
- Trigger control plane upgrades manually:
```bash
for cluster in dev-cluster-1 dev-cluster-2 dev-cluster-3 dev-cluster-4; do
  gcloud container clusters upgrade $cluster \
    --master \
    --cluster-version 1.33.X-gke.XXXX &
done
```

**Tuesday (Day 2):**
- Trigger node pool upgrades after CP upgrades complete:
```bash
# Configure surge settings first (example for typical dev workloads)
gcloud container node-pools update default-pool \
  --cluster dev-cluster-1 \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# Then upgrade (repeat for all dev clusters)
gcloud container node-pools upgrade default-pool \
  --cluster dev-cluster-1 \
  --cluster-version 1.33.X-gke.XXXX
```

**Wednesday-Thursday (Days 3-4):**
- Validate dev environment health
- Run smoke tests and integration tests
- Monitor error rates, latency, resource usage

### Week 2: Staging Environment

**Monday-Tuesday (Days 8-9):**
- **Go/No-Go Decision:** Dev validation results
- If GO: Remove minor exclusions from staging clusters and repeat upgrade process
- Focus on production-like workload testing

**Wednesday-Friday (Days 10-12):**
- Extended staging validation
- Performance testing under load
- Database/stateful workload validation
- Third-party integration testing

### Week 3: Production Environment  

**Monday (Day 15):**
- **Go/No-Go Decision:** Staging validation results
- If GO: Upgrade prod-cluster-1 only
- Monitor for 24-48 hours

**Wednesday (Day 17):**
- Upgrade prod-cluster-2 if cluster-1 is stable
- Continue sequential pattern

**Friday onwards:**
- Complete remaining prod clusters with 24-48h gaps
- Final validation and documentation

## Validation Gates

### Development Gate (required to proceed to staging):
- [ ] All dev clusters healthy (nodes Ready, system pods Running)
- [ ] No increase in error rates >5% baseline
- [ ] Application smoke tests passing
- [ ] No deprecated API warnings in logs

### Staging Gate (required to proceed to production):
- [ ] All staging clusters healthy 
- [ ] Performance tests within 10% of baseline
- [ ] Database/stateful workload integrity confirmed
- [ ] Load testing passed
- [ ] Integration tests with external services passed
- [ ] Security scans completed

### Production Progression Gate (between prod clusters):
- [ ] Previous prod cluster stable for 24-48h
- [ ] No increase in alerts or incidents
- [ ] Customer-facing metrics stable
- [ ] On-call team available for next cluster

## Pre-Upgrade Preparation

### Version Compatibility Check
```bash
# Verify 1.33 is available in Regular channel
gcloud container get-server-config --zone us-central1-a \
  --format="yaml(channels.REGULAR)"

# Check for deprecated APIs across all clusters
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```

### Workload Assessment
- [ ] Identify stateful workloads (databases, caches) in each environment
- [ ] Configure appropriate PDBs: `minAvailable: 1` for most workloads
- [ ] Verify no bare pods exist
- [ ] Check admission webhook compatibility with K8s 1.33

### Rollback Plan
- Control plane: Patch downgrades supported, minor downgrades require support ticket
- Node pools: Can create new pools at 1.32 and migrate workloads if needed
- Estimated rollback time: 2-4 hours per cluster

## Monitoring and Alerting

### Key Metrics to Watch
- API server latency (p95, p99)
- Pod startup times  
- Error rates by service
- Resource utilization (CPU, memory, disk)
- Network connectivity between services

### Alert Thresholds
- Error rate increase >5% sustained for >10 minutes → investigate
- Latency increase >20% sustained for >15 minutes → consider rollback
- Any customer-impacting incidents → pause rollout

## Emergency Procedures

### Upgrade Stuck/Failing
1. Check PDB status: `kubectl get pdb -A`
2. Look for resource constraints: `kubectl get events -A --field-selector reason=FailedScheduling`
3. Verify node pool surge settings allow progress
4. Contact GKE support if operation stuck >2 hours

### Critical Issue Found
1. Apply temporary maintenance exclusion to prevent further auto-upgrades
2. Document the issue and impact
3. Execute rollback plan if customer-impacting
4. Pause rollout until fix confirmed

## Success Criteria
- All 12 clusters successfully upgraded to 1.33
- No customer-impacting incidents during rollout
- All environments stable for 1 week post-upgrade
- Performance metrics within 5% of pre-upgrade baseline
- Documentation updated with lessons learned

**Estimated Total Timeline:** 2-3 weeks with proper validation gates  
**Resource Requirements:** On-call coverage during all production upgrade windows  
**Risk Level:** Medium (controlled progression with validation gates)