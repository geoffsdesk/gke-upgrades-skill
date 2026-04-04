# GKE Multi-Environment Rollout Strategy
**12 Standard Clusters: 1.32 → 1.33 (Regular Channel)**

## Executive Summary

**Recommended approach:** Progressive rollout with natural channel sequencing + maintenance window staggering. Since all clusters are on Regular channel, they'll all receive 1.33 at roughly the same time when it becomes the auto-upgrade target. We'll use maintenance windows to control timing and create proper dev → staging → prod sequencing.

**Timeline:** 2-3 weeks total (1 week per environment tier with validation periods)

## Environment Topology & Strategy

```
Dev (4 clusters)     → Week 1: Tuesday-Thursday
Staging (4 clusters) → Week 2: Tuesday-Thursday  
Prod (4 clusters)    → Week 3: Tuesday-Thursday
```

**Key insight:** Since all clusters are on the same Regular channel, we can't use GKE rollout sequencing (which requires different channels or fleet configuration). Instead, we'll use maintenance window timing to create artificial sequencing.

## Detailed Rollout Plan

### Phase 1: Dev Environment (Week 1)
**Clusters:** dev-cluster-1, dev-cluster-2, dev-cluster-3, dev-cluster-4

**Timeline:** Tuesday 2:00-6:00 AM, Wednesday 2:00-6:00 AM (2 clusters per night)

**Strategy:**
- Manual control plane upgrades during maintenance windows
- Natural node auto-upgrades following CP upgrade
- 1-day soak between cluster pairs, 1 week soak before staging

```bash
# Configure maintenance windows for dev clusters
gcloud container clusters update dev-cluster-1 \
  --zone ZONE \
  --maintenance-window-start "2024-XX-XXTXX:XX:XXZ" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=TU"

gcloud container clusters update dev-cluster-2 \
  --zone ZONE \
  --maintenance-window-start "2024-XX-XXTXX:XX:XXZ" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=TU"

# Repeat for clusters 3,4 on Wednesday
```

### Phase 2: Staging Environment (Week 2)
**Clusters:** staging-cluster-1, staging-cluster-2, staging-cluster-3, staging-cluster-4

**Prerequisites:**
- [ ] Dev clusters healthy for 1 week at 1.33
- [ ] No critical issues discovered in dev
- [ ] Application compatibility validated

**Same maintenance window pattern as dev, offset by 1 week**

### Phase 3: Production Environment (Week 3)
**Clusters:** prod-cluster-1, prod-cluster-2, prod-cluster-3, prod-cluster-4

**Prerequisites:**
- [ ] Staging clusters healthy for 1 week at 1.33
- [ ] Performance benchmarks within acceptable range
- [ ] All stakeholder approvals obtained

**Enhanced controls for production:**
```bash
# Add disruption intervals for production (optional - for max control)
gcloud container clusters update prod-cluster-1 \
  --zone ZONE \
  --maintenance-minor-version-disruption-interval=2592000s \
  --maintenance-window-start "2024-XX-XXTXX:XX:XXZ" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=TU"
```

## Node Pool Upgrade Strategy (All Clusters)

**Recommended settings per pool type:**

```bash
# Web/API pools (stateless)
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# Database/stateful pools  
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# GPU pools (if any)
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

## Pre-Flight Validation (Run Before Each Phase)

```bash
# Verify 1.33 availability in Regular channel
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels.regular)"

# Check for deprecated API usage across all clusters
for cluster in cluster-1 cluster-2 cluster-3 cluster-4; do
  echo "=== Checking $cluster ==="
  kubectl --context=$cluster get --raw /metrics | grep deprecated || echo "No deprecated APIs found"
done

# Verify PDB configurations
kubectl get pdb -A -o wide
```

## Alternative: Maintenance Exclusion Approach

If you prefer **manual control over timing** rather than relying on auto-upgrade timing:

```bash
# Block auto-upgrades on all clusters initially
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "rollout-control" \
  --add-maintenance-exclusion-start-time "2024-XX-XXTXX:XX:XXZ" \
  --add-maintenance-exclusion-end-time "2024-XX-XXTXX:XX:XXZ" \
  --add-maintenance-exclusion-scope no_minor_upgrades

# Then manually trigger upgrades in sequence:
# Week 1: Remove exclusion from dev clusters + manual upgrade
# Week 2: Remove exclusion from staging clusters + manual upgrade  
# Week 3: Remove exclusion from prod clusters + manual upgrade
```

## Monitoring & Validation

**After each cluster upgrade:**
```bash
# Verify versions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Check cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed

# Validate workloads
kubectl get deployments -A
kubectl get statefulsets -A
```

**Key metrics to monitor:**
- Control plane API latency
- Pod restart counts
- Application error rates
- Resource utilization

## Rollback Plan

**If issues discovered:**

1. **During dev:** Stop rollout, investigate, fix issues
2. **During staging:** Pause prod rollout, assess blast radius
3. **During prod:** Contact GKE support for urgent control plane rollback

**Node pool rollback (if needed):**
```bash
# Create rollback node pool at 1.32
gcloud container node-pools create POOL_NAME-rollback-132 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.XXXX \
  --num-nodes NUM_NODES

# Cordon upgraded pool and migrate workloads
kubectl cordon -l cloud.google.com/gke-nodepool=POOL_NAME
```

## Communication Plan

**Week before each phase:**
- [ ] Notify stakeholders of upcoming upgrade window
- [ ] Confirm on-call coverage
- [ ] Review rollback procedures

**During upgrade:**
- [ ] Real-time updates in incident channel
- [ ] Health checks every 30 minutes post-upgrade

**Post-upgrade:**
- [ ] Upgrade completion notification
- [ ] Any issues or lessons learned documented

## Success Criteria

✅ **Phase completion criteria:**
- All clusters in phase at target version (1.33)
- All pods Running or Completed
- Application health checks passing
- No degradation in key metrics
- 24+ hour soak period before next phase

This strategy balances speed with safety, giving you proper validation gates while completing the full fleet upgrade in 3 weeks.