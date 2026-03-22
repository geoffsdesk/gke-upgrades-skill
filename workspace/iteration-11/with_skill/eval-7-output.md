I notice you mentioned upgrading from 1.32 to 1.32 — I assume you meant upgrading **to** a newer version like 1.33 or 1.34. I'll create a strategy assuming you're targeting the latest available version in the Regular channel. Please confirm your target version and I'll adjust accordingly.

# Multi-Environment GKE Upgrade Rollout Strategy

## Environment Overview
- **12 clusters total:** 4 dev + 4 staging + 4 prod
- **Current version:** 1.32.x
- **Target version:** Latest Regular channel (please confirm specific version)
- **Channel:** All on Regular (good — enables rollout sequencing)
- **Mode:** All Standard clusters

## Recommended Rollout Sequence

### Phase 1: Development Environment
**Timeline:** Week 1
**Clusters:** dev-cluster-1, dev-cluster-2, dev-cluster-3, dev-cluster-4

```bash
# Configure maintenance windows (example: Saturday 2-6 AM)
for cluster in dev-cluster-1 dev-cluster-2 dev-cluster-3 dev-cluster-4; do
  gcloud container clusters update $cluster \
    --zone ZONE \
    --maintenance-window-start "2024-MM-DDTHH:MM:SSZ" \
    --maintenance-window-end "2024-MM-DDTHH:MM:SSZ" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
done
```

**Approach:** Parallel upgrades within dev environment
- All 4 dev clusters can upgrade simultaneously
- Use auto-upgrades with maintenance windows for predictable timing
- 48-hour soak period before proceeding to staging

### Phase 2: Staging Environment  
**Timeline:** Week 2 (after dev validation)
**Clusters:** staging-cluster-1, staging-cluster-2, staging-cluster-3, staging-cluster-4

```bash
# Stagger staging clusters by 12 hours for controlled rollout
# Cluster 1 & 2: Saturday 2 AM
# Cluster 3 & 4: Saturday 2 PM
```

**Approach:** Paired rollout (2 clusters, then remaining 2)
- 72-hour soak period before production
- Validate critical user journeys and integration tests

### Phase 3: Production Environment
**Timeline:** Week 3 (after staging validation)  
**Clusters:** prod-cluster-1, prod-cluster-2, prod-cluster-3, prod-cluster-4

**Approach:** Sequential with 24-hour soak between pairs
- **Wave 1:** prod-cluster-1, prod-cluster-2 (Saturday 2 AM)
- **Wave 2:** prod-cluster-3, prod-cluster-4 (Sunday 2 AM, after 24h soak)

## GKE Rollout Sequencing Configuration

Since all clusters are on the same channel (Regular), you can use GKE's native rollout sequencing:

```bash
# Create rollout sequence
gcloud container clusters update dev-cluster-1 \
  --zone ZONE \
  --enable-rollout-sequencing \
  --rollout-sequence-name "multi-env-upgrade" \
  --rollout-sequence-stage "dev" \
  --rollout-sequence-soak-duration "48h"

# Add other clusters to sequence
gcloud container clusters update staging-cluster-1 \
  --zone ZONE \
  --rollout-sequence-name "multi-env-upgrade" \
  --rollout-sequence-stage "staging" \
  --rollout-sequence-soak-duration "72h"

gcloud container clusters update prod-cluster-1 \
  --zone ZONE \
  --rollout-sequence-name "multi-env-upgrade" \
  --rollout-sequence-stage "prod" \
  --rollout-sequence-soak-duration "24h"
```

## Alternative: Manual Maintenance Windows (Simpler)

If rollout sequencing is too complex, use staggered maintenance windows:

```bash
# Dev: Week 1, Saturday 2-6 AM
# Staging: Week 2, Saturday 2-6 AM  
# Prod Wave 1: Week 3, Saturday 2-6 AM
# Prod Wave 2: Week 3, Sunday 2-6 AM
```

## Node Pool Upgrade Strategy Per Environment

### Development Clusters
```bash
# Aggressive settings for faster completion
gcloud container node-pools update default-pool \
  --cluster dev-cluster-X \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

### Staging Clusters  
```bash
# Balanced approach
gcloud container node-pools update default-pool \
  --cluster staging-cluster-X \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

### Production Clusters
```bash
# Conservative, stateful-friendly settings
gcloud container node-pools update default-pool \
  --cluster prod-cluster-X \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

## Validation Gates

### After Dev (48h soak)
- [ ] All 4 dev clusters at target version
- [ ] No application errors in dev environment
- [ ] Smoke tests passing
- [ ] Resource utilization normal

### After Staging (72h soak)  
- [ ] All 4 staging clusters at target version
- [ ] End-to-end tests passing
- [ ] Performance benchmarks within baseline
- [ ] Integration tests with external services passing

### After Prod Wave 1 (24h soak)
- [ ] First 2 prod clusters healthy
- [ ] Production traffic handling normally  
- [ ] SLOs maintained
- [ ] No customer-facing issues

## Risk Mitigation

### Maintenance Exclusions (Emergency Brake)
```bash
# Apply "no upgrades" exclusion to halt auto-upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "emergency-hold" \
  --add-maintenance-exclusion-start-time "2024-MM-DDTHH:MM:SSZ" \
  --add-maintenance-exclusion-end-time "2024-MM-DDTHH:MM:SSZ" \
  --add-maintenance-exclusion-scope no_upgrades
```

### Rollback Plan
- Control plane: Contact GKE support for minor version downgrade
- Node pools: Create new pools at previous version, migrate workloads
- Timeline: Budget 4-6 hours for full environment rollback

## Pre-Upgrade Checklist (Apply to All Environments)

```bash
# Check current auto-upgrade targets
for cluster in $(gcloud container clusters list --format="value(name)"); do
  echo "=== $cluster ==="
  gcloud container clusters get-upgrade-info $cluster --zone ZONE
done

# Verify no deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```

## Communication Plan

- **T-7 days:** Stakeholder notification of upgrade schedule
- **T-2 days:** Final go/no-go decision  
- **During upgrade:** Real-time status in shared channel
- **Post-upgrade:** Environment health report

**Questions for you:**
1. What's your specific target version (1.33.x, 1.34.x)?
2. Do any clusters have GPU workloads or special node pool types?
3. Preference for GKE rollout sequencing vs. manual maintenance windows?
4. Any critical business periods we should avoid (maintenance exclusions)?