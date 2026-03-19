# GKE Cluster Upgrade Plan

**Cluster:** Standard GKE, Regular channel, us-central1-a  
**Current Version:** 1.28  
**Target Version:** 1.30  
**Timeline:** Before end of quarter

## Executive Summary

This plan covers upgrading your 3-node-pool cluster through two sequential minor versions (1.28→1.29→1.30). The upgrade will prioritize safety for your Postgres workloads and handle GPU driver compatibility carefully. Total estimated duration: 2-4 hours depending on cluster size.

## Version Compatibility Analysis

**Upgrade Path:** 1.28 → 1.29 → 1.30 (sequential minor versions recommended for safety)

**Critical Checks Required:**
- [ ] Verify 1.29 and 1.30 are available in Regular channel for us-central1-a
- [ ] Review deprecated APIs - especially important for 1.29+ (PodSecurityPolicy removal, beta API graduations)
- [ ] Confirm Postgres operator compatibility with K8s 1.29 and 1.30
- [ ] Validate GPU driver versions for ML inference workloads

## Node Pool Upgrade Strategy

### 1. General-Purpose Pool
- **Strategy:** Surge upgrade
- **Settings:** `maxSurge=2, maxUnavailable=0`
- **Rationale:** Faster completion, zero downtime for stateless workloads

### 2. High-Memory Pool (Postgres)
- **Strategy:** Surge upgrade (conservative)
- **Settings:** `maxSurge=1, maxUnavailable=0`
- **Rationale:** Database workloads need careful handling; PDBs will protect during drain
- **Special Considerations:** 
  - Verify Postgres operator PDBs are configured
  - Ensure connection pooling can handle brief connection interruptions
  - Consider upgrading during low-traffic window

### 3. GPU Pool (ML Inference)
- **Strategy:** Surge upgrade (conservative)
- **Settings:** `maxSurge=1, maxUnavailable=0`
- **Critical Notes:**
  - GPU driver version will change with node image update
  - New CUDA version may affect ML frameworks
  - **Must test inference workloads on target version first**
  - If GPU quota is scarce: use `maxSurge=0, maxUnavailable=1` instead

## Maintenance Windows & Timing

**Recommended Schedule:**
- **Phase 1 (1.28→1.29):** Weekend maintenance window, 4-hour block
- **Phase 2 (1.29→1.30):** Following weekend, 4-hour block
- **Soak Time:** 1 week between major phases for validation

```bash
# Configure maintenance window (Saturday 2-6 AM CT)
gcloud container clusters update CLUSTER_NAME \
  --zone us-central1-a \
  --maintenance-window-start YYYY-MM-DDTHH:MM:SSZ \
  --maintenance-window-end YYYY-MM-DDTHH:MM:SSZ \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Pre-Upgrade Validation Checklist

```
Infrastructure Readiness
- [ ] Target versions available: `gcloud container get-server-config --zone us-central1-a --format="yaml(channels)"`
- [ ] Sufficient compute quota for surge nodes in us-central1-a
- [ ] Postgres operator version supports K8s 1.29/1.30
- [ ] GPU driver compatibility tested with target GKE versions
- [ ] ML inference models tested against new CUDA version

Workload Protection
- [ ] PDBs configured for Postgres pods (not overly restrictive)
- [ ] ML inference deployments have adequate replicas for rolling updates
- [ ] No bare pods in any namespace
- [ ] Connection pooling configured for database connections
- [ ] Resource requests/limits set on all containers

Operational Readiness
- [ ] Database backups completed and verified
- [ ] ML model artifacts backed up
- [ ] Monitoring baselines captured (query latency, inference throughput)
- [ ] Rollback plan documented
- [ ] Team available during maintenance window
```

## Upgrade Execution Plan

### Phase 1: Upgrade to 1.29

**Step 1: Control Plane (10-15 minutes)**
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-central1-a \
  --master \
  --cluster-version 1.29.X-gke.YYYY
```

**Step 2: General-Purpose Pool (30-60 minutes)**
```bash
gcloud container node-pools update general-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade general-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.29.X-gke.YYYY
```

**Step 3: High-Memory Pool - Postgres (60-90 minutes)**
```bash
gcloud container node-pools update highmem-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Verify Postgres PDBs before proceeding
kubectl get pdb -n postgres-namespace

gcloud container node-pools upgrade highmem-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.29.X-gke.YYYY
```

**Step 4: GPU Pool (60-120 minutes)**
```bash
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.29.X-gke.YYYY
```

### Validation & Soak Period (1 week)

- [ ] All workloads healthy and performing within baseline
- [ ] Postgres query performance stable
- [ ] ML inference latency/throughput within acceptable range
- [ ] GPU driver and CUDA compatibility confirmed

### Phase 2: Upgrade to 1.30

Repeat the same sequence (control plane → general → highmem → GPU) with version 1.30.X-gke.YYYY.

## Risk Mitigation

**High-Risk Items:**
1. **GPU driver compatibility** - New GKE version may change CUDA version, breaking ML frameworks
   - **Mitigation:** Test inference workloads in staging cluster first
2. **Postgres operator compatibility** - Database operators often have K8s version dependencies  
   - **Mitigation:** Review operator release notes, test in non-prod
3. **PDB blocking drain** - Over-restrictive PDBs can stall upgrades
   - **Mitigation:** Review `minAvailable` settings, have temporary relaxation plan ready

**Rollback Strategy:**
- Control plane downgrades require GKE support involvement
- Node pool rollback: create new pool at previous version, migrate workloads
- Database restore from pre-upgrade backup if needed

## Troubleshooting Quick Reference

If upgrade stalls:
1. Check PDBs: `kubectl get pdb -A` (most common cause)
2. Check resource constraints: `kubectl get pods -A | grep Pending`
3. Check bare pods: Look for pods without ownerReferences
4. Monitor progress: `watch 'kubectl get nodes -o wide'`

## Success Criteria

- [ ] All node pools at target version 1.30
- [ ] All pods Running or Succeeded
- [ ] Postgres query performance within 5% of baseline
- [ ] ML inference throughput within 10% of baseline
- [ ] No stuck PDBs or failing health checks
- [ ] GPU driver version confirmed compatible with workloads

**Next Steps:** Schedule Phase 1 execution during your next maintenance window, ensuring the database and ML teams are available for validation.