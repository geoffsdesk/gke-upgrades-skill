# GKE Upgrade Plan: 1.32 → 1.33

**Cluster Details:**
- Mode: Standard GKE
- Channel: Regular 
- Current: 1.32
- Target: 1.33
- Zone: us-central1-a
- Node pools: general-purpose, high-memory (Postgres), GPU (ML inference)

## Executive Summary

This is a **minor version upgrade** requiring careful sequencing: control plane first, then node pools. The GPU pool requires special handling due to likely surge capacity constraints, and the Postgres pool needs PDB protection during drain operations.

**Recommended timeline:** 2-3 weeks
- Week 1: Staging validation, PDB audit, surge capacity verification  
- Week 2: Control plane upgrade + general-purpose pool
- Week 3: High-memory and GPU pools (off-peak hours)

## Version Compatibility Check

✅ **Target version availability:** Verify 1.33 is available in Regular channel:
```bash
gcloud container get-server-config --zone us-central1-a \
  --format="yaml(channels.REGULAR)"
```

✅ **Version skew:** 1.32→1.33 is a standard single minor version upgrade - no skew issues

⚠️ **Breaking changes:** Review [GKE 1.33 release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) for:
- Deprecated APIs (most common upgrade failure)
- Postgres operator compatibility with K8s 1.33
- GPU driver version changes

## Pre-Upgrade Validation

### Deprecated API Check
```bash
# Quick check
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Comprehensive check via GKE recommender
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=us-central1-a \
    --project=PROJECT_ID
```

### Workload Readiness Audit
```bash
# Check for bare pods (won't be rescheduled)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Verify PDBs for critical workloads
kubectl get pdb -A
```

## Upgrade Strategy by Node Pool

### 1. General-Purpose Pool
**Strategy:** Surge upgrade
**Settings:** `maxSurge=5%` (minimum 1), `maxUnavailable=0`
**Rationale:** Zero-downtime rolling replacement for stateless workloads

### 2. High-Memory Pool (Postgres)
**Strategy:** Conservative surge upgrade  
**Settings:** `maxSurge=1`, `maxUnavailable=0`
**Rationale:** Database workloads need careful PDB protection and controlled drain

**Critical:** Verify Postgres operator PDBs are configured but not overly restrictive (allow at least 1 disruption)

### 3. GPU Pool (ML Inference)
**Strategy:** Drain-first upgrade (assume no surge GPU capacity)
**Settings:** `maxSurge=0`, `maxUnavailable=1`
**Rationale:** GPU reservations typically have no surge capacity available

⚠️ **GPU Considerations:**
- Verify GPU driver compatibility with GKE 1.33 node image
- GPU VMs don't support live migration - every upgrade requires pod restart
- Test inference workloads in staging first

## Upgrade Sequence

### Phase 1: Control Plane Upgrade
```bash
# Set maintenance exclusion first (optional - for timing control)
gcloud container clusters update CLUSTER_NAME \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "manual-upgrade-window" \
  --add-maintenance-exclusion-start-time 2024-XX-XXTXX:XX:XXZ \
  --add-maintenance-exclusion-end-time 2024-XX-XXTXX:XX:XXZ \
  --add-maintenance-exclusion-scope no_upgrades

# Upgrade control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-central1-a \
  --master \
  --cluster-version 1.33.X-gke.XXXX
```

**Validation:** Wait 10-15 minutes, then verify:
```bash
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="value(currentMasterVersion)"
kubectl get pods -n kube-system
```

### Phase 2: General-Purpose Pool
```bash
# Configure surge settings
gcloud container node-pools update general-purpose-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade
gcloud container node-pools upgrade general-purpose-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33.X-gke.XXXX
```

### Phase 3: High-Memory Pool (Postgres)
```bash
# Configure conservative settings
gcloud container node-pools update high-memory-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Verify Postgres PDBs allow disruption
kubectl get pdb -n postgres-namespace -o yaml

# Upgrade during maintenance window
gcloud container node-pools upgrade high-memory-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33.X-gke.XXXX
```

### Phase 4: GPU Pool (Off-Peak)
```bash
# Configure drain-first settings (no surge capacity assumed)
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

# Upgrade during off-peak hours
gcloud container node-pools upgrade gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33.X-gke.XXXX
```

## Maintenance Windows & Timing

**Recommended schedule:**
- **Control plane + general pool:** Business hours (easier rollback)
- **Database pool:** Maintenance window (2AM-6AM weekends)  
- **GPU pool:** Off-peak hours when inference load is lowest

```bash
# Configure recurring maintenance window
gcloud container clusters update CLUSTER_NAME \
  --zone us-central1-a \
  --maintenance-window-start 2024-XX-XXTXX:XX:XXZ \
  --maintenance-window-end 2024-XX-XXTXX:XX:XXZ \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```

## Risk Mitigation

### High-Risk Areas
1. **GPU driver compatibility** - Test ML inference workloads in staging
2. **Postgres operator** - Verify operator supports K8s 1.33  
3. **Deprecated APIs** - Most common cause of upgrade failures

### Rollback Strategy
- **Control plane:** Requires GKE support for minor version downgrade
- **Node pools:** Can be rolled back during upgrade or by creating new pool at 1.32
- **Recommendation:** Fix-forward rather than rollback for minor versions

## Monitoring & Validation

### During Upgrade
```bash
# Monitor node upgrade progress  
watch 'kubectl get nodes -o wide'

# Check for stuck operations
gcloud container operations list --cluster CLUSTER_NAME --zone us-central1-a
```

### Post-Upgrade Health Checks
```bash
# Verify all components at target version
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Workload health
kubectl get pods -A | grep -v Running | grep -v Completed
kubectl get deployments -A
kubectl get statefulsets -A

# ML inference smoke test
# Run sample inference request against GPU workloads
```

## Timeline & Checkpoints

**Week 1 - Preparation**
- [ ] Version availability confirmed in Regular channel
- [ ] Deprecated API usage audit completed  
- [ ] Postgres operator 1.33 compatibility verified
- [ ] GPU driver compatibility tested in staging
- [ ] PDB audit completed
- [ ] Maintenance windows configured

**Week 2 - Control Plane & General Pool**  
- [ ] Control plane upgraded to 1.33
- [ ] General-purpose pool upgraded
- [ ] Smoke tests passing
- [ ] Baseline metrics captured

**Week 3 - Database & GPU Pools**
- [ ] High-memory pool upgraded (weekend maintenance window)
- [ ] Postgres operator health verified
- [ ] GPU pool upgraded (off-peak)
- [ ] ML inference validation completed
- [ ] All pools at 1.33, cluster fully upgraded

This plan balances upgrade speed with risk management, using appropriate strategies for each workload type while maintaining service availability.