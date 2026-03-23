# GKE Multi-Environment Upgrade Rollout Strategy

## Environment Overview
- **12 Standard clusters** across 3 environments (4 clusters each)
- **Current version:** 1.32.x → **Target version:** 1.33.x
- **Release channel:** Regular (all environments)
- **Upgrade type:** Minor version upgrade

## Recommended Rollout Strategy

### Option 1: Maintenance Windows with Manual Control (Recommended)

Since all environments are on the same Regular channel, **rollout sequencing cannot orchestrate them automatically**. Instead, use maintenance exclusions + manual upgrades for controlled sequencing.

#### Configuration per Environment

```bash
# Apply "no minor or node upgrades" exclusion to ALL clusters
# This blocks auto-upgrades while allowing CP security patches

# Dev clusters (4 clusters)
for cluster in dev-cluster-{1..4}; do
  gcloud container clusters update $cluster \
    --zone ZONE \
    --add-maintenance-exclusion-name "manual-minor-upgrade-control" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
done

# Staging clusters (4 clusters) 
for cluster in staging-cluster-{1..4}; do
  gcloud container clusters update $cluster \
    --zone ZONE \
    --add-maintenance-exclusion-name "manual-minor-upgrade-control" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
done

# Production clusters (4 clusters)
for cluster in prod-cluster-{1..4}; do
  gcloud container clusters update $cluster \
    --zone ZONE \
    --add-maintenance-exclusion-name "manual-minor-upgrade-control" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
done
```

#### Rollout Timeline

**Week 1: Dev Environment**
- Upgrade dev clusters 1-2 on Monday
- Validate for 24-48h
- Upgrade dev clusters 3-4 on Wednesday
- Full validation through Friday

**Week 2: Staging Environment** 
- Upgrade staging clusters 1-2 on Monday
- Run full staging test suite
- Upgrade staging clusters 3-4 on Wednesday
- Performance and integration testing

**Week 3: Production Environment**
- Upgrade prod clusters 1-2 on Monday (off-peak)
- Monitor for 48h
- Upgrade prod clusters 3-4 on Wednesday (off-peak)
- Full production validation

### Option 2: Release Channel Strategy (Alternative)

Move environments to different channels for natural progression:

```bash
# Move dev to Rapid channel (gets 1.33 first)
for cluster in dev-cluster-{1..4}; do
  gcloud container clusters update $cluster \
    --zone ZONE \
    --release-channel rapid
done

# Keep staging on Regular channel 

# Move prod to Stable channel (gets 1.33 last)
for cluster in prod-cluster-{1..4}; do
  gcloud container clusters update $cluster \
    --zone ZONE \
    --release-channel stable
done
```

**Pros:** Automatic progression as versions promote through channels
**Cons:** Lose precise timing control, environments drift over time

## Detailed Upgrade Runbook

### Pre-upgrade Setup (All Clusters)

```bash
# Configure maintenance windows (example for production - off-peak)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-27T02:00:00Z" \
  --maintenance-window-duration "4h" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"

# Set conservative disruption intervals
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-minor-version-disruption-interval=7d \
  --maintenance-patch-version-disruption-interval=24h
```

### Upgrade Execution (Per Cluster)

**Control Plane First:**
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.33.x-gke.PATCH

# Verify CP upgrade (wait ~10-15 min)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

**Node Pools Second:**
```bash
# Configure surge settings per pool type
# Standard workload pools:
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# For larger pools (100+ nodes), use percentage:
# maxSurge = 5% of pool size, minimum 1

# Execute node pool upgrade
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.33.x-gke.PATCH

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

### Validation Checklist (Per Environment)

```markdown
## Environment Validation: [DEV/STAGING/PROD]

### Cluster Health
- [ ] All control planes at 1.33.x: `gcloud container clusters list --format="table(name,currentMasterVersion)"`
- [ ] All node pools at 1.33.x: `gcloud container node-pools list --cluster CLUSTER --format="table(name,version)"`
- [ ] All nodes Ready: `kubectl get nodes`
- [ ] System pods healthy: `kubectl get pods -n kube-system`

### Workload Health  
- [ ] All deployments at desired replica count
- [ ] No CrashLoopBackOff or Pending pods
- [ ] Load balancers responding
- [ ] Application health checks passing
- [ ] Database connections stable (if applicable)

### Environment-Specific Tests
**Dev:** Unit and integration tests pass
**Staging:** Full regression test suite + performance benchmarks  
**Production:** Smoke tests + real traffic validation

### Soak Period
- [ ] 24h soak completed for dev
- [ ] 48h soak completed for staging  
- [ ] 72h soak completed for production
```

## Risk Mitigation

### Pre-upgrade Preparation
- **Deprecated API scan:** Run across all clusters before starting
- **Backup validation:** Ensure all stateful workloads have recent backups
- **PDB audit:** Check that PDBs aren't overly restrictive
- **Resource capacity:** Verify surge quota available

### Rollback Plan
```bash
# If issues arise, create new node pools at 1.32.x
gcloud container node-pools create nodepool-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.PREVIOUS_PATCH \
  --num-nodes 3

# Migrate workloads, then remove upgraded pool
```

### Go/No-Go Criteria
- **Go:** All validation checks pass, no critical issues in previous environment
- **No-Go:** Any CrashLoopBackOff pods, failed health checks, or performance regression >10%

## Timeline Summary

| Week | Environment | Action | Validation |
|------|------------|--------|------------|
| 1 | Dev | Upgrade all 4 clusters | 48h soak + tests |
| 2 | Staging | Upgrade all 4 clusters | 48h soak + regression tests |  
| 3 | Production | Upgrade all 4 clusters | 72h soak + monitoring |

**Total timeline:** 3 weeks with built-in validation periods

This strategy prioritizes safety and validation over speed, which is appropriate for a minor version upgrade across production workloads.