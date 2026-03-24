# GKE Multi-Environment Rollout Strategy

## Overview
- **Scope**: 12 Standard clusters across 3 environments (4 clusters each)
- **Current version**: 1.32
- **Target version**: 1.33
- **Channel**: Regular (all environments)
- **Strategy**: Progressive rollout with validation gates

## Environment Rollout Sequence

Since all environments are on the same Regular channel, we'll use **manual minor version control** to ensure proper sequencing:

### Phase 1: Configure Minor Version Control
Apply "no minor upgrades" exclusion to all environments to prevent auto-upgrades during rollout:

```bash
# Apply to all 12 clusters
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "rollout-control" \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

This allows patches but blocks minor version auto-upgrades, giving you control over 1.33 progression.

## Rollout Timeline

| Phase | Environment | Duration | Soak Time |
|-------|-------------|----------|-----------|
| 1 | Dev (4 clusters) | Week 1 | 3-5 days |
| 2 | Staging (4 clusters) | Week 2 | 5-7 days |
| 3 | Production (4 clusters) | Week 3 | Ongoing |

## Phase 1: Development Environment

### Pre-rollout Setup
```bash
# Verify 1.33 availability in Regular channel
gcloud container get-server-config --zone us-central1-a \
  --format="yaml(channels)" | grep -A 10 "REGULAR"

# Check deprecated API usage across dev clusters
for cluster in dev-cluster-1 dev-cluster-2 dev-cluster-3 dev-cluster-4; do
  echo "=== $cluster ==="
  kubectl --context=$cluster get --raw /metrics | grep apiserver_request_total | grep deprecated
done
```

### Dev Cluster Upgrade Sequence
Upgrade dev clusters in parallel (acceptable risk for dev environment):

```bash
# Control plane upgrades (can run in parallel)
gcloud container clusters upgrade dev-cluster-1 --zone ZONE --master --cluster-version 1.33.x-gke.latest &
gcloud container clusters upgrade dev-cluster-2 --zone ZONE --master --cluster-version 1.33.x-gke.latest &
gcloud container clusters upgrade dev-cluster-3 --zone ZONE --master --cluster-version 1.33.x-gke.latest &
gcloud container clusters upgrade dev-cluster-4 --zone ZONE --master --cluster-version 1.33.x-gke.latest &

# Wait for control planes to complete
wait

# Node pool upgrades (parallel within each cluster)
for cluster in dev-cluster-{1..4}; do
  for pool in $(gcloud container node-pools list --cluster=$cluster --zone=ZONE --format="value(name)"); do
    gcloud container node-pools upgrade $pool \
      --cluster $cluster \
      --zone ZONE \
      --cluster-version 1.33.x-gke.latest
  done
done
```

### Dev Validation (3-5 days)
- [ ] All dev workloads healthy
- [ ] API compatibility validated
- [ ] Performance regression testing
- [ ] Integration test suites passing
- [ ] No deprecated API warnings in logs

## Phase 2: Staging Environment

### Prerequisites
- [ ] Dev environment stable for 3+ days
- [ ] No critical issues identified
- [ ] Staging maintenance window scheduled

### Staging Cluster Upgrade Sequence
Upgrade staging clusters sequentially (higher risk tolerance than prod):

```bash
# Cluster 1
gcloud container clusters upgrade staging-cluster-1 --zone ZONE --master --cluster-version 1.33.x-gke.latest
# Wait for control plane, then node pools
for pool in $(gcloud container node-pools list --cluster=staging-cluster-1 --zone=ZONE --format="value(name)"); do
  gcloud container node-pools upgrade $pool --cluster staging-cluster-1 --zone ZONE --cluster-version 1.33.x-gke.latest
done

# Validate staging-cluster-1 for 24-48h before proceeding

# Repeat for remaining staging clusters with 24h gaps
```

### Staging Validation (5-7 days)
- [ ] Load testing with production-like traffic
- [ ] End-to-end testing
- [ ] Performance benchmarking
- [ ] Security scanning
- [ ] Disaster recovery testing

## Phase 3: Production Environment

### Prerequisites
- [ ] Staging environment stable for 5+ days
- [ ] Load testing results within acceptable thresholds
- [ ] Go/no-go decision from stakeholders
- [ ] Production maintenance windows scheduled

### Production Cluster Upgrade Strategy
Upgrade production clusters one at a time with maximum soak time:

#### Recommended Node Pool Strategy
For production Standard clusters, use **surge upgrade** with conservative settings:

```bash
# Configure surge settings per node pool type
# Stateless application pools
gcloud container node-pools update app-pool \
  --cluster prod-cluster-1 \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# Database/stateful pools  
gcloud container node-pools update db-pool \
  --cluster prod-cluster-1 \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# GPU pools (if any) - maxUnavailable is the primary lever
gcloud container node-pools update gpu-pool \
  --cluster prod-cluster-1 \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

#### Production Rollout Schedule

**Week 3: Prod Cluster 1**
```bash
# Control plane upgrade
gcloud container clusters upgrade prod-cluster-1 \
  --zone ZONE \
  --master \
  --cluster-version 1.33.x-gke.latest

# Node pool upgrades (sequential within cluster)
for pool in $(gcloud container node-pools list --cluster=prod-cluster-1 --zone=ZONE --format="value(name)"); do
  echo "Upgrading pool: $pool"
  gcloud container node-pools upgrade $pool \
    --cluster prod-cluster-1 \
    --zone ZONE \
    --cluster-version 1.33.x-gke.latest
  
  # Validate after each pool
  kubectl get pods -A | grep -v Running
  kubectl get nodes -l cloud.google.com/gke-nodepool=$pool
done
```

**Soak period: 3-5 days between production clusters**

**Week 4: Prod Clusters 2-4** (repeat process)

## Maintenance Windows & Controls

### Recommended Maintenance Windows
```bash
# Configure weekend maintenance windows for all clusters
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-02-03T02:00:00Z" \
  --maintenance-window-end "2024-02-03T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### Maintenance Exclusions Already Applied
The "no minor upgrades" exclusions prevent auto-upgrades while allowing patches. Remove them after manual rollout completes:

```bash
# After all clusters upgraded, remove exclusions to resume auto-upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "rollout-control"
```

## Monitoring & Validation

### Health Checks Per Phase
```bash
# Cluster health validation
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed
kubectl get pdb --all-namespaces

# Version verification
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Workload health
kubectl get deployments -A
kubectl get statefulsets -A
```

### Success Criteria
- [ ] All nodes at target version 1.33
- [ ] All system pods healthy
- [ ] Application health checks passing
- [ ] No increase in error rates/latency
- [ ] No deprecated API usage warnings

## Rollback Strategy

### Control Plane Rollback
Control plane minor version rollback requires GKE support involvement. **Prevention is key** - validate thoroughly in dev/staging.

### Node Pool Rollback
If issues arise, create new node pools at the previous version:

```bash
# Emergency rollback: create new pool at 1.32
gcloud container node-pools create rollback-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.version \
  --num-nodes 3 \
  --machine-type e2-standard-4

# Cordon problematic 1.33 nodes and drain workloads
kubectl cordon -l cloud.google.com/gke-nodepool=original-pool
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data

# Delete problematic pool after workloads migrated
gcloud container node-pools delete original-pool --cluster CLUSTER_NAME --zone ZONE
```

## Communication Plan

### Stakeholder Updates
- **Weekly progress reports** during rollout
- **Immediate notification** of any issues or delays
- **Go/no-go checkpoints** before each production cluster
- **Post-rollout retrospective** and lessons learned

### Key Contacts
- Platform team lead (on-call during production upgrades)
- Application teams (notified of upgrade windows)
- SRE team (monitoring alerts configured)

## Timeline Summary

| Week | Activity | Risk Level |
|------|----------|------------|
| Week 1 | Dev environment (4 clusters) | Low |
| Week 2 | Staging environment (4 clusters) | Medium |
| Week 3-4 | Production environment (1 cluster/week) | High |
| Week 5 | Cleanup and retrospective | Low |

**Total duration**: 4-5 weeks with proper validation gates and soak periods.

This strategy balances speed with safety, using your existing Regular channel setup while maintaining strict control over the minor version progression across environments.