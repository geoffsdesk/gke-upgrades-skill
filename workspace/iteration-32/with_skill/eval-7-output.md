# GKE Multi-Environment Rollout Strategy
**12 clusters across 3 environments: 1.32 → 1.33**

## Strategy Overview

**Recommended approach:** Use GKE rollout sequencing with environment-based progression. All clusters on Regular channel ensures consistent version availability and enables rollout sequencing.

**Progressive rollout sequence:**
1. **Dev clusters** (4 clusters) → validate → soak 2 days
2. **Staging clusters** (4 clusters) → validate → soak 3 days  
3. **Production clusters** (4 clusters) → validate → complete

**Auto-upgrade control:** Use "no minor upgrades" maintenance exclusion to prevent automatic 1.32→1.33 upgrades, then manually trigger upgrades in controlled sequence.

## Fleet Configuration for Rollout Sequencing

Set up fleet-based rollout sequencing to ensure proper environment progression:

```bash
# Configure dev fleet (goes first)
gcloud container fleet clusterupgrade update \
    --project=PROJECT_ID \
    --default-upgrade-soaking=2d

# Configure staging fleet (waits for dev)
gcloud container fleet clusterupgrade update \
    --project=PROJECT_ID \
    --upstream-fleet=DEV_PROJECT_ID \
    --default-upgrade-soaking=3d

# Configure prod fleet (waits for staging)  
gcloud container fleet clusterupgrade update \
    --project=PROJECT_ID \
    --upstream-fleet=STAGING_PROJECT_ID \
    --default-upgrade-soaking=1d
```

## Pre-Rollout: Block Auto-Upgrades

Apply "no minor upgrades" exclusion to all 12 clusters to prevent automatic 1.32→1.33 upgrades:

```bash
# Apply to all clusters
for CLUSTER in dev-cluster-{1..4} staging-cluster-{1..4} prod-cluster-{1..4}; do
  gcloud container clusters update $CLUSTER \
    --zone ZONE \
    --add-maintenance-exclusion-name "controlled-upgrade" \
    --add-maintenance-exclusion-scope no_minor_upgrades \
    --add-maintenance-exclusion-until-end-of-support
done
```

## Phase 1: Dev Environment (Week 1)

**Clusters:** dev-cluster-1, dev-cluster-2, dev-cluster-3, dev-cluster-4

### Day 1: Control Plane Upgrades
```bash
# Upgrade all dev control planes
for CLUSTER in dev-cluster-{1..4}; do
  echo "Upgrading control plane: $CLUSTER"
  gcloud container clusters upgrade $CLUSTER \
    --zone ZONE \
    --master \
    --cluster-version 1.33.0-gke.PATCH
    
  # Wait for completion before next cluster
  sleep 1800  # 30 min between CP upgrades
done
```

### Day 2: Node Pool Upgrades
```bash
# Upgrade node pools (can run in parallel across clusters)
for CLUSTER in dev-cluster-{1..4}; do
  # Get node pool names
  POOLS=$(gcloud container node-pools list --cluster $CLUSTER --zone ZONE --format="value(name)")
  
  for POOL in $POOLS; do
    echo "Upgrading node pool: $CLUSTER/$POOL"
    gcloud container node-pools upgrade $POOL \
      --cluster $CLUSTER \
      --zone ZONE \
      --cluster-version 1.33.0-gke.PATCH &
  done
done

# Monitor all upgrades
watch 'kubectl get nodes -o wide --context=dev-cluster-1 | head -5; echo "---"; kubectl get nodes -o wide --context=dev-cluster-2 | head -5'
```

### Dev Validation Checklist
```
Dev Environment Validation (Days 3-4)
- [ ] All 4 dev clusters at 1.33.0-gke.PATCH
- [ ] All nodes Ready across all clusters
- [ ] Application smoke tests passing
- [ ] CI/CD pipelines functional
- [ ] No performance regressions in dev workloads
- [ ] Monitoring and logging operational
- [ ] Security scans passing on new version
```

## Phase 2: Staging Environment (Week 2)

**Trigger condition:** Dev validation complete + 2-day soak period

**Clusters:** staging-cluster-1, staging-cluster-2, staging-cluster-3, staging-cluster-4

### Control Plane → Node Pool Sequence
```bash
# Day 1: Control planes
for CLUSTER in staging-cluster-{1..4}; do
  gcloud container clusters upgrade $CLUSTER \
    --zone ZONE \
    --master \
    --cluster-version 1.33.0-gke.PATCH
  sleep 1800
done

# Day 2: Node pools  
for CLUSTER in staging-cluster-{1..4}; do
  POOLS=$(gcloud container node-pools list --cluster $CLUSTER --zone ZONE --format="value(name)")
  for POOL in $POOLS; do
    gcloud container node-pools upgrade $POOL \
      --cluster $CLUSTER \
      --zone ZONE \
      --cluster-version 1.33.0-gke.PATCH &
  done
done
```

### Staging Validation Checklist
```
Staging Environment Validation (Days 3-5)
- [ ] All 4 staging clusters at 1.33.0-gke.PATCH
- [ ] End-to-end testing complete
- [ ] Load testing at staging scale
- [ ] Database migration scripts tested
- [ ] Third-party integrations validated
- [ ] Performance benchmarks within acceptable range
- [ ] Disaster recovery procedures tested
```

## Phase 3: Production Environment (Week 3)

**Trigger condition:** Staging validation complete + 3-day soak period

**Clusters:** prod-cluster-1, prod-cluster-2, prod-cluster-3, prod-cluster-4

### Production-Safe Rollout
```bash
# Canary production cluster first
echo "=== CANARY: prod-cluster-1 ==="
gcloud container clusters upgrade prod-cluster-1 \
  --zone ZONE \
  --master \
  --cluster-version 1.33.0-gke.PATCH

# Wait and validate before proceeding
read -p "Validate prod-cluster-1 control plane. Continue? (y/n): " confirm
[[ $confirm == "y" ]] || exit 1

# Node pool upgrade with conservative settings
POOLS=$(gcloud container node-pools list --cluster prod-cluster-1 --zone ZONE --format="value(name)")
for POOL in $POOLS; do
  gcloud container node-pools update $POOL \
    --cluster prod-cluster-1 \
    --zone ZONE \
    --max-surge-upgrade 1 \
    --max-unavailable-upgrade 0
    
  gcloud container node-pools upgrade $POOL \
    --cluster prod-cluster-1 \
    --zone ZONE \
    --cluster-version 1.33.0-gke.PATCH
done

# 24-hour soak on canary before remaining prod clusters
echo "=== SOAK PERIOD: 24 hours on prod-cluster-1 ==="
```

### Remaining Production Clusters
After 24-hour canary validation:

```bash
# Remaining 3 production clusters
for CLUSTER in prod-cluster-{2..4}; do
  echo "=== Upgrading: $CLUSTER ==="
  
  # Control plane
  gcloud container clusters upgrade $CLUSTER \
    --zone ZONE \
    --master \
    --cluster-version 1.33.0-gke.PATCH
  
  # Node pools
  POOLS=$(gcloud container node-pools list --cluster $CLUSTER --zone ZONE --format="value(name)")
  for POOL in $POOLS; do
    gcloud container node-pools upgrade $POOL \
      --cluster $CLUSTER \
      --zone ZONE \
      --cluster-version 1.33.0-gke.PATCH &
  done
  
  # Stagger cluster upgrades by 4 hours
  sleep 14400
done
```

## Validation Framework

### Automated Health Checks
```bash
#!/bin/bash
# health-check.sh - Run after each phase

CLUSTERS=("$@")

for CLUSTER in "${CLUSTERS[@]}"; do
  echo "=== Health check: $CLUSTER ==="
  
  # Cluster version
  VERSION=$(gcloud container clusters describe $CLUSTER --zone ZONE --format="value(currentMasterVersion)")
  echo "Control plane: $VERSION"
  
  # Node readiness
  READY_NODES=$(kubectl get nodes --context=$CLUSTER --no-headers | grep " Ready " | wc -l)
  TOTAL_NODES=$(kubectl get nodes --context=$CLUSTER --no-headers | wc -l)
  echo "Nodes ready: $READY_NODES/$TOTAL_NODES"
  
  # Pod health
  UNHEALTHY_PODS=$(kubectl get pods -A --context=$CLUSTER --field-selector=status.phase!=Running,status.phase!=Succeeded --no-headers | wc -l)
  echo "Unhealthy pods: $UNHEALTHY_PODS"
  
  # System components
  SYSTEM_ISSUES=$(kubectl get pods -n kube-system --context=$CLUSTER | grep -v Running | grep -v Completed | wc -l)
  echo "System pod issues: $SYSTEM_ISSUES"
  
  echo ""
done
```

### Key Metrics to Monitor
- **API server latency** (p95 < 1s)
- **Node ready percentage** (>99%)
- **Pod restart rate** (baseline comparison)
- **Application error rates** (< 0.1% increase)
- **Resource utilization** (CPU/memory within normal ranges)

## Rollback Plan

### If Issues Found in Dev/Staging
- **Control plane:** Contact GKE support for rollback (not customer-initiated)
- **Node pools:** Create new pools at 1.32, migrate workloads, delete upgraded pools

### If Issues Found in Production Canary
```bash
# Create rollback node pool
gcloud container node-pools create emergency-rollback \
  --cluster prod-cluster-1 \
  --zone ZONE \
  --cluster-version 1.32.0-gke.PREVIOUS_PATCH \
  --num-nodes 3

# Cordon upgraded nodes
kubectl cordon -l cloud.google.com/gke-nodepool=UPGRADED_POOL

# Drain critical workloads to rollback pool
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --grace-period=300
```

## Timeline Summary

| Week | Phase | Activities | Validation Period |
|------|-------|------------|------------------|
| **Week 1** | Dev | CP upgrade (Day 1), Node pools (Day 2) | Days 3-4 (2 days) |
| **Week 2** | Staging | CP upgrade (Day 1), Node pools (Day 2) | Days 3-5 (3 days) |
| **Week 3** | Production | Canary (Days 1-2), 24h soak, Remaining clusters | Ongoing monitoring |

**Total duration:** ~3 weeks with validation gates
**Risk mitigation:** Progressive rollout, canary validation, automated health checks
**Rollback capability:** Available at each phase before proceeding to next environment

This strategy balances upgrade velocity with risk management, using GKE's rollout sequencing to ensure proper environment progression while maintaining operational safety through validation gates and rollback procedures.