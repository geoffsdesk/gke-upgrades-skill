# GKE Multi-Environment Upgrade Rollout Strategy

## Overview
- **Scope**: 12 Standard clusters across 3 environments (4 clusters each)
- **Current version**: 1.32.x → **Target version**: 1.33.x
- **Channel**: Regular (all environments)
- **Upgrade type**: Minor version upgrade

## Rollout Strategy

### Option 1: Sequential Environment Rollout (Recommended)

Since all environments are on the same Regular channel, you'll need to use maintenance exclusions + manual upgrades to maintain proper sequencing. Here's the structured approach:

#### Phase 1: Preparation (Week 1)
```bash
# Apply "no minor or node upgrades" exclusions to ALL clusters
for env in dev staging prod; do
  for i in {1..4}; do
    gcloud container clusters update ${env}-cluster-${i} \
      --zone us-central1-a \
      --add-maintenance-exclusion-name "controlled-upgrade-exclusion" \
      --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
      --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
      --add-maintenance-exclusion-until-end-of-support
  done
done
```

#### Phase 2: Dev Environment (Week 2)
**Timeline**: Monday-Wednesday, with 24h soak between clusters

1. **Dev-Cluster-1** (Monday)
   ```bash
   # Remove exclusion from dev-cluster-1
   gcloud container clusters update dev-cluster-1 \
     --zone us-central1-a \
     --remove-maintenance-exclusion-name "controlled-upgrade-exclusion"
   
   # Manual upgrade to 1.33 (or wait for auto-upgrade)
   gcloud container clusters upgrade dev-cluster-1 \
     --zone us-central1-a \
     --master \
     --cluster-version 1.33.x-gke.latest
   ```

2. **Dev-Cluster-2** (Tuesday, after 24h soak)
3. **Dev-Cluster-3** (Wednesday)
4. **Dev-Cluster-4** (Thursday)

**Validation**: Run smoke tests, validate application functionality

#### Phase 3: Staging Environment (Week 3)
**Timeline**: Monday-Thursday, with 24h soak between clusters

Same process as dev, but with additional validation:
- Load testing
- Integration test suites
- Performance benchmarks

#### Phase 4: Production Environment (Week 4)
**Timeline**: During maintenance windows, 48h soak between clusters

Production clusters upgrade during off-peak hours with extended monitoring.

### Phase-by-Phase Commands

#### Development Phase
```bash
# Configure maintenance windows for dev clusters (example: weekday mornings)
for i in {1..4}; do
  gcloud container clusters update dev-cluster-${i} \
    --zone us-central1-a \
    --maintenance-window-start "2024-MM-DDTII:00:00Z" \
    --maintenance-window-end "2024-MM-DDTII:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH"
done

# Remove exclusion and upgrade (repeat for each dev cluster)
gcloud container clusters update dev-cluster-1 \
  --zone us-central1-a \
  --remove-maintenance-exclusion-name "controlled-upgrade-exclusion"

# Manual control plane upgrade
gcloud container clusters upgrade dev-cluster-1 \
  --zone us-central1-a \
  --master \
  --cluster-version 1.33.x-gke.latest

# Node pool upgrade (configure surge settings first)
for pool in $(gcloud container node-pools list --cluster dev-cluster-1 --zone us-central1-a --format="value(name)"); do
  gcloud container node-pools update ${pool} \
    --cluster dev-cluster-1 \
    --zone us-central1-a \
    --max-surge-upgrade 1 \
    --max-unavailable-upgrade 0
  
  gcloud container node-pools upgrade ${pool} \
    --cluster dev-cluster-1 \
    --zone us-central1-a \
    --cluster-version 1.33.x-gke.latest
done
```

## Alternative: Channel-Based Strategy (Simpler but Less Control)

If you're open to changing your channel strategy, consider:

```bash
# Move environments to different channels for natural sequencing
# Dev → Rapid, Staging → Regular, Prod → Stable
gcloud container clusters update dev-cluster-1 \
  --zone us-central1-a \
  --release-channel rapid

gcloud container clusters update prod-cluster-1 \
  --zone us-central1-a \
  --release-channel stable
```

This provides automatic sequencing but less precise timing control.

## Pre-Upgrade Checklist (Apply to Each Cluster)

```markdown
- [ ] Cluster: ___ | Mode: Standard | Channel: Regular
- [ ] Current version: 1.32.x | Target version: 1.33.x

Compatibility
- [ ] 1.33 available in Regular channel: `gcloud container get-server-config --zone ZONE --format="yaml(channels.regular)"`
- [ ] No deprecated API usage (check GKE deprecation insights dashboard)
- [ ] GKE release notes reviewed for 1.32→1.33 breaking changes
- [ ] Third-party operators tested against 1.33

Workload Readiness  
- [ ] PDBs configured appropriately (not overly restrictive)
- [ ] No bare pods in cluster
- [ ] Adequate terminationGracePeriodSeconds set
- [ ] Resource requests/limits on all containers

Infrastructure (Standard clusters)
- [ ] Node pool surge strategy: maxSurge=1, maxUnavailable=0 (default)
- [ ] Sufficient compute quota for surge nodes
- [ ] Maintenance windows configured for off-peak hours
- [ ] "No minor or node upgrades" exclusion applied during controlled rollout

Ops Readiness
- [ ] Monitoring active, baseline metrics captured
- [ ] Rollback plan documented
- [ ] Stakeholders notified of upgrade windows
```

## Monitoring & Validation

### During Each Cluster Upgrade
```bash
# Monitor upgrade progress
watch 'kubectl get nodes -o wide'

# Check for stuck pods
kubectl get pods -A | grep -E "Terminating|Pending|Error"

# Verify cluster health
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Environment-Level Validation
- **Dev**: Automated smoke tests, developer validation
- **Staging**: Full integration tests, load testing, performance validation  
- **Prod**: Health checks, real traffic validation, rollback readiness

## Rollback Strategy

If issues are discovered:

1. **Control plane**: Contact GKE support for minor version downgrades
2. **Node pools**: Create new pools at 1.32, migrate workloads, delete 1.33 pools
3. **Pause rollout**: Apply exclusions to remaining clusters immediately

## Timeline Summary

| Week | Phase | Clusters | Validation |
|------|-------|----------|------------|
| 1 | Prep | All 12 | Apply exclusions, test readiness |
| 2 | Dev | 4 clusters | Smoke tests, 24h soak |
| 3 | Staging | 4 clusters | Integration tests, 24h soak |  
| 4 | Prod | 4 clusters | Production validation, 48h soak |

**Total duration**: 4 weeks with built-in validation gates

This strategy gives you controlled sequencing while working within the same release channel. The key is using maintenance exclusions to prevent auto-upgrades until you're ready to proceed with each phase.