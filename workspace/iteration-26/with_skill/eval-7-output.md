# GKE Rollout Strategy: Regular Channel 1.32 → 1.33 Upgrade

## Overview
- **Clusters:** 12 Standard clusters (4 dev, 4 staging, 4 prod)
- **Current version:** 1.32.x → **Target:** 1.33.x
- **Channel:** Regular (all environments)
- **Strategy:** Progressive rollout with validation gates

## Recommended Approach: Rollout Sequencing + Manual Control

Since all environments are on the **same channel** (Regular), you can leverage **GKE rollout sequencing** to automatically orchestrate the upgrade order across environments while maintaining manual control over minor version timing.

### Configuration Steps

1. **Set up rollout sequencing (one-time setup):**
```bash
# Configure fleet progression: dev → staging → prod
gcloud container fleet clusterupgrade update \
    --project=PROJECT_ID \
    --upstream-fleet=dev-fleet-project-id \
    --default-upgrade-soaking=48h  # 2-day soak between environments

# Apply to staging fleet (waits for dev)
gcloud container fleet clusterupgrade update \
    --project=STAGING_PROJECT_ID \
    --upstream-fleet=dev-fleet-project-id \
    --default-upgrade-soaking=72h  # 3-day soak before prod

# Apply to prod fleet (waits for staging)
gcloud container fleet clusterupgrade update \
    --project=PROD_PROJECT_ID \
    --upstream-fleet=staging-fleet-project-id \
    --default-upgrade-soaking=72h
```

2. **Add "no minor" exclusions to all clusters:**
```bash
# Apply to all 12 clusters to prevent auto-minor upgrades
for cluster in dev-cluster-{1..4} staging-cluster-{1..4} prod-cluster-{1..4}; do
    gcloud container clusters update $cluster \
        --zone ZONE \
        --add-maintenance-exclusion-scope no_minor_upgrades \
        --add-maintenance-exclusion-until-end-of-support
done
```

3. **Configure maintenance windows (staggered within environments):**
```bash
# Dev clusters: Tuesday 2-4 AM
# Staging clusters: Wednesday 2-4 AM  
# Prod clusters: Saturday 2-6 AM (longer window)
```

## Rollout Timeline

### Week 1: Development Environment
**Trigger:** When 1.33 becomes available as auto-upgrade target in Regular channel

**Day 1-2: Dev Validation**
- Manually trigger 1.33 upgrade on dev-cluster-1 (canary)
- Run comprehensive test suite
- Validate application compatibility, deprecated APIs
- Monitor for 48 hours

**Day 3-4: Dev Fleet Rollout**
- If canary successful, trigger remaining dev clusters
- Rollout sequencing ensures proper soak time between dev clusters
- All 4 dev clusters complete within 48 hours

### Week 2: Staging Environment
**Trigger:** Automatic (after dev fleet soak period)

**Day 8-10: Staging Validation**
- Rollout sequencing automatically starts staging after dev soak
- staging-cluster-1 upgrades first (internal sequencing)
- Production-like workload testing
- Performance regression testing
- 72-hour soak period

**Day 11-12: Staging Fleet Complete**
- Remaining staging clusters follow sequencing
- Load testing with production traffic patterns

### Week 3: Production Environment  
**Trigger:** Automatic (after staging fleet soak period)

**Day 15-17: Production Rollout**
- Rollout sequencing automatically starts prod after staging soak
- prod-cluster-1 upgrades first
- 25% of production traffic validation
- Monitor business metrics, SLAs

**Day 18-21: Production Fleet Complete**
- Remaining prod clusters follow sequencing
- Full production traffic validation
- Final verification across all environments

## Per-Cluster Upgrade Commands

### Manual trigger process (when ready for each environment):

**Control Plane:**
```bash
gcloud container clusters upgrade CLUSTER_NAME \
    --zone ZONE \
    --master \
    --cluster-version 1.33.x-gke.xxxx
```

**Node Pools (Standard clusters):**
```bash
# Configure conservative surge for production
gcloud container node-pools update default-pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 1 \
    --max-unavailable-upgrade 0

# Upgrade node pool
gcloud container node-pools upgrade default-pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version 1.33.x-gke.xxxx
```

## Validation Gates

### Dev Environment Gates
- [ ] All pods running and healthy
- [ ] Application smoke tests pass
- [ ] No deprecated API warnings in logs
- [ ] Monitoring/alerting functional
- [ ] 48-hour stability period

### Staging Environment Gates
- [ ] Performance benchmarks within 5% of baseline
- [ ] Integration test suite passes
- [ ] Load testing at 80% production scale
- [ ] Database migrations successful (if applicable)
- [ ] 72-hour stability period

### Production Environment Gates
- [ ] First cluster: 25% traffic for 24 hours
- [ ] SLA metrics within thresholds
- [ ] Error rates < baseline + 0.1%
- [ ] Latency p99 < baseline + 50ms
- [ ] Business metrics stable

## Rollback Strategy

**If issues discovered:**

1. **During soak period:** Apply temporary "no upgrades" exclusion to pause rollout:
```bash
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "pause-rollout" \
    --add-maintenance-exclusion-scope no_upgrades \
    --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
    --add-maintenance-exclusion-end-time $(date -u -d "+7 days" +"%Y-%m-%dT%H:%M:%SZ")
```

2. **For severe issues:** Create new node pools at 1.32, migrate workloads, delete upgraded pools

3. **Control plane rollback:** Requires GKE support - not customer-initiated

## Monitoring & Notifications

**Enable scheduled upgrade notifications:**
```bash
# Get 72-hour advance notice
gcloud container clusters update CLUSTER_NAME \
    --enable-scheduled-upgrades
```

**Monitor upgrade progress:**
```bash
# Check auto-upgrade status
gcloud container clusters get-upgrade-info CLUSTER_NAME --zone ZONE

# Monitor operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE
```

## Key Benefits of This Approach

1. **Automated orchestration** - Rollout sequencing handles environment progression
2. **Manual control** - "No minor" exclusions let you control timing
3. **Built-in validation** - Soak periods between environments
4. **Consistent process** - Same channel ensures version consistency
5. **Rollback safety** - Can pause/stop at any environment boundary

## Timeline Summary
- **Week 1:** Dev environment (4 clusters)
- **Week 2:** Staging environment (4 clusters)  
- **Week 3:** Production environment (4 clusters)
- **Total duration:** ~21 days with validation periods

This approach leverages GKE's native rollout sequencing while giving you full control over when the minor version upgrade begins. The "no minor" exclusions prevent unwanted auto-upgrades while patches continue to flow automatically.