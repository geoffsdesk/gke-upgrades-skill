# GKE Fleet Upgrade Strategy: Regular Channel 1.32 → 1.33

## Environment Overview
- **12 Standard clusters** across 3 environments (4 clusters each)
- **Current version:** 1.32
- **Target version:** 1.33  
- **Release channel:** Regular (all environments)
- **Upgrade type:** Minor version upgrade

## Recommended Rollout Strategy

Since all environments are on the same release channel (Regular), **rollout sequencing cannot provide automatic ordering**. GKE's rollout sequencing only works when environments use different channels or versions.

### Option A: Channel-Based Strategy (Recommended)

Migrate environments to different channels to guarantee upgrade ordering:

```bash
# Migrate dev clusters to Rapid channel (gets 1.33 first)
for cluster in dev-cluster-1 dev-cluster-2 dev-cluster-3 dev-cluster-4; do
  gcloud container clusters update $cluster \
    --zone us-central1-a \
    --release-channel rapid
done

# Keep staging on Regular channel (gets 1.33 ~1 month after Rapid)
# Staging clusters stay as-is

# Configure prod with "no minor or node upgrades" exclusion
for cluster in prod-cluster-1 prod-cluster-2 prod-cluster-3 prod-cluster-4; do
  gcloud container clusters update $cluster \
    --zone us-central1-a \
    --add-maintenance-exclusion-name "controlled-upgrades" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
done
```

**Rollout sequence:**
1. **Dev (Rapid channel):** Auto-upgrades to 1.33 within ~2 weeks
2. **Staging (Regular channel):** Auto-upgrades to 1.33 ~1 month after dev
3. **Prod (Regular + exclusion):** Manual upgrade after staging validation

### Option B: Maintenance Window Strategy (Alternative)

Keep all on Regular channel but stagger maintenance windows:

```bash
# Dev: Weekend early morning
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Staging: 1 week later
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-13T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Prod: Manual trigger after validation
for cluster in prod-cluster-1 prod-cluster-2 prod-cluster-3 prod-cluster-4; do
  gcloud container clusters update $cluster \
    --zone ZONE \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
done
```

**⚠️ Warning:** Maintenance windows do NOT guarantee ordering across environments. Version 1.33 could become available in different regions at different times, potentially upgrading prod before dev.

## Detailed Rollout Plan

### Phase 1: Pre-upgrade Preparation (Week 1)

```bash
# Check current auto-upgrade targets
for cluster in $(gcloud container clusters list --format="value(name)"); do
  echo "=== $cluster ==="
  gcloud container clusters get-upgrade-info $cluster --region us-central1
done

# Configure maintenance windows for dev (if using Option B)
gcloud container clusters update dev-cluster-1 \
  --zone us-central1-a \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Pre-flight checklist per environment:**
- [ ] Check deprecated API usage across all 12 clusters
- [ ] Verify no "No channel" clusters (legacy config)
- [ ] Confirm PDBs configured for critical workloads
- [ ] Test 1.33 compatibility in dev environment first
- [ ] Review GKE 1.32 → 1.33 release notes for breaking changes

### Phase 2: Dev Environment (Week 2-3)

**Trigger:** Auto-upgrade when 1.33 reaches Regular channel

```bash
# Monitor dev upgrade progress
watch 'gcloud container clusters list --filter="name~dev" --format="table(name,currentMasterVersion,status)"'

# Validate each dev cluster post-upgrade
for cluster in dev-cluster-1 dev-cluster-2 dev-cluster-3 dev-cluster-4; do
  echo "=== Validating $cluster ==="
  kubectl --cluster=$cluster get nodes
  kubectl --cluster=$cluster get pods -A | grep -v Running | grep -v Completed
done
```

**Dev soak period:** 1 week minimum to catch issues

### Phase 3: Staging Environment (Week 4)

```bash
# Staging auto-upgrades after dev validation
# Monitor and validate same as dev

# Critical validation tests for staging
kubectl --cluster=staging-cluster-1 run smoke-test --image=nginx --rm -it --restart=Never -- curl -I http://your-app
```

**Staging soak period:** 3-5 days for production-like validation

### Phase 4: Production Environment (Week 5+)

**Manual trigger after staging validation:**

```bash
# Remove exclusions and trigger manual upgrade
for cluster in prod-cluster-1 prod-cluster-2 prod-cluster-3 prod-cluster-4; do
  echo "=== Upgrading $cluster ==="
  
  # Remove maintenance exclusion
  gcloud container clusters update $cluster \
    --zone us-central1-a \
    --remove-maintenance-exclusion-name "controlled-upgrades"
  
  # Trigger immediate upgrade
  gcloud container clusters upgrade $cluster \
    --zone us-central1-a \
    --master \
    --cluster-version=1.33
  
  # Wait and validate before next cluster
  echo "Waiting 30 minutes before next cluster..."
  sleep 1800
done
```

## Node Pool Strategy (All Environments)

Since these are minor version upgrades with significant control plane changes, use **conservative node pool settings**:

```bash
# Configure surge settings for stateless workloads
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# For stateful/database workloads
gcloud container node-pools update database-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Node upgrade sequence per cluster:**
1. Control plane upgrade first (automatic)
2. Node pools upgrade after CP completes (can be simultaneous across pools)
3. Skip-level node upgrades (1.32 → 1.33 in one jump) to reduce drain cycles

## Monitoring & Rollback

### Health Checks Per Phase
```bash
# Cluster health validation script
#!/bin/bash
for cluster in $CLUSTER_LIST; do
  echo "=== $cluster health check ==="
  
  # Version verification
  gcloud container clusters describe $cluster --zone $ZONE \
    --format="value(currentMasterVersion)"
  
  # Node status
  kubectl --cluster=$cluster get nodes | grep -v Ready && echo "❌ Unhealthy nodes" || echo "✅ All nodes ready"
  
  # Pod status
  kubectl --cluster=$cluster get pods -A | grep -E "CrashLoop|Error|Pending" && echo "❌ Unhealthy pods" || echo "✅ All pods healthy"
  
  # Critical workload check
  kubectl --cluster=$cluster get deployments -A | awk '$3!=$4 {print "❌ " $0}'
done
```

### Emergency Rollback Plan
- **Control plane:** Contact GKE support for 1.33 → 1.32 downgrade (not customer-initiated)
- **Node pools:** Create new pools at 1.32, migrate workloads, delete upgraded pools
- **Exclusions:** Apply "no upgrades" exclusion immediately to stop further auto-upgrades

## Timeline Summary

| Week | Phase | Action | Validation |
|------|--------|--------|------------|
| 1 | Prep | Configure channels/windows | Pre-flight checks |
| 2-3 | Dev | Auto-upgrade to 1.33 | App smoke tests |
| 4 | Staging | Auto-upgrade to 1.33 | Production-like testing |
| 5+ | Prod | Manual upgrade (controlled) | Gradual rollout |

**Total timeline:** 5-6 weeks for complete fleet upgrade with proper validation gates.

This strategy provides deterministic upgrade ordering while maintaining the safety and automation benefits of GKE's managed upgrade lifecycle.