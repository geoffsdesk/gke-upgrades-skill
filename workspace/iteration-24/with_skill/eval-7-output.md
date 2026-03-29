# Multi-Environment GKE Upgrade Rollout Strategy

## Environment Overview
- **12 clusters total:** 4 dev, 4 staging, 4 prod
- **Current version:** 1.32 → **Target version:** 1.33
- **All clusters:** Standard mode, Regular release channel
- **Upgrade type:** Minor version upgrade (sequential CP then nodes)

## Rollout Strategy: Progressive with Validation Gates

### Phase 1: Development Environment (Week 1)
**Clusters:** dev-cluster-1, dev-cluster-2, dev-cluster-3, dev-cluster-4  
**Risk:** Low - development workloads can tolerate disruption

```bash
# Upgrade all dev clusters in parallel (acceptable risk for dev)
for cluster in dev-cluster-1 dev-cluster-2 dev-cluster-3 dev-cluster-4; do
  echo "Upgrading control plane: $cluster"
  gcloud container clusters upgrade $cluster \
    --zone ZONE \
    --master \
    --cluster-version 1.33 &
done
wait

# After all control planes complete, upgrade node pools
# Use higher maxSurge for dev (faster, acceptable disruption)
for cluster in dev-cluster-1 dev-cluster-2 dev-cluster-3 dev-cluster-4; do
  for pool in $(gcloud container node-pools list --cluster $cluster --zone ZONE --format="value(name)"); do
    gcloud container node-pools update $pool \
      --cluster $cluster --zone ZONE \
      --max-surge-upgrade 3 --max-unavailable-upgrade 0
    
    gcloud container node-pools upgrade $pool \
      --cluster $cluster --zone ZONE \
      --cluster-version 1.33 &
  done
done
wait
```

**Validation gate:** All dev clusters healthy, applications functioning, no regressions detected

---

### Phase 2: Staging Environment (Week 2)
**Clusters:** staging-cluster-1, staging-cluster-2, staging-cluster-3, staging-cluster-4  
**Risk:** Medium - production-like workloads, more conservative approach

```bash
# Upgrade staging clusters in pairs with soak time
# Pair 1: staging-cluster-1, staging-cluster-2
for cluster in staging-cluster-1 staging-cluster-2; do
  gcloud container clusters upgrade $cluster \
    --zone ZONE \
    --master \
    --cluster-version 1.33 &
done
wait

# Configure conservative surge settings for staging
for cluster in staging-cluster-1 staging-cluster-2; do
  for pool in $(gcloud container node-pools list --cluster $cluster --zone ZONE --format="value(name)"); do
    gcloud container node-pools update $pool \
      --cluster $cluster --zone ZONE \
      --max-surge-upgrade 2 --max-unavailable-upgrade 0
    
    gcloud container node-pools upgrade $pool \
      --cluster $cluster --zone ZONE \
      --cluster-version 1.33
  done
done

# 48-hour soak period - monitor for issues
# Then proceed with Pair 2
```

**Validation gate:** First staging pair stable for 48 hours before proceeding to remaining staging clusters

---

### Phase 3: Production Environment (Week 3-4)
**Clusters:** prod-cluster-1, prod-cluster-2, prod-cluster-3, prod-cluster-4  
**Risk:** High - mission-critical workloads, maximum caution

```bash
# Production: One cluster at a time with extended validation
# Configure maintenance windows (off-peak hours)
for cluster in prod-cluster-1 prod-cluster-2 prod-cluster-3 prod-cluster-4; do
  gcloud container clusters update $cluster \
    --zone ZONE \
    --maintenance-window-start "2024-01-06T02:00:00Z" \
    --maintenance-window-end "2024-01-06T06:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
done

# Conservative surge settings for production
for cluster in prod-cluster-1 prod-cluster-2 prod-cluster-3 prod-cluster-4; do
  for pool in $(gcloud container node-pools list --cluster $cluster --zone ZONE --format="value(name)"); do
    gcloud container node-pools update $pool \
      --cluster $cluster --zone ZONE \
      --max-surge-upgrade 1 --max-unavailable-upgrade 0
  done
done

# Upgrade one production cluster per weekend
# Weekend 1: prod-cluster-1
# Weekend 2: prod-cluster-2  
# Weekend 3: prod-cluster-3
# Weekend 4: prod-cluster-4
```

**Per-cluster production workflow:**
1. Apply maintenance window (Saturday 2-6 AM)
2. Upgrade control plane
3. Wait 24 hours, validate stability
4. Upgrade node pools
5. 72-hour soak period before next cluster

---

## Maintenance Control Configuration

Since all environments are on the **same channel** (Regular), use maintenance exclusions to control progression:

```bash
# Block auto-upgrades during manual rollout period
for cluster in dev-cluster-1 dev-cluster-2 dev-cluster-3 dev-cluster-4 \
               staging-cluster-1 staging-cluster-2 staging-cluster-3 staging-cluster-4 \
               prod-cluster-1 prod-cluster-2 prod-cluster-3 prod-cluster-4; do
  gcloud container clusters update $cluster \
    --zone ZONE \
    --add-maintenance-exclusion-name "manual-1.33-rollout" \
    --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-02-01T00:00:00Z" \
    --add-maintenance-exclusion-scope no_upgrades
done
```

**Remove exclusions after manual rollout completes** to resume normal auto-upgrade behavior.

---

## Rollback Strategy

**If issues discovered in any phase:**

1. **Control plane:** Contact GKE support for minor version downgrade assistance
2. **Node pools:** Create new pools at 1.32, migrate workloads:
   ```bash
   gcloud container node-pools create rollback-pool \
     --cluster CLUSTER_NAME --zone ZONE \
     --cluster-version 1.32 \
     --num-nodes 3 --machine-type n1-standard-4
   
   # Cordon upgraded pools, migrate workloads to rollback pool
   kubectl cordon -l cloud.google.com/gke-nodepool=UPGRADED_POOL
   ```

3. **Stop further rollout** until issues resolved

---

## Pre-Flight Requirements

### All Environments
- [ ] 1.33 available in Regular channel: `gcloud container get-server-config --zone ZONE`
- [ ] No deprecated API usage: Check GKE deprecation insights dashboard
- [ ] Review [GKE 1.33 release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) for breaking changes
- [ ] PDBs configured but not overly restrictive
- [ ] All operators/controllers compatible with K8s 1.33

### Environment-Specific
- [ ] **Dev:** Acceptable for parallel upgrades, higher maxSurge
- [ ] **Staging:** Production-like validation, 48h soak between batches  
- [ ] **Prod:** Off-peak maintenance windows, conservative surge, weekly cadence

---

## Timeline Summary

| Week | Environment | Activity | Soak Period |
|------|-------------|----------|-------------|
| Week 1 | Development | All 4 clusters (parallel) | 2-3 days validation |
| Week 2 | Staging | 2 clusters → 48h → 2 clusters | 48h between batches |
| Week 3-4 | Production | 1 cluster per weekend | 72h between clusters |

**Total duration:** 4 weeks  
**Alternative:** Use [GKE rollout sequencing](https://cloud.google.com/kubernetes-engine/docs/how-to/rollout-sequencing) to automate this progression with built-in soak periods, but requires fleet configuration.

This strategy balances speed (parallel dev upgrades) with safety (conservative production rollout) while maintaining validation gates between environments.