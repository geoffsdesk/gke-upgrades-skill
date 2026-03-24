# Multi-Environment GKE Upgrade Strategy
**Target:** 12 Standard clusters (4 dev + 4 staging + 4 prod) | Regular channel | 1.32 → 1.33

## Strategy Overview

Since all environments are on the **same release channel** (Regular), we'll use **maintenance window staggering** + **maintenance exclusions** for controlled rollout sequencing. This is simpler than GKE's rollout sequencing feature and gives you manual control over timing.

**Key principle:** Use "no minor or node upgrades" exclusions to block auto-upgrades, then manually trigger upgrades in sequence with soak time between environments.

## Rollout Sequence

### Phase 1: Development (Week 1)
- **Timing:** Monday-Wednesday
- **Approach:** Allow auto-upgrades with maintenance windows
- **Soak period:** 3-4 days before staging

### Phase 2: Staging (Week 1-2) 
- **Timing:** Friday (after dev soak)
- **Approach:** Manual upgrades during maintenance window
- **Soak period:** 1 week before production

### Phase 3: Production (Week 2-3)
- **Timing:** Following Friday (after staging soak)  
- **Approach:** Manual upgrades with maximum control
- **Completion:** Staggered across 2-3 maintenance windows

## Implementation Plan

### Step 1: Configure Maintenance Windows (All Clusters)

Set staggered maintenance windows to control timing and spread load:

```bash
# Development clusters - early week, 2-hour windows
for CLUSTER in dev-cluster-1 dev-cluster-2 dev-cluster-3 dev-cluster-4; do
  gcloud container clusters update $CLUSTER \
    --zone ZONE \
    --maintenance-window-start "2024-01-08T02:00:00Z" \
    --maintenance-window-end "2024-01-08T04:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=MO"
done

# Staging clusters - mid-week, 3-hour windows  
for CLUSTER in staging-cluster-1 staging-cluster-2 staging-cluster-3 staging-cluster-4; do
  gcloud container clusters update $CLUSTER \
    --zone ZONE \
    --maintenance-window-start "2024-01-12T02:00:00Z" \
    --maintenance-window-end "2024-01-12T05:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=FR"
done

# Production clusters - weekend, 4-hour windows with 2-hour spacing
gcloud container clusters update prod-cluster-1 \
  --zone ZONE \
  --maintenance-window-start "2024-01-20T02:00:00Z" \
  --maintenance-window-end "2024-01-20T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

gcloud container clusters update prod-cluster-2 \
  --zone ZONE \
  --maintenance-window-start "2024-01-20T04:00:00Z" \
  --maintenance-window-end "2024-01-20T08:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Continue for prod-cluster-3 and prod-cluster-4...
```

### Step 2: Apply Maintenance Exclusions (Staging & Prod)

Block auto-upgrades on staging and prod while allowing dev to proceed:

```bash
# Staging - block until manual trigger
for CLUSTER in staging-cluster-1 staging-cluster-2 staging-cluster-3 staging-cluster-4; do
  gcloud container clusters update $CLUSTER \
    --zone ZONE \
    --add-maintenance-exclusion-name "hold-for-dev-validation" \
    --add-maintenance-exclusion-start-time "2024-01-08T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-01-15T00:00:00Z" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades
done

# Production - block until manual trigger  
for CLUSTER in prod-cluster-1 prod-cluster-2 prod-cluster-3 prod-cluster-4; do
  gcloud container clusters update $CLUSTER \
    --zone ZONE \
    --add-maintenance-exclusion-name "hold-for-staging-validation" \
    --add-maintenance-exclusion-start-time "2024-01-08T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-01-22T00:00:00Z" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades
done
```

## Execution Timeline

### Week 1: Development Phase

**Monday (Day 1):**
- Dev clusters auto-upgrade to 1.33 during maintenance windows
- Monitor for issues: deprecated APIs, PDB conflicts, workload compatibility

**Tuesday-Thursday (Days 2-4):**  
- **Validation period** - monitor dev environment health
- Check metrics: error rates, latency, throughput
- Validate application functionality
- **Go/No-Go decision** by Thursday EOD

### Week 1: Staging Phase (if dev validation passes)

**Friday (Day 5):**
- Remove staging maintenance exclusions
- **Manual upgrade trigger** during maintenance window:

```bash
# Staging control planes first
for CLUSTER in staging-cluster-1 staging-cluster-2 staging-cluster-3 staging-cluster-4; do
  gcloud container clusters upgrade $CLUSTER \
    --zone ZONE \
    --master \
    --cluster-version 1.33
done

# Then node pools (can run in parallel after CP upgrades complete)
for CLUSTER in staging-cluster-1 staging-cluster-2 staging-cluster-3 staging-cluster-4; do
  for NODE_POOL in $(gcloud container node-pools list --cluster $CLUSTER --zone ZONE --format="value(name)"); do
    gcloud container node-pools upgrade $NODE_POOL \
      --cluster $CLUSTER \
      --zone ZONE \
      --cluster-version 1.33 &
  done
done
```

**Weekend + Week 2 (Days 6-12):**
- **Extended soak period** for staging
- Run integration tests, performance benchmarks
- **Final go/no-go decision** by Friday Week 2

### Week 2-3: Production Phase (if staging validation passes)

**Friday-Saturday (Days 12-13):**
- Remove production maintenance exclusions  
- **Manual upgrade trigger** with maximum control:

```bash
# Staggered production upgrades - 2 clusters per maintenance window

# First batch - Friday 2 AM
gcloud container clusters upgrade prod-cluster-1 --zone ZONE --master --cluster-version 1.33
gcloud container clusters upgrade prod-cluster-2 --zone ZONE --master --cluster-version 1.33

# Node pools after CP completes
gcloud container node-pools upgrade primary-pool --cluster prod-cluster-1 --zone ZONE --cluster-version 1.33
gcloud container node-pools upgrade primary-pool --cluster prod-cluster-2 --zone ZONE --cluster-version 1.33

# Second batch - Saturday 2 AM (next day)  
gcloud container clusters upgrade prod-cluster-3 --zone ZONE --master --cluster-version 1.33
gcloud container clusters upgrade prod-cluster-4 --zone ZONE --master --cluster-version 1.33

# Continue node pools...
```

## Pre-Upgrade Checklist (Per Environment)

```markdown
Environment: _____ | Phase: _____ | Date: _____

Pre-Flight
- [ ] GKE 1.33 available in Regular channel confirmed
- [ ] No deprecated API usage (check GKE insights dashboard)  
- [ ] Release notes reviewed for 1.32 → 1.33 breaking changes
- [ ] Maintenance windows configured and tested
- [ ] Maintenance exclusions applied to downstream environments

Workload Readiness  
- [ ] PDBs reviewed - not overly restrictive
- [ ] No bare pods detected
- [ ] Resource requests set on all containers
- [ ] Integration tests prepared for validation
- [ ] Monitoring baseline captured (error rates, latency)

Operations
- [ ] On-call team notified and available
- [ ] Rollback plan reviewed
- [ ] Communication plan executed (stakeholder notification)
- [ ] Next environment prepared (exclusions ready to lift)
```

## Monitoring & Validation

### Key Metrics to Track
- **Cluster health:** Node readiness, system pod health
- **Application health:** HTTP error rates, response latency (p95/p99)  
- **Infrastructure:** Resource utilization, PDB status
- **Business metrics:** Transaction success rates, user experience

### Validation Commands
```bash
# Cluster upgrade status
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Workload health
kubectl get pods -A | grep -v Running | grep -v Completed
kubectl get pdb -A -o wide

# Application validation  
curl -s https://app.example.com/healthz
# Run integration test suite
```

## Rollback Strategy

**Development/Staging:** If issues found, address in next minor release or create new node pools at 1.32

**Production:** 
- **Control plane:** Contact GKE support for minor version downgrade (requires support ticket)
- **Node pools:** Create new pools at 1.32, migrate workloads, delete upgraded pools
- **Timeline:** 2-4 hours for node pool recreation and workload migration

## Risk Mitigation

1. **Failure isolation:** Staggered timing prevents fleet-wide outage
2. **Extended soak periods:** 3-4 days dev, 1 week staging catches most issues  
3. **Manual control:** No surprises from auto-upgrades during critical periods
4. **Maintenance windows:** Upgrades happen during planned low-traffic periods
5. **Monitoring:** Comprehensive health checks at each phase gate

This strategy balances upgrade velocity (3-week total timeline) with risk management through proper sequencing and validation gates. The use of maintenance exclusions gives you full control over timing while leveraging GKE's auto-upgrade capabilities where appropriate.