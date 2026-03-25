# GKE Upgrade Plan: Regular Channel 1.32 → 1.33

## Executive Summary
**Cluster:** Standard GKE, Regular channel, us-central1-a  
**Upgrade Path:** 1.32 → 1.33 (single minor version jump)  
**Timeline:** Target completion before end of quarter  
**Risk Level:** Medium (involves GPU pool + database workload)  

## Version Compatibility Assessment

**✅ Target Version Status:**
- GKE 1.33 is available in Regular channel
- Single minor version upgrade (recommended path)
- Node version skew will be within supported limits (nodes can stay at 1.32 during CP upgrade)

**Required Pre-Upgrade Checks:**
```bash
# Verify 1.33 availability in Regular channel
gcloud container get-server-config --zone us-central1-a \
  --format="yaml(channels.regular)"

# Check for deprecated API usage (critical!)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Review GKE deprecation insights
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=us-central1-a \
    --project=PROJECT_ID
```

## Upgrade Strategy by Node Pool

### 1. General-Purpose Pool (Upgrade First)
**Strategy:** Surge upgrade with moderate parallelism
```bash
# Configure surge settings
gcloud container node-pools update general-purpose-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```
**Rationale:** Stateless workloads can tolerate rolling replacement. 2-node surge provides good speed while managing resource usage.

### 2. GPU Pool (Upgrade Second) 
**Strategy:** Conservative surge with maxUnavailable (assumes fixed GPU reservation)
```bash
# Configure for GPU constraints
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```
**Rationale:** GPU nodes typically have fixed reservations with no surge capacity. `maxUnavailable=1` is the primary lever - drains first, no extra GPUs needed, but causes temporary capacity dip. **Critical:** Verify GPU driver compatibility with GKE 1.33 in staging before production upgrade.

### 3. High-Memory Pool (Postgres - Upgrade Last)
**Strategy:** Ultra-conservative surge 
```bash
# Configure for database safety
gcloud container node-pools update high-memory-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```
**Rationale:** Database workloads require maximum care. One-at-a-time replacement with PDB protection.

## Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist
- [ ] Cluster: ___ | Mode: Standard | Channel: Regular
- [ ] Current version: 1.32 | Target version: 1.33

Compatibility
- [ ] Target version available in Regular channel
- [ ] No deprecated API usage (check insights dashboard + metrics endpoint)
- [ ] GKE 1.32→1.33 release notes reviewed for breaking changes
- [ ] Postgres operator compatibility with GKE 1.33 verified
- [ ] GPU driver compatibility confirmed with 1.33 node image
- [ ] ML inference framework compatibility tested in staging

Workload Readiness  
- [ ] PDBs configured for Postgres workloads (minAvailable: 1 or 50%)
- [ ] PDBs configured for ML inference services (minAvailable: 1)
- [ ] No bare pods — all managed by controllers
- [ ] terminationGracePeriodSeconds adequate for graceful shutdown
- [ ] Postgres PV backups completed, reclaim policies = Retain
- [ ] GPU workload staging validation completed

Infrastructure
- [ ] Node pool surge strategies configured (see commands above)
- [ ] Sufficient compute quota for general-purpose surge nodes
- [ ] GPU reservation headroom checked (if using maxSurge>0)
- [ ] Maintenance window configured for off-peak hours
- [ ] Scheduled upgrade notifications enabled (72h advance warning)

Ops Readiness
- [ ] Baseline metrics captured (API latency, inference latency, DB performance)
- [ ] Postgres backups automated and verified
- [ ] ML model serving health checks active
- [ ] Upgrade window communicated to stakeholders
- [ ] On-call team available during upgrade window
```

## Upgrade Runbook

### Phase 1: Control Plane Upgrade
```bash
# Upgrade control plane first (required order)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-central1-a \
  --master \
  --cluster-version 1.33

# Verify CP upgrade (wait 10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="value(currentMasterVersion)"

# Check system pods health
kubectl get pods -n kube-system
```

### Phase 2: Node Pool Upgrades (Sequential)

**2A. General-Purpose Pool**
```bash
# Upgrade general-purpose pool first (lowest risk)
gcloud container node-pools upgrade general-purpose-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33

# Monitor progress
watch 'kubectl get nodes -o wide -l cloud.google.com/gke-nodepool=general-purpose-pool'
```

**2B. GPU Pool** 
```bash
# Pause ML inference traffic if possible during this phase
gcloud container node-pools upgrade gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33

# Monitor GPU node readiness and driver installation
kubectl get nodes -l cloud.google.com/gke-nodepool=gpu-pool
kubectl describe nodes -l cloud.google.com/gke-nodepool=gpu-pool | grep nvidia
```

**2C. High-Memory Pool (Postgres)**
```bash
# Final pool - database workload
gcloud container node-pools upgrade high-memory-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33

# Monitor Postgres pods during upgrade
kubectl get pods -n postgres-namespace -w
kubectl get statefulsets -n postgres-namespace
```

## Critical Risk Mitigations

### Database Protection
- **Before upgrade:** Take application-level Postgres backup via your operator's backup mechanism
- **During upgrade:** Monitor Postgres connection pooling and failover behavior  
- **PDB Configuration:** Ensure `minAvailable: 1` on Postgres StatefulSets to prevent quorum loss

### GPU Workload Protection  
- **Staging validation required:** Deploy representative ML models on GKE 1.33 staging cluster first
- **Driver compatibility:** GKE 1.33 may ship different GPU drivers - validate CUDA version compatibility
- **Inference service continuity:** Consider blue-green deployment if inference SLAs are strict

### Resource Constraints
- **Peak capacity planning:** Schedule upgrades during off-peak hours when resource demand is lower
- **Quota monitoring:** Ensure sufficient CPU/memory quota for surge nodes in general-purpose pool
- **GPU reservation:** Confirm current GPU reservation status before attempting any surge upgrades

## Maintenance Controls

```bash
# Recommended maintenance window (Saturday 2-6 AM PT)
gcloud container clusters update CLUSTER_NAME \
  --zone us-central1-a \
  --maintenance-window-start "2024-01-06T10:00:00Z" \
  --maintenance-window-end "2024-01-06T14:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Optional: Apply "no upgrades" exclusion if you need to defer auto-upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "manual-upgrade-control" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-01-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Post-Upgrade Validation

```bash
# Verify all components at target version
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="table(currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check workload health
kubectl get deployments -A
kubectl get statefulsets -A  
kubectl get pods -A | grep -v Running | grep -v Completed

# Test ML inference endpoints
curl -X POST https://your-inference-endpoint/predict

# Verify Postgres connectivity
kubectl exec -it postgres-pod -- psql -c "SELECT version();"
```

## Troubleshooting Quick Reference

**If upgrade stalls:**
1. **Check PDBs:** `kubectl get pdb -A` - look for ALLOWED DISRUPTIONS = 0
2. **Check resource constraints:** `kubectl get pods -A | grep Pending`
3. **GPU-specific:** Verify GPU reservation hasn't been exceeded
4. **Database-specific:** Check if Postgres operator is blocking pod eviction

**Rollback Path:**
- Control plane minor version rollback requires GKE support
- Node pools can be rolled back by creating new pools at 1.32 and migrating workloads
- Always contact GKE support for guidance on rollback scenarios

## Timeline Estimate
- **Control Plane:** 15-20 minutes
- **General-Purpose Pool:** 1-2 hours (depends on pool size)  
- **GPU Pool:** 2-3 hours (slower due to maxUnavailable=1 + driver installation)
- **High-Memory Pool:** 1-2 hours (conservative pace for database safety)
- **Total Duration:** 4-7 hours

**Recommendation:** Plan for a full weekend maintenance window to accommodate any unexpected issues, especially with the GPU and database components.