# GKE Multi-Environment Upgrade Strategy

## Overview
**Scope:** 12 Standard clusters across 3 environments  
**Current version:** 1.28  
**Target version:** 1.30  
**Upgrade path:** 1.28 → 1.29 → 1.30 (sequential minor versions recommended)  

## Release Channel Strategy

| Environment | Channel | Clusters | Version Flow |
|-------------|---------|----------|--------------|
| **Dev** | Rapid | 4 clusters | Gets 1.29 and 1.30 first |
| **Staging** | Regular | 4 clusters | Gets versions ~2-4 weeks after Rapid |
| **Prod** | Stable | 4 clusters | Gets versions ~4-8 weeks after Regular |

## Rollout Timeline

### Phase 1: Dev Environment (Week 1-2)
**Target:** 1.28 → 1.29
- Day 1-2: Dev-cluster-1 (canary)
- Day 3-4: Dev-cluster-2, Dev-cluster-3 (parallel)
- Day 5-6: Dev-cluster-4
- Day 7-10: Soak time, validate applications

**Target:** 1.29 → 1.30 (once available in Rapid)
- Day 11-12: Dev-cluster-1 (canary)
- Day 13-14: Remaining dev clusters (parallel if stable)

### Phase 2: Staging Environment (Week 3-4)
Wait for 1.29 availability in Regular channel

**Target:** 1.28 → 1.29
- Day 1-2: Staging-cluster-1 (canary)
- Day 3-4: Staging-cluster-2, Staging-cluster-3 (parallel)
- Day 5-6: Staging-cluster-4
- Day 7-10: Soak time, full regression testing

**Target:** 1.29 → 1.30 (once available in Regular)
- Similar pattern once Regular channel has 1.30

### Phase 3: Production Environment (Week 5-6)
Wait for 1.29 availability in Stable channel

**Target:** 1.28 → 1.29
- Day 1-2: Prod-cluster-1 (lowest risk workloads)
- Day 3-4: Prod-cluster-2
- Day 5-6: Prod-cluster-3
- Day 7-8: Prod-cluster-4 (critical workloads last)
- Day 9-14: Extended soak time

## Pre-Rollout Preparation

### Week -2: Version Availability Check
```bash
# Check current version availability across channels
for ZONE in us-central1-a us-east1-b europe-west1-c; do
  echo "=== Zone: $ZONE ==="
  gcloud container get-server-config --zone $ZONE \
    --format="yaml(channels)" | grep -A 10 -B 2 "1.29\|1.30"
done
```

### Week -1: Cluster Assessment
```bash
# For each cluster, capture baseline
CLUSTERS=(
  "dev-cluster-1:us-central1-a"
  "dev-cluster-2:us-central1-a"
  # ... add all 12 clusters
)

for cluster_info in "${CLUSTERS[@]}"; do
  CLUSTER=$(echo $cluster_info | cut -d: -f1)
  ZONE=$(echo $cluster_info | cut -d: -f2)
  
  echo "=== $CLUSTER ==="
  # Current versions
  gcloud container clusters describe $CLUSTER --zone $ZONE \
    --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"
  
  # Deprecated APIs
  kubectl --context=${CLUSTER} get --raw /metrics | grep apiserver_request_total | grep deprecated
  
  # Workload inventory
  kubectl --context=${CLUSTER} get deployments,statefulsets,daemonsets -A
done
```

## Surge Strategy by Environment

### Dev Clusters
- **Stateless pools:** `maxSurge=3, maxUnavailable=0`
- **Stateful pools:** `maxSurge=1, maxUnavailable=0`
- **Priority:** Speed over cost efficiency

### Staging Clusters
- **Stateless pools:** `maxSurge=2, maxUnavailable=0`
- **Stateful pools:** `maxSurge=1, maxUnavailable=0`
- **Priority:** Production-like testing

### Production Clusters
- **Stateless pools:** `maxSurge=1, maxUnavailable=0`
- **Stateful pools:** `maxSurge=1, maxUnavailable=0`
- **Priority:** Maximum safety and PDB respect

## Maintenance Windows

```bash
# Dev: Flexible hours (business hours OK)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start 2024-01-15T14:00:00Z \
  --maintenance-window-end 2024-01-15T18:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"

# Staging: Off-hours
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start 2024-01-15T02:00:00Z \
  --maintenance-window-end 2024-01-15T06:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA,SU"

# Production: Weekend off-peak
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start 2024-01-13T06:00:00Z \
  --maintenance-window-end 2024-01-13T10:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Success Criteria & Gates

### Dev → Staging Gate
- [ ] All 4 dev clusters successfully at 1.29
- [ ] No application regressions in dev environment
- [ ] 1.29 available in Regular channel
- [ ] Dev workloads stable for 72+ hours

### Staging → Prod Gate
- [ ] All 4 staging clusters successfully at 1.29
- [ ] Full regression test suite passed
- [ ] Performance baselines maintained
- [ ] 1.29 available in Stable channel
- [ ] Staging workloads stable for 7+ days

### Phase Completion Gate
- [ ] Control plane and all node pools at target version
- [ ] All workloads healthy and at desired replica counts
- [ ] No increase in error rates or latency
- [ ] Monitoring and alerting functional

## Risk Mitigation

### Canary Strategy
- Always upgrade lowest-risk cluster in each environment first
- 24-48 hour soak time before proceeding to remaining clusters
- Ability to pause rollout if issues detected

### Rollback Plan
- Node pool rollback requires creating new pools at previous version
- Control plane rollback requires GKE support involvement
- Application rollback via deployment history

### Communication Plan
- Slack channel: `#gke-upgrades-2024`
- Daily standup updates during active upgrade weeks
- Stakeholder notifications 48 hours before production upgrades

## Monitoring During Rollout

```bash
# Real-time cluster health dashboard
for CLUSTER in dev-cluster-1 staging-cluster-1 prod-cluster-1; do
  echo "=== $CLUSTER Health ==="
  kubectl --context=$CLUSTER get nodes | grep -v Ready || echo "All nodes ready"
  kubectl --context=$CLUSTER get pods -A | grep -v Running | grep -v Completed | wc -l
done
```

Set up alerts for:
- Node NotReady conditions
- Pod CrashLoopBackOff
- Increased error rates in application metrics
- PDB violations

## Estimated Timeline
- **Total duration:** 6-8 weeks
- **Dev environment:** 2 weeks
- **Staging environment:** 2 weeks  
- **Production environment:** 2-4 weeks
- **Buffer for channel availability:** Variable (monitor [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule))

This strategy leverages your release channel setup to validate each version in lower environments before production exposure, with appropriate soak times and safety measures at each stage.