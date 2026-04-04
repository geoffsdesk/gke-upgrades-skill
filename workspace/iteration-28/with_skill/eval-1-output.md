# GKE Upgrade Plan: Standard Cluster 1.32 → 1.33

## Cluster Overview
- **Cluster:** Standard GKE cluster
- **Channel:** Regular release channel  
- **Current version:** 1.32
- **Target version:** 1.33
- **Location:** us-central1-a (zonal)
- **Node pools:** 3 pools (general-purpose, high-memory/Postgres, GPU/ML inference)

## Pre-Upgrade Assessment

### Version Compatibility ✅
- Target version 1.33 is available in Regular channel
- Sequential minor version upgrade (1.32→1.33) - supported
- Node pools can upgrade directly to 1.33 after control plane

### Critical Checks Required

**Deprecated API Usage:**
```bash
# Check for deprecated APIs (most common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Check GKE deprecation insights
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=us-central1-a \
    --project=PROJECT_ID \
    --filter="category.category:RELIABILITY"
```

**Postgres Operator Compatibility:**
- Verify your Postgres operator version supports Kubernetes 1.33
- Check operator release notes for any breaking changes
- Test in dev/staging environment first

**GPU Driver Compatibility:**
- GKE will auto-install GPU drivers matching 1.33
- This may change CUDA version - test inference workloads in staging
- Validate model loading and throughput with new driver version

## Upgrade Strategy

### Node Pool Upgrade Strategies

**1. General-purpose pool:**
- **Strategy:** Surge upgrade
- **Settings:** `maxSurge=5%` of pool size (minimum 1), `maxUnavailable=0`
- **Rationale:** Stateless workloads, zero-downtime rolling replacement

**2. High-memory pool (Postgres):**
- **Strategy:** Surge upgrade (conservative)
- **Settings:** `maxSurge=1, maxUnavailable=0`
- **Rationale:** One-at-a-time replacement to protect database workloads
- **Special handling:** Verify PDBs protect quorum during upgrade

**3. GPU pool (ML inference):**
- **Strategy:** Surge upgrade with drain-first approach
- **Settings:** `maxSurge=0, maxUnavailable=1`
- **Rationale:** GPU reservations typically have no surge capacity; maxUnavailable is the primary lever
- **Special handling:** Brief inference downtime per node (GPUs don't support live migration)

### Upgrade Sequence
1. **Control plane** (automatic, ~10-15 minutes)
2. **General-purpose pool** (lowest risk, validates surge settings)  
3. **GPU pool** (validate inference workloads)
4. **High-memory pool** (most critical, upgrade last after validation)

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist
- [ ] Cluster: us-central1-a | Mode: Standard | Channel: Regular
- [ ] Current version: 1.32 | Target version: 1.33

Compatibility
- [ ] Target version available in Regular channel
- [ ] No deprecated API usage (check GKE deprecation insights dashboard)
- [ ] GKE release notes reviewed for 1.32→1.33 breaking changes
- [ ] Postgres operator compatible with Kubernetes 1.33
- [ ] GPU driver compatibility confirmed for inference workloads
- [ ] ML model loading tested with target version in staging

Workload Readiness
- [ ] PDBs configured for Postgres workloads (protect quorum)
- [ ] No bare pods — all managed by controllers
- [ ] terminationGracePeriodSeconds adequate for Postgres graceful shutdown
- [ ] Postgres backups completed, PV reclaim policies verified (Retain)
- [ ] Inference workloads tested with new GPU driver version

Infrastructure
- [ ] Node pool upgrade strategies configured:
      • General: maxSurge=5%, maxUnavailable=0
      • High-memory: maxSurge=1, maxUnavailable=0  
      • GPU: maxSurge=0, maxUnavailable=1
- [ ] Sufficient compute quota for general-purpose surge nodes
- [ ] Maintenance window configured (off-peak hours)
- [ ] No maintenance exclusions blocking the upgrade

Ops Readiness
- [ ] Monitoring and alerting active
- [ ] Baseline metrics captured (inference latency, DB performance)
- [ ] Upgrade window communicated to stakeholders
- [ ] On-call team available during upgrade window
- [ ] Rollback plan documented
```

## Upgrade Runbook

### Step 1: Pre-flight Checks
```bash
# Verify current state
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check available versions
gcloud container get-server-config --zone us-central1-a \
  --format="yaml(channels.REGULAR)"

# Verify no deprecated APIs
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed
kubectl get pdb -A -o wide
```

### Step 2: Control Plane Upgrade
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-central1-a \
  --master \
  --cluster-version 1.33

# Monitor progress (~10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="value(currentMasterVersion)"

# Verify system pods healthy
kubectl get pods -n kube-system
```

### Step 3: Configure Node Pool Surge Settings
```bash
# General-purpose pool (5% surge, adjust based on actual pool size)
gcloud container node-pools update GENERAL_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# High-memory pool (conservative)
gcloud container node-pools update HIGH_MEMORY_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# GPU pool (drain-first, no surge capacity assumed)
gcloud container node-pools update GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

### Step 4: Node Pool Upgrades (Sequential)

**General-purpose pool first:**
```bash
gcloud container node-pools upgrade GENERAL_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33

# Monitor progress
watch 'kubectl get nodes -o wide | grep GENERAL_POOL_NAME'
```

**GPU pool second:**
```bash
gcloud container node-pools upgrade GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33

# Test inference workloads after each node
kubectl get pods -l workload-type=inference -o wide
# Run inference smoke tests
```

**High-memory pool last:**
```bash
gcloud container node-pools upgrade HIGH_MEMORY_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33

# Monitor Postgres health closely
kubectl get pods -l app=postgres -o wide
kubectl logs -l app=postgres --tail=50
```

## Validation Steps

After each node pool upgrade:
```bash
# Node status
kubectl get nodes -o wide

# Pod health  
kubectl get pods -A | grep -v Running | grep -v Completed

# Postgres specific
kubectl get statefulsets -A
kubectl exec -it postgres-0 -- psql -c "SELECT version();"

# GPU/inference specific
kubectl get pods -l workload-type=inference
# Run inference endpoint health checks
```

## Troubleshooting Common Issues

### GPU Pool Issues
- **Inference downtime:** Expected during node replacement (GPUs don't live migrate)
- **Driver compatibility:** If models fail to load, verify CUDA version compatibility
- **Quota exhaustion:** maxSurge=0 avoids this, but upgrade is slower

### Postgres Pool Issues  
- **PDB blocking drain:** Temporarily relax PDB if blocking (restore after upgrade)
- **Connection interruption:** Brief reconnection during pod rescheduling is normal
- **Performance impact:** Monitor query latency during upgrade window

### General Issues
- **Pods pending:** Check resource constraints, may need to reduce maxSurge
- **Admission webhook failures:** Common with cert-manager, may need operator upgrade

## Rollback Plan

**Control plane:** Contact GKE support for minor version rollback (not customer-initiated)

**Node pools:** Create new pools at 1.32 and migrate workloads if critical issues arise:
```bash
# Emergency rollback - create new pool at old version
gcloud container node-pools create POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.32 \
  --num-nodes NUM_NODES

# Cordon upgraded pool and migrate workloads
kubectl cordon -l cloud.google.com/gke-nodepool=UPGRADED_POOL
```

## Timeline Estimate

- **Control plane:** 15 minutes
- **General-purpose pool:** 30-60 minutes (depends on size)
- **GPU pool:** 45-90 minutes (drain-first is slower)  
- **High-memory pool:** 30-60 minutes (conservative settings)
- **Total window:** 2-4 hours including validation

## Success Criteria

- [ ] All nodes at version 1.33
- [ ] All pods Running/Completed
- [ ] Postgres queries executing normally
- [ ] ML inference endpoints responding with acceptable latency
- [ ] No increase in error rates or latency beyond baseline
- [ ] System pods healthy in kube-system namespace

Schedule this upgrade during your next maintenance window, ensuring the Postgres and ML teams are available for validation. Test the exact upgrade path in dev/staging first, especially for Postgres operator and GPU driver compatibility.