# GKE Fleet Rollout Strategy: 1.32 → 1.33

## Executive Summary

**Scope:** 12 Standard GKE clusters across 3 environments (4 clusters each)  
**Current:** 1.32 (Regular channel)  
**Target:** 1.33 (Regular channel)  
**Strategy:** Progressive environment rollout with validation gates

## Environment Topology & Sequencing

```
DEV (4 clusters) → STAGING (4 clusters) → PROD (4 clusters)
     ↓ 48h soak        ↓ 72h soak         ↓ Final validation
```

**Key principle:** All environments on Regular channel enables natural rollout sequencing — 1.33 becomes available uniformly, allowing controlled progression through environments.

## Rollout Timeline

| Phase | Environment | Duration | Validation Gate |
|-------|-------------|----------|-----------------|
| **Phase 1** | DEV (4 clusters) | Week 1 | 48h soak + smoke tests |
| **Phase 2** | STAGING (4 clusters) | Week 2 | 72h soak + full regression |
| **Phase 3** | PROD (4 clusters) | Week 3 | Per-cluster validation |

**Total timeline:** 3 weeks from start to completion

## Per-Environment Strategy

### DEV Environment (Phase 1)
**Objective:** Fast iteration, catch major issues early

**Approach:** Parallel cluster upgrades within environment
- All 4 DEV clusters upgrade simultaneously
- Higher risk tolerance — use auto-upgrades with minimal exclusions
- Focus on compatibility testing (deprecated APIs, workload health)

**Commands:**
```bash
# Remove any maintenance exclusions to allow auto-upgrade
for cluster in dev-cluster-{1..4}; do
  gcloud container clusters update $cluster \
    --zone ZONE \
    --remove-maintenance-exclusion-name "any-existing-exclusions"
done

# Or manually trigger for faster iteration
for cluster in dev-cluster-{1..4}; do
  gcloud container clusters upgrade $cluster \
    --zone ZONE \
    --master \
    --cluster-version 1.33.X-gke.Y &
done
```

**Validation criteria:**
- [ ] All system pods healthy
- [ ] No deprecated API usage blocking minor upgrade
- [ ] Core application smoke tests pass
- [ ] Monitoring/logging pipeline intact

**Go/No-Go for Stage 2:** 48h soak period with zero critical issues

### STAGING Environment (Phase 2)
**Objective:** Production-like validation with full regression testing

**Approach:** Sequential cluster upgrades (2+2 pattern)
- Upgrade 2 clusters, validate, then remaining 2
- Mirrors production safety but allows full regression suite
- Test deployment pipelines and integration points

**Sequence:**
```bash
# Batch 1: staging-cluster-1, staging-cluster-2
# Batch 2: staging-cluster-3, staging-cluster-4 (after 24h validation)
```

**Validation criteria:**
- [ ] Full regression test suite passes
- [ ] End-to-end application flows validated  
- [ ] CI/CD pipelines deploy successfully
- [ ] Performance benchmarks within 5% of baseline
- [ ] Cross-cluster communication (if applicable) works

**Go/No-Go for Stage 3:** 72h soak period + full test suite green

### PROD Environment (Phase 3)
**Objective:** Zero-disruption upgrades with maximum control

**Approach:** One cluster at a time with extensive validation
- Manual upgrade initiation for precise timing control
- Maintenance windows during off-peak hours
- PDB validation before each cluster
- Rollback plan per cluster

**Maintenance window strategy:**
```bash
# Set maintenance windows for Sunday 2-6 AM
for cluster in prod-cluster-{1..4}; do
  gcloud container clusters update $cluster \
    --zone ZONE \
    --maintenance-window-start "2024-XX-XXTXX:XX:XXZ" \
    --maintenance-window-end "2024-XX-XXTXX:XX:XXZ" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
done
```

**Per-cluster sequence:**
1. **prod-cluster-1** (Week 3, Sunday #1)
2. **prod-cluster-2** (Week 3, Sunday #2) — after 48h validation
3. **prod-cluster-3** (Week 4, Sunday #1) — after validation  
4. **prod-cluster-4** (Week 4, Sunday #2) — final cluster

## Pre-Upgrade Preparation

### Version Compatibility Check
```bash
# Verify 1.33 is available in Regular channel across all regions
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels)" | grep -A5 "regular"

# Check for deprecated API usage across all clusters
for cluster in cluster-{1..12}; do
  echo "=== $cluster ==="
  kubectl config use-context $cluster
  kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
done
```

### Infrastructure Readiness
```bash
# Standard pre-upgrade checklist per cluster
for cluster in cluster-{1..12}; do
  echo "=== Cluster: $cluster ==="
  
  # PDB audit
  kubectl get pdb -A -o wide
  
  # Node pool surge settings (recommend 5% of pool size, min 1)
  gcloud container node-pools list --cluster $cluster --zone ZONE
  
  # Resource utilization
  kubectl top nodes
done
```

## Risk Mitigation

### Upgrade Blockers Prevention
1. **PDB audit:** Ensure `minAvailable` allows at least 1 pod disruption
2. **Resource headroom:** Verify 20% CPU/memory headroom for surge nodes  
3. **Bare pod elimination:** Convert to Deployments/StatefulSets
4. **Webhook compatibility:** Test cert-manager, OPA, service mesh against 1.33

### Rollback Strategy
- **DEV/STAGING:** Acceptable to leave at 1.33 even if issues found
- **PROD:** Per-cluster rollback capability required

```bash
# Emergency rollback pattern (if needed in PROD)
# 1. Create new node pool at 1.32
gcloud container node-pools create rollback-pool \
  --cluster PROD_CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.X-gke.Y

# 2. Cordon upgraded nodes, migrate workloads
kubectl cordon -l cloud.google.com/gke-nodepool=default-pool

# 3. Delete upgraded pool after validation
```

## Communication Plan

### Stakeholder Notifications

**Week before DEV (Phase 1):**
- Engineering teams: Deprecated API cleanup required
- Platform team: Monitoring dashboards updated

**Week before STAGING (Phase 2):**  
- QA teams: Regression test schedule
- DevOps: CI/CD pipeline compatibility confirmed

**Week before PROD (Phase 3):**
- SRE: On-call coverage for maintenance windows  
- Business stakeholders: Planned maintenance notifications

### Status Reporting
- **Daily:** Upgrade progress dashboard
- **Post-phase:** Go/No-Go decision documentation
- **Weekly:** Executive summary of fleet status

## Monitoring & Validation

### Key Metrics to Track
```bash
# Application health
kubectl get deployments -A | grep -v "AVAILABLE.*AVAILABLE"

# System stability  
kubectl get pods -n kube-system | grep -v Running

# Performance baseline
# - API server latency (Cloud Monitoring)
# - Pod startup times
# - Application response times
```

### Automated Validation Script
```bash
#!/bin/bash
# post-upgrade-validation.sh

CLUSTER=$1
echo "Validating cluster: $CLUSTER"

# Control plane version
MASTER_VERSION=$(gcloud container clusters describe $CLUSTER --zone $ZONE --format="value(currentMasterVersion)")
echo "Master version: $MASTER_VERSION"

# Node versions  
gcloud container node-pools list --cluster $CLUSTER --zone $ZONE

# Workload health
UNHEALTHY=$(kubectl get pods -A | grep -c -v -E "(Running|Completed|Succeeded)")
echo "Unhealthy pods: $UNHEALTHY"

if [ $UNHEALTHY -eq 0 ]; then
  echo "✅ Cluster $CLUSTER validation PASSED"
  exit 0
else
  echo "❌ Cluster $CLUSTER validation FAILED"  
  kubectl get pods -A | grep -v -E "(Running|Completed|Succeeded)"
  exit 1
fi
```

## Alternative: GKE Rollout Sequencing (Advanced Option)

If you want automated fleet-wide orchestration instead of manual environment progression:

```bash
# Configure fleet-based rollout sequencing
# DEV fleet upgrades first, 48h soak, then STAGING, then PROD
gcloud container fleet clusterupgrade update \
  --project PROJECT_ID \
  --default-upgrade-soaking 48h
```

**Note:** Requires all clusters to be on identical versions initially. More complex than manual progression but provides automated orchestration.

## Next Steps

1. **Week -1:** Complete pre-upgrade preparation checklist
2. **Week 1:** Execute DEV phase, monitor for 48h
3. **Week 2:** Execute STAGING phase, monitor for 72h  
4. **Week 3-4:** Execute PROD phase, one cluster per maintenance window

This strategy balances upgrade velocity with production safety, using your Regular channel enrollment to enable natural rollout sequencing while maintaining manual control over timing and scope.