# GKE Upgrade Plan: 1.28 → 1.30

**Cluster:** Standard GKE | **Channel:** Regular | **Zone:** us-central1-a  
**Current Version:** 1.28 | **Target Version:** 1.30  
**Timeline:** End of quarter

## Executive Summary

This requires a two-phase sequential upgrade (1.28 → 1.29 → 1.30) to follow best practices. Total estimated time: 4-6 hours across two maintenance windows. The upgrade will proceed control plane first, then node pools in order of criticality: general-purpose → high-memory → GPU.

## Version Compatibility & Path

**Recommended Path:** 1.28 → 1.29 → 1.30 (sequential minor versions)
- While GKE technically allows skipping versions via CLI, sequential upgrades are safer for catching compatibility issues
- **Phase 1:** 1.28 → 1.29 (Week 1)
- **Phase 2:** 1.29 → 1.30 (Week 2, after validation)

**Pre-requisites to verify:**
- Confirm 1.29 and 1.30 availability in Regular channel
- Check Postgres operator compatibility with K8s 1.29/1.30
- Verify GPU driver compatibility with target node images
- Scan for deprecated API usage (most common upgrade failure)

## Node Pool Upgrade Strategy

### General-Purpose Pool
- **Strategy:** Surge upgrade
- **Settings:** `maxSurge=3, maxUnavailable=0`
- **Rationale:** Higher surge for speed, zero unavailable for safety

### High-Memory Pool (Postgres)
- **Strategy:** Surge upgrade  
- **Settings:** `maxSurge=1, maxUnavailable=0`
- **Rationale:** Conservative approach for stateful workloads, rely on PDBs for protection

### GPU Pool (ML Inference)
- **Strategy:** Surge upgrade
- **Settings:** `maxSurge=1, maxUnavailable=0`
- **Rationale:** GPUs are expensive, minimize temporary overcapacity

## Maintenance Windows

**Recommended Schedule:**
- **Phase 1 (1.28→1.29):** Weekend morning, allow 3-4 hours
- **Phase 2 (1.29→1.30):** Following weekend, allow 2-3 hours

**Configure maintenance window:**
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone us-central1-a \
  --maintenance-window-start 2024-XX-XXTXX:XX:XXZ \
  --maintenance-window-end 2024-XX-XXTXX:XX:XXZ \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Pre-Upgrade Requirements

### Critical Workload Preparation
- **PDBs:** Ensure Postgres operator and ML inference services have appropriate PodDisruptionBudgets
- **No bare pods:** Verify all workloads are managed by Deployments/StatefulSets
- **Termination grace:** Confirm adequate `terminationGracePeriodSeconds` for database graceful shutdown
- **Postgres-specific:** Complete backup, verify PV reclaim policies are not "Delete"

### Compatibility Checks
```bash
# Check for deprecated APIs
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Verify current versions
gcloud container clusters describe CLUSTER_NAME --zone us-central1-a \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Available versions in Regular channel
gcloud container get-server-config --zone us-central1-a \
  --format="yaml(channels.regular)"
```

## Rollout Sequence

### Phase 1: 1.28 → 1.29

1. **Control plane upgrade** (~15 min)
2. **General-purpose pool** (~30-45 min)  
3. **Validation & soak** (~30 min)
4. **High-memory pool** (~45-60 min)
5. **Validation & soak** (~30 min)
6. **GPU pool** (~30-45 min)
7. **Full system validation** (~30 min)

### Phase 2: 1.29 → 1.30 (1 week later)
Same sequence, should be faster as workloads are proven compatible.

## Risk Mitigation

### High-Risk Areas
1. **Postgres operator:** Most likely to have compatibility issues
2. **GPU workloads:** Driver/runtime dependencies
3. **Custom admission webhooks:** May reject new pod specs

### Rollback Strategy
- **Control plane:** Downgrade requires GKE support (rare)
- **Node pools:** Create new pools at previous version, migrate workloads
- **Preparation:** Document current node pool configurations for rollback

## Success Criteria

### Per-Phase Validation
- [ ] All nodes at target version and Ready status
- [ ] All system pods (kube-system) healthy
- [ ] Postgres operator reconciling successfully
- [ ] ML inference endpoints responding within SLA
- [ ] No increase in application error rates
- [ ] Monitoring and logging pipelines intact

### Final Validation
- [ ] Full application smoke tests
- [ ] Performance within baseline (latency, throughput)
- [ ] All StatefulSets at desired replica count
- [ ] PVC attachments successful

## Timeline & Responsibilities

**3 weeks before:**
- [ ] Postgres operator compatibility verification
- [ ] GPU driver compatibility check
- [ ] Deprecated API scan and remediation

**1 week before:**  
- [ ] PDB configuration review
- [ ] Baseline metrics capture
- [ ] Stakeholder notification

**Day of:**
- [ ] On-call engineer available
- [ ] Monitoring dashboards active
- [ ] Execute upgrade runbook

**Next Steps:**
Would you like me to produce the detailed pre-flight checklist and step-by-step runbook with actual `gcloud` commands for your cluster?