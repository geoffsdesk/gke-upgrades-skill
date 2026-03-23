# GKE Upgrade Plan: 1.32 → 1.33

**Cluster Details:**
- Mode: Standard GKE
- Channel: Regular
- Current Version: 1.32
- Target Version: 1.33
- Region: us-central1-a
- Node Pools: 3 (general-purpose, high-memory/Postgres, GPU/ML inference)

## Executive Summary

This is a **minor version upgrade** requiring sequential steps: control plane first, then node pools. Total estimated time: 4-8 hours depending on pool sizes and surge settings. The upgrade should complete well before end of quarter given Regular channel timing.

## Version Compatibility Assessment

✅ **Target Version Available:** GKE 1.33 is available in Regular channel  
✅ **Version Skew:** 1.32→1.33 is a single minor version jump (supported)  
⚠️ **Breaking Changes:** Review [GKE 1.33 release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) for:
- Kubernetes API deprecations
- Node image changes affecting GPU drivers
- Any Postgres operator compatibility issues

**Pre-upgrade API check:**
```bash
# Check for deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# GKE deprecation insights
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=us-central1-a \
    --project=PROJECT_ID
```

## Upgrade Strategy by Node Pool

### 1. General-Purpose Pool (Upgrade First)
- **Strategy:** Surge upgrade
- **Settings:** `maxSurge=5%` (minimum 1), `maxUnavailable=0`
- **Rationale:** Stateless workloads, rolling replacement with zero downtime

### 2. High-Memory Pool (Postgres) - Upgrade Second
- **Strategy:** Conservative surge upgrade  
- **Settings:** `maxSurge=1`, `maxUnavailable=0`
- **Rationale:** Database workloads need careful handling, let PDBs protect data

### 3. GPU Pool (ML Inference) - Upgrade Last
- **Strategy:** Availability-focused surge (assuming no surge GPU quota)
- **Settings:** `maxSurge=0`, `maxUnavailable=1`
- **Rationale:** GPU VMs don't support live migration, limited surge capacity typical
- **Special Considerations:** GPU driver version will change with node image upgrade

## Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist
- [ ] Cluster: YOUR_CLUSTER | Mode: Standard | Channel: Regular
- [ ] Current version: 1.32 | Target version: 1.33

Compatibility
- [ ] Target version available in Regular channel (`gcloud container get-server-config --zone us-central1-a --format="yaml(channels)"`)
- [ ] No deprecated API usage (check GKE deprecation insights dashboard)
- [ ] GKE release notes reviewed for 1.32→1.33 breaking changes
- [ ] Postgres operator compatibility verified with K8s 1.33
- [ ] GPU driver compatibility confirmed with target node image
- [ ] ML inference framework compatibility tested

Workload Readiness
- [ ] PDBs configured for Postgres and ML inference workloads (not overly restrictive)
- [ ] No bare pods — all managed by controllers
- [ ] terminationGracePeriodSeconds adequate for graceful shutdown (especially Postgres)
- [ ] Postgres PV backups completed, reclaim policies verified
- [ ] Resource requests/limits set on all containers
- [ ] ML model serving can handle pod restarts gracefully

Infrastructure
- [ ] Surge settings configured per pool (see strategy above)
- [ ] Skip-level node pool upgrade evaluated (N/A - single minor jump)
- [ ] Sufficient compute quota for surge nodes (general + high-memory pools)
- [ ] GPU surge quota confirmed OR using maxUnavailable mode
- [ ] Maintenance window configured for off-peak hours

Ops Readiness
- [ ] Monitoring and alerting active
- [ ] Baseline metrics captured (inference latency, DB query times)
- [ ] Upgrade window communicated to stakeholders
- [ ] Rollback plan documented
- [ ] On-call team aware and available
```

## Step-by-Step Runbook

### Phase 1: Control Plane Upgrade (15-20 minutes)

```bash
# Pre-flight checks
gcloud container clusters describe YOUR_CLUSTER \
  --zone us-central1-a \
  --format="table(name, currentMasterVersion, nodePools[].version)"

kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed

# Upgrade control plane
gcloud container clusters upgrade YOUR_CLUSTER \
  --zone us-central1-a \
  --master \
  --cluster-version 1.33

# Verify control plane (wait ~15 minutes)
gcloud container clusters describe YOUR_CLUSTER \
  --zone us-central1-a \
  --format="value(currentMasterVersion)"

kubectl get pods -n kube-system
```

### Phase 2: General-Purpose Pool (30-60 minutes)

```bash
# Configure surge settings
gcloud container node-pools update GENERAL_POOL_NAME \
  --cluster YOUR_CLUSTER \
  --zone us-central1-a \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# Upgrade general pool
gcloud container node-pools upgrade GENERAL_POOL_NAME \
  --cluster YOUR_CLUSTER \
  --zone us-central1-a \
  --cluster-version 1.33

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

### Phase 3: High-Memory Pool (Postgres) - 45-90 minutes

```bash
# Configure conservative surge settings
gcloud container node-pools update HIGH_MEMORY_POOL_NAME \
  --cluster YOUR_CLUSTER \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Verify Postgres PDBs are reasonable (not 100% minAvailable)
kubectl get pdb -A -o wide

# Upgrade high-memory pool
gcloud container node-pools upgrade HIGH_MEMORY_POOL_NAME \
  --cluster YOUR_CLUSTER \
  --zone us-central1-a \
  --cluster-version 1.33

# Monitor Postgres pod health during upgrade
kubectl get pods -n POSTGRES_NAMESPACE -w
```

### Phase 4: GPU Pool (ML Inference) - 60-120 minutes

```bash
# Configure GPU-optimized settings (no surge capacity assumed)
gcloud container node-pools update GPU_POOL_NAME \
  --cluster YOUR_CLUSTER \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

# Pre-upgrade: verify ML workloads can handle restarts
kubectl get pods -n ML_NAMESPACE

# Upgrade GPU pool
gcloud container node-pools upgrade GPU_POOL_NAME \
  --cluster YOUR_CLUSTER \
  --zone us-central1-a \
  --cluster-version 1.33

# Post-upgrade: verify GPU driver and ML inference
kubectl get nodes -o wide
kubectl get pods -n ML_NAMESPACE
# Test inference endpoints
```

## Post-Upgrade Validation

```markdown
Post-Upgrade Checklist

Cluster Health
- [ ] Control plane at 1.33: `gcloud container clusters describe YOUR_CLUSTER --zone us-central1-a --format="value(currentMasterVersion)"`
- [ ] All node pools at 1.33: `gcloud container node-pools list --cluster YOUR_CLUSTER --zone us-central1-a`
- [ ] All nodes Ready: `kubectl get nodes`
- [ ] System pods healthy: `kubectl get pods -n kube-system`

Workload Health
- [ ] All deployments at desired replica count: `kubectl get deployments -A`
- [ ] No CrashLoopBackOff or Pending pods: `kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded`
- [ ] Postgres cluster healthy and accepting connections
- [ ] ML inference endpoints responding correctly
- [ ] GPU drivers loaded and accessible to pods

Performance
- [ ] Postgres query latency within baseline
- [ ] ML inference latency within baseline (may improve with newer drivers)
- [ ] No resource contention or throttling
```

## Timing and Maintenance Window

**Recommended Window:** 6-hour weekend maintenance window
- Phase 1 (Control Plane): 15-20 minutes
- Phase 2 (General Pool): 30-60 minutes  
- Phase 3 (Postgres Pool): 45-90 minutes
- Phase 4 (GPU Pool): 60-120 minutes
- Validation & Buffer: 60 minutes

**Set maintenance window:**
```bash
gcloud container clusters update YOUR_CLUSTER \
  --zone us-central1-a \
  --maintenance-window-start 2024-12-08T02:00:00Z \
  --maintenance-window-end 2024-12-08T08:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```

## Rollback Strategy

- **Control Plane:** Downgrade requires GKE support involvement
- **Node Pools:** Create new pools at 1.32 and migrate workloads if needed
- **Postgres:** Ensure PV reclaim policies allow data preservation
- **GPU:** Test GPU driver compatibility in staging first

## Risk Mitigation

1. **Test in staging first** - Run identical upgrade on staging cluster
2. **Postgres backup** - Full backup before maintenance window
3. **ML model validation** - Verify inference accuracy post-upgrade
4. **PDB review** - Ensure Postgres PDBs allow some disruption
5. **GPU driver testing** - Confirm CUDA/framework compatibility

This upgrade plan balances speed with safety, upgrading the least critical pool first and the most sensitive (GPU/ML) last. The sequential approach allows validation at each step and reduces blast radius if issues arise.