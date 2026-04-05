# GKE Multi-Environment Rollout Strategy

## Overview
**Scope:** 12 Standard clusters across 3 environments  
**Current:** GKE 1.32 (Regular channel)  
**Target:** GKE 1.33  
**Strategy:** Progressive rollout with validation gates

## Recommended Rollout Sequence

### Phase 1: Dev Environment (4 clusters)
- **Timeline:** Week 1
- **Approach:** Parallel upgrades within dev
- **Validation:** 48-72 hour soak period

### Phase 2: Staging Environment (4 clusters) 
- **Timeline:** Week 2 (after dev validation)
- **Approach:** Sequential upgrades with 24h gaps
- **Validation:** Full integration test suite + 48h soak

### Phase 3: Production Environment (4 clusters)
- **Timeline:** Week 3-4 (after staging validation)
- **Approach:** One cluster at a time with extended validation
- **Validation:** Business metrics monitoring + 72h soak per cluster

## Implementation Options

### Option A: Automated with Rollout Sequencing (Recommended)

Configure GKE's native rollout sequencing to automate the progression:

```bash
# Set up fleet memberships (one-time setup)
gcloud container fleet memberships register dev-fleet \
    --gke-cluster=projects/PROJECT_ID/locations/REGION/clusters/dev-cluster-1 \
    --project=PROJECT_ID

# Configure rollout sequence: dev → staging → prod
gcloud container fleet clusterupgrade update \
    --project=PROJECT_ID \
    --upstream-fleet=dev-fleet \
    --default-upgrade-soaking=72h

# Set maintenance exclusions to control minor version timing
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-scope no_minor_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

**Benefits:**
- Automated progression with built-in soak periods
- GKE handles upgrade orchestration
- Consistent timing across environments

**Trigger the sequence:**
```bash
# Remove exclusions from dev clusters to start the cascade
gcloud container clusters update dev-cluster-1 \
    --zone ZONE \
    --remove-maintenance-exclusion-name EXCLUSION_NAME
```

### Option B: Manual Controlled Rollout

If you prefer manual control or need custom validation between phases:

#### Week 1: Dev Environment
```bash
# Upgrade all dev clusters in parallel
for cluster in dev-cluster-1 dev-cluster-2 dev-cluster-3 dev-cluster-4; do
  gcloud container clusters upgrade $cluster \
    --zone ZONE \
    --cluster-version 1.33.x-gke.xxxx &
done

# Monitor progress
watch 'gcloud container clusters list --filter="name ~ dev-" --format="table(name,currentMasterVersion,status)"'
```

#### Week 2: Staging Environment (after dev validation)
```bash
# Sequential upgrades with 24h gaps
gcloud container clusters upgrade staging-cluster-1 \
  --zone ZONE \
  --cluster-version 1.33.x-gke.xxxx

# Wait 24h, validate, then proceed to next
gcloud container clusters upgrade staging-cluster-2 \
  --zone ZONE \
  --cluster-version 1.33.x-gke.xxxx
```

#### Week 3-4: Production Environment
```bash
# One cluster at a time with extended validation
gcloud container clusters upgrade prod-cluster-1 \
  --zone ZONE \
  --cluster-version 1.33.x-gke.xxxx

# Wait 72h + business validation before next cluster
```

## Pre-Rollout Configuration

### Maintenance Windows (All Clusters)
```bash
# Configure weekend maintenance windows
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-duration 6h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### Node Pool Upgrade Strategy
For all Standard clusters, configure appropriate surge settings:

```bash
# Stateless workload pools
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# Database/stateful pools  
gcloud container node-pools update database-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

## Validation Gates

### Dev Environment Validation (48-72h)
- [ ] All clusters at 1.33
- [ ] No deprecated API warnings
- [ ] Application smoke tests passing
- [ ] No increase in error rates or latency
- [ ] System pods healthy across all clusters

### Staging Environment Validation (48h per cluster)
- [ ] Full integration test suite passes
- [ ] Load testing confirms performance baseline
- [ ] Database connectivity and migrations work
- [ ] External integrations functional
- [ ] Monitoring/alerting systems operational

### Production Environment Validation (72h per cluster)
- [ ] Business KPIs within acceptable range
- [ ] Customer-facing services responsive
- [ ] Payment/critical path functions verified
- [ ] Rollback plan confirmed and tested
- [ ] On-call team acknowledges health

## Rollback Strategy

### Immediate Issues (during upgrade)
```bash
# Cancel in-progress node pool upgrade if needed
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE

# For control plane issues, contact GKE support immediately
# Node pools can be rolled back by creating new pools at 1.32
```

### Post-Upgrade Issues
```bash
# Create replacement node pool at previous version
gcloud container node-pools create rollback-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxxx \
  --num-nodes 3

# Cordon upgraded nodes and migrate workloads
kubectl cordon -l cloud.google.com/gke-nodepool=default-pool
```

## Communication Plan

### Week Before: Stakeholder Notification
- Dev teams: Upgrade schedule and expected changes
- Platform team: On-call coverage during rollout
- Business stakeholders: Maintenance windows and risk mitigation

### During Rollout: Status Updates
- Slack/email updates after each environment completion
- Incident response contacts clearly defined
- Validation results shared with stakeholders

### Post-Rollout: Lessons Learned
- Document any issues encountered and solutions
- Update upgrade procedures based on experience
- Plan next minor version upgrade timeline

## Monitoring and Alerting

### Key Metrics to Track
```bash
# Cluster health
kubectl get nodes --all-namespaces
kubectl get pods --all-namespaces | grep -v Running

# Application health
# Monitor your existing SLIs (error rates, latency, throughput)
```

### Alerts to Configure
- Node upgrade failures
- Pod eviction spikes during drain
- API server latency increases
- Application error rate increases

## Timeline Summary

| Week | Environment | Action | Validation Period |
|------|------------|--------|------------------|
| 1 | Dev (4 clusters) | Parallel upgrade | 72h soak |
| 2 | Staging (4 clusters) | Sequential upgrade | 48h per cluster |
| 3-4 | Production (4 clusters) | One-by-one upgrade | 72h per cluster |

**Total Duration:** 4 weeks  
**Risk Mitigation:** Progressive validation with rollback capability at each stage

This strategy balances speed (parallel dev upgrades) with safety (sequential prod rollout) while leveraging GKE's native rollout sequencing capabilities where possible.