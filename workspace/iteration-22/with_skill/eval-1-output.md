# GKE Upgrade Plan: Regular Channel 1.32 → 1.33

**Cluster:** Standard GKE cluster  
**Location:** us-central1-a (zonal)  
**Current:** 1.32 → **Target:** 1.33  
**Channel:** Regular  
**Timeline:** Before end of quarter

## Executive Summary

This is a **minor version upgrade** requiring sequential control plane upgrade (1.32→1.33) followed by node pool upgrades. Given your mixed workload types (general-purpose, Postgres, GPU inference), we'll use a conservative upgrade strategy with validation checkpoints between pools.

## Pre-Upgrade Planning

### Version Compatibility Check
```bash
# Verify 1.33 is available in Regular channel
gcloud container get-server-config --zone us-central1-a --format="yaml(channels)"

# Check current cluster state
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Critical: Check for deprecated APIs (common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Also check GKE deprecation insights
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=us-central1-a \
    --project=PROJECT_ID
```

### Node Pool Strategy Selection

**General-purpose pool:** Surge upgrade with `maxSurge=5%, maxUnavailable=0`  
**High-memory pool (Postgres):** Conservative surge with `maxSurge=1, maxUnavailable=0` + PDB protection  
**GPU pool (Inference):** `maxSurge=0, maxUnavailable=1` (assumes fixed GPU reservation with no surge capacity)

## Upgrade Sequence

### Phase 1: Control Plane Upgrade
**Timing:** Off-peak hours (evenings/weekends)  
**Duration:** 10-15 minutes  
**Impact:** Brief API unavailability (~2-5 minutes for zonal cluster)

```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-central1-a \
  --master \
  --cluster-version 1.33
```

**Validation checkpoint:**
```bash
# Confirm control plane version
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="value(currentMasterVersion)"

# Verify system pods healthy
kubectl get pods -n kube-system
```

### Phase 2: Node Pool Upgrades (Sequential)

#### Step 1: General-Purpose Pool (Lowest Risk)
Configure surge settings:
```bash
gcloud container node-pools update general-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

Upgrade:
```bash
gcloud container node-pools upgrade general-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33
```

**Validation:** Wait for completion, verify workloads healthy before proceeding.

#### Step 2: High-Memory Pool (Postgres - Stateful)
**Pre-requisites:**
- Ensure Postgres operator supports Kubernetes 1.33
- Configure PDBs for Postgres pods (if not already set)
- Take application-level backup via Postgres operator

Configure conservative surge:
```bash
gcloud container node-pools update high-memory-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

Upgrade:
```bash
gcloud container node-pools upgrade high-memory-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33
```

**Validation:** Monitor Postgres pod restarts, verify database connectivity and replication status.

#### Step 3: GPU Pool (Inference - Most Sensitive)
**Critical pre-steps:**
- **Test GPU driver compatibility:** Create a staging GPU node at 1.33, deploy representative inference workload, validate CUDA calls and model loading
- Verify inference service can handle brief capacity reduction during upgrade

Configure for fixed GPU reservation (no surge capacity):
```bash
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

Upgrade:
```bash
gcloud container node-pools upgrade gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33
```

**Validation:** Monitor inference latency, GPU utilization, and model serving health.

## Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist - Standard GKE 1.32→1.33
- [ ] Cluster: ___ | Mode: Standard | Channel: Regular
- [ ] Current version: 1.32 | Target version: 1.33

Compatibility
- [ ] 1.33 available in Regular channel (`gcloud container get-server-config --zone us-central1-a`)
- [ ] No deprecated API usage (check GKE deprecation insights dashboard)
- [ ] GKE release notes reviewed for 1.32→1.33 breaking changes
- [ ] Postgres operator compatibility with K8s 1.33 verified
- [ ] GPU driver compatibility confirmed with 1.33 node image

Workload Readiness
- [ ] PDBs configured for Postgres pods (not overly restrictive)
- [ ] No bare pods — all managed by controllers
- [ ] terminationGracePeriodSeconds adequate for graceful shutdown
- [ ] Postgres operator backup completed
- [ ] GPU inference staging test completed at target version

Infrastructure
- [ ] Node pool surge strategies configured:
      - General: maxSurge=2, maxUnavailable=0
      - High-memory: maxSurge=1, maxUnavailable=0  
      - GPU: maxSurge=0, maxUnavailable=1
- [ ] Sufficient compute quota for surge nodes (general + high-memory pools)
- [ ] Maintenance window configured for off-peak hours
- [ ] Skip-level upgrade not applicable (1.32→1.33 is single minor version)

Ops Readiness
- [ ] Monitoring active for all workload types (web, database, inference)
- [ ] Baseline metrics captured (API latency, DB performance, inference throughput)
- [ ] Upgrade window communicated to stakeholders
- [ ] On-call team aware and available
```

## Maintenance Windows & Controls

**Recommended maintenance window:**
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone us-central1-a \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-end "2024-01-06T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Optional upgrade control** (if you need to defer auto-upgrades while planning):
```bash
# "No minor or node upgrades" exclusion - allows CP patches but blocks disruptive changes
gcloud container clusters update CLUSTER_NAME \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "q4-upgrade-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Risk Mitigation

### High-Memory Pool (Postgres)
- **PDB Configuration:** Ensure `minAvailable: 1` for replica sets to prevent simultaneous drain of multiple replicas
- **Backup Strategy:** Take application-level backup before node upgrade
- **Monitoring:** Watch for extended pod startup times due to high memory allocation

### GPU Pool (Inference) 
- **Capacity Planning:** `maxUnavailable=1` causes temporary capacity reduction during upgrade
- **Driver Testing:** GPU driver version changes with GKE 1.33 — test inference workloads in staging first
- **Inference SLA:** Brief inference downtime expected as pods restart on new nodes (GPU VMs don't support live migration)

## Rollback Strategy

**Control Plane:** Minor version rollback requires GKE support involvement. Not self-service.

**Node Pools:** Create replacement pools at previous version if critical issues discovered:
```bash
# Example rollback for GPU pool if 1.33 has driver issues
gcloud container node-pools create gpu-pool-rollback \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.32 \
  --machine-type n1-standard-4 \
  --accelerator type=nvidia-tesla-t4,count=1 \
  --num-nodes 3

# Migrate workloads, then delete problematic pool
```

## Timeline & Duration Estimates

- **Control plane upgrade:** 15 minutes
- **General pool:** 30-45 minutes (depends on pool size)  
- **High-memory pool:** 45-60 minutes (conservative drain for stateful workloads)
- **GPU pool:** 60-90 minutes (GPU nodes take longer to initialize)
- **Total window:** 3-4 hours including validation checkpoints

**Recommendation:** Schedule for a 4-hour Saturday morning window (2AM-6AM) to accommodate any unexpected delays.

## Success Criteria

```bash
# Final validation commands
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

kubectl get nodes
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
```

All components at 1.33, no pods in error states, application health checks passing.

---

**Next Steps:**
1. Verify 1.33 availability in Regular channel for us-central1-a
2. Schedule staging validation for Postgres operator and GPU inference workloads
3. Book maintenance window and communicate to stakeholders
4. Execute control plane upgrade first, followed by sequential node pool upgrades

Let me know if you need the detailed runbook commands or have questions about any specific pool's upgrade strategy!