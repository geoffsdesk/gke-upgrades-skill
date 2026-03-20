# GKE Upgrade Plan: 1.28 → 1.30

**Cluster:** Standard GKE | **Channel:** Regular | **Location:** us-central1-a  
**Current:** 1.28 | **Target:** 1.30 | **Timeline:** End of quarter

## Executive Summary

This upgrade requires two sequential minor version jumps (1.28→1.29→1.30) to safely handle API deprecations and compatibility issues. Total estimated timeline: 2-3 weeks including validation periods between versions.

## Version Compatibility Analysis

### Sequential upgrade path (REQUIRED)
- **Step 1:** 1.28 → 1.29 (allow 1 week for validation)
- **Step 2:** 1.29 → 1.30 (final target)

While GKE technically allows skipping minor versions via CLI, sequential upgrades are strongly recommended to catch compatibility issues between versions.

### Critical checks needed
- [ ] **Deprecated APIs:** Check for removed APIs between 1.28-1.30 using GKE deprecation insights dashboard
- [ ] **Postgres operator compatibility:** Verify your Postgres operator supports K8s 1.29 and 1.30
- [ ] **ML inference workloads:** Confirm GPU driver compatibility with target node image versions
- [ ] **Version availability:** Confirm 1.29 and 1.30 are available in Regular channel

```bash
# Check available versions
gcloud container get-server-config --zone us-central1-a \
  --format="yaml(channels)" | grep -A 10 "channel: REGULAR"

# Check deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```

## Node Pool Upgrade Strategy

### General-purpose pool
- **Strategy:** Surge upgrade
- **Settings:** `maxSurge=2, maxUnavailable=0`
- **Rationale:** Fast upgrade while maintaining capacity for workload rescheduling

### High-memory pool (Postgres)
- **Strategy:** Surge upgrade (conservative)
- **Settings:** `maxSurge=1, maxUnavailable=0`
- **Rationale:** Database workloads need careful handling; PDBs will protect running instances
- **Special considerations:** 
  - Ensure Postgres operator PDBs are properly configured
  - Coordinate with DB team for maintenance window
  - Verify PV reclaim policies and recent backups

### GPU pool (ML inference)
- **Strategy:** Surge upgrade (conservative)
- **Settings:** `maxSurge=1, maxUnavailable=0`
- **Rationale:** GPU VMs don't support live migration; minimize temporary GPU overcapacity
- **Special considerations:**
  - **Critical:** Verify GPU driver compatibility - GKE auto-installs drivers matching the target version, which may change CUDA versions
  - Test inference workloads against target GKE version in staging first
  - If GPU quota is insufficient for surge, use `maxSurge=0, maxUnavailable=1` instead

## Rollout Timeline

### Week 1: Pre-flight and 1.28→1.29
- **Day 1-2:** Pre-upgrade validation and testing
- **Day 3:** Control plane upgrade to 1.29 (maintenance window)
- **Day 4:** General-purpose pool upgrade
- **Day 5:** High-memory pool upgrade (coordinate with DB team)
- **Day 6-7:** GPU pool upgrade + validation

### Week 2: Validation and 1.29→1.30
- **Day 1-3:** Soak time on 1.29, monitor all workloads
- **Day 4:** Control plane upgrade to 1.30
- **Day 5:** General-purpose pool upgrade
- **Day 6:** High-memory pool upgrade
- **Day 7:** GPU pool upgrade

### Week 3: Buffer for issues
- Final validation and documentation

## Maintenance Configuration

```bash
# Set maintenance window (example: Saturday 2-6 AM CT)
gcloud container clusters update CLUSTER_NAME \
  --zone us-central1-a \
  --maintenance-window-start 2024-01-06T08:00:00Z \
  --maintenance-window-end 2024-01-06T12:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Configure surge settings for each pool
gcloud container node-pools update general-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

gcloud container node-pools update high-memory-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

## Workload Readiness Requirements

### All pools
- [ ] PDBs configured for critical workloads (not overly restrictive)
- [ ] No bare pods - all managed by Deployments/StatefulSets
- [ ] Adequate `terminationGracePeriodSeconds` (30-60s for most workloads)
- [ ] Resource requests/limits properly set

### Postgres-specific
- [ ] Recent database backups completed
- [ ] PV reclaim policies verified (should be "Retain" for production)
- [ ] Postgres operator PDBs configured (typically `maxUnavailable: 0` for primaries)
- [ ] Connection pooling configured to handle brief connection drops

### GPU workload-specific
- [ ] Test ML inference workloads against target GKE version in staging
- [ ] Verify CUDA version compatibility with your ML frameworks
- [ ] Consider graceful model serving shutdown procedures
- [ ] Monitor GPU utilization during upgrade to detect issues

## Risk Mitigation

### High-risk factors
1. **GPU driver changes:** CUDA version may change silently
2. **Database disruption:** Postgres pods will restart during node upgrade
3. **API deprecations:** 1.28→1.30 spans significant K8s changes

### Mitigation strategies
- Sequential upgrade path with validation between versions
- Conservative surge settings for stateful workloads
- Staging environment testing (especially for GPU workloads)
- Database team coordination and backup verification
- Rollback plan documented (though control plane downgrade requires GKE support)

## Success Criteria

After each version upgrade:
- [ ] All nodes at target version
- [ ] All deployments at desired replica count
- [ ] Postgres databases accessible and performing normally
- [ ] ML inference endpoints responding with expected latency
- [ ] No CrashLoopBackOff or Pending pods
- [ ] GPU utilization and CUDA operations working correctly

## Next Steps

1. **Immediate:** Verify version availability and deprecated API usage
2. **This week:** Test 1.29 upgrade in staging environment (especially GPU workloads)
3. **Schedule:** Book maintenance windows with stakeholders
4. **Coordinate:** Align with DB team for Postgres pool upgrade timing

Would you like me to create detailed runbooks with the specific gcloud commands for each upgrade step, or focus on any particular aspect of this plan?