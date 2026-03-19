# GKE Upgrade Rollout Strategy: 12 Clusters → v1.30

## Environment Overview
- **Dev (4 clusters)**: Rapid channel, currently 1.28 → 1.30
- **Staging (4 clusters)**: Regular channel, currently 1.28 → 1.30  
- **Prod (4 clusters)**: Stable channel, currently 1.28 → 1.30
- **Cluster mode**: Standard (all environments)
- **Upgrade path**: Sequential minors (1.28 → 1.29 → 1.30) — safer for compatibility validation

## Rollout Sequence & Timeline

### Phase 1: Dev Environment (Week 1)
**Target**: All dev clusters on 1.29, begin 1.30 rollout

```
Dev-1 → Dev-2 → Dev-3 → Dev-4
├─ 1.28→1.29 (Mon-Tue)
├─ Soak 24h + validation
└─ 1.29→1.30 (Thu-Fri)
```

- **Soak time**: 24 hours between clusters
- **Validation gate**: Application health checks, integration tests
- **Rapid channel advantage**: 1.30 likely available immediately

### Phase 2: Staging Environment (Week 2-3)
**Target**: Staging follows dev with extended soak times

```
Staging-1 → Staging-2 → Staging-3 → Staging-4
├─ 1.28→1.29 (after dev validation complete)
├─ Soak 48h + full regression testing
└─ 1.29→1.30 (once available in Regular channel)
```

- **Soak time**: 48 hours between clusters
- **Validation gate**: Full regression suite, performance benchmarks
- **Version availability**: Wait for 1.30 in Regular channel (typically 2-4 weeks after Rapid)

### Phase 3: Production Environment (Week 4-6)
**Target**: Production upgrades during planned maintenance windows

```
Prod-1 → Prod-2 → Prod-3 → Prod-4
├─ 1.28→1.29 (weekend maintenance window)
├─ Soak 1 week + business validation
└─ 1.29→1.30 (once available in Stable channel)
```

- **Soak time**: 1 week between clusters
- **Validation gate**: Business acceptance, traffic validation
- **Version availability**: Wait for 1.30 in Stable channel (typically 4-6 weeks after Regular)

## Version Availability Timeline

| Environment | Channel | 1.29 Available | 1.30 Available (estimated) |
|-------------|---------|---------------|---------------------------|
| Dev | Rapid | Now | Likely available now |
| Staging | Regular | Now | 2-4 weeks after Rapid |
| Production | Stable | Now | 4-6 weeks after Regular |

Check current availability:
```bash
gcloud container get-server-config --zone YOUR_ZONE --format="yaml(channels)"
```

## Maintenance Windows & Exclusions

### Recommended Configuration

**All environments:**
```bash
# Set maintenance windows (example for weekend upgrades)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start 2024-01-13T02:00:00Z \
  --maintenance-window-end 2024-01-13T06:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Production clusters** (maximum control):
```bash
# Apply "no minor or node upgrades" exclusion
# Allows security patches but blocks disruptive changes
gcloud container clusters update PROD_CLUSTER \
  --zone ZONE \
  --add-maintenance-exclusion-name "controlled-upgrades" \
  --add-maintenance-exclusion-start-time 2024-01-01T00:00:00Z \
  --add-maintenance-exclusion-end-time 2024-12-31T23:59:59Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

## Node Pool Upgrade Strategy

### Standard Configuration (All Clusters)
```bash
# Configure surge settings per workload type
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

### Pool-Specific Tuning
- **Stateless app pools**: `maxSurge=3, maxUnavailable=0` (faster)
- **Database/stateful pools**: `maxSurge=1, maxUnavailable=0` (conservative)  
- **Large pools (50+ nodes)**: `maxSurge=5, maxUnavailable=0` (parallel efficiency)

## Rollout Sequencing Setup

Configure GKE rollout sequencing to automate the environment progression:

```bash
# Create rollout sequence (requires fleet membership)
gcloud container fleet create my-fleet

# Add clusters to fleet
for cluster in dev-1 dev-2 staging-1 prod-1; do
  gcloud container hub memberships register $cluster \
    --gke-cluster=zones/ZONE/clusters/$cluster
done

# Configure rollout sequence with soak times
# Dev → Staging (48h soak) → Prod (1 week soak)
```

## Pre-Upgrade Validation Checklist

Run this checklist for EACH cluster before upgrading:

```markdown
**Cluster: ___ | Environment: ___ | Current: 1.28 | Target: 1.29/1.30**

Compatibility
- [ ] Target version available in cluster's release channel
- [ ] Deprecated API scan clean (check GKE deprecation insights)
- [ ] Release notes reviewed (1.28→1.29, 1.29→1.30)
- [ ] Third-party operators tested against target version

Workload Readiness  
- [ ] PDBs configured appropriately (not blocking all disruptions)
- [ ] No bare pods present
- [ ] StatefulSet backups completed
- [ ] Resource requests/limits set on all containers

Infrastructure
- [ ] Surge settings configured per node pool
- [ ] Sufficient compute quota for surge capacity
- [ ] Maintenance window configured for off-peak hours
- [ ] Monitoring baseline captured
```

## Upgrade Commands

### Control Plane Upgrade
```bash
# Upgrade control plane first (required order)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# Verify completion (~10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Node Pool Upgrade
```bash
# Upgrade each node pool
gcloud container node-pools upgrade POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION

# Monitor progress
watch 'kubectl get nodes -o wide'
```

## Risk Mitigation

### Break Glass Scenarios
1. **Critical production issue during upgrade**
   - Apply "no upgrades" maintenance exclusion (30 days max)
   - Pause rollout, investigate issue
   
2. **Version compatibility problem discovered**
   - Stop rollout at current environment
   - Create new node pool at previous version for rollback
   
3. **Capacity shortage during surge**
   - Reduce maxSurge temporarily
   - Scale down non-critical workloads

### Validation Gates
- **Dev → Staging**: Integration tests pass, no error rate increase
- **Staging → Prod**: Full regression suite, performance benchmarks stable  
- **Between prod clusters**: Business validation, 1 week soak minimum

## Timeline Summary

```
Week 1: Dev clusters (1.28→1.29→1.30)
Week 2-3: Staging clusters (wait for Regular channel)
Week 4-6: Production clusters (wait for Stable channel)
Total duration: ~6 weeks for complete rollout
```

This conservative timeline ensures each environment validates the upgrade before the next begins, with channel availability naturally gating the progression.