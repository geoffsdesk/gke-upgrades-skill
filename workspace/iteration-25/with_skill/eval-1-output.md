# GKE Upgrade Plan: Standard Cluster 1.32 → 1.33

## Executive Summary

**Cluster:** Standard GKE cluster  
**Channel:** Regular  
**Current Version:** 1.32  
**Target Version:** 1.33  
**Location:** us-central1-a (zonal)  
**Timeline:** Before end of quarter  

**Recommended Strategy:** Sequential control plane upgrade followed by tailored node pool upgrades using different strategies per pool type.

## Version Compatibility Assessment

✅ **Target version availability:** 1.33 is available in Regular channel  
✅ **Version skew:** All node pools can upgrade directly to 1.33 (within 2 minor version limit)  
⚠️ **Deprecated API check required:** Run pre-flight validation  
📋 **Breaking changes:** Review GKE 1.33 release notes for Postgres operator and ML framework compatibility  

## Upgrade Path & Strategy

### Phase 1: Control plane upgrade (1.32 → 1.33)
**Duration:** ~10-15 minutes  
**Impact:** Brief API unavailability (zonal cluster), workloads continue running  
**Strategy:** Direct upgrade to 1.33

### Phase 2: Node pool upgrades (tailored per workload)

| Pool Type | Strategy | Reasoning | Settings |
|-----------|----------|-----------|----------|
| **General-purpose** | Surge upgrade | Stateless workloads, cost-efficient | `maxSurge=5%`, `maxUnavailable=0` |
| **High-memory (Postgres)** | Surge upgrade (conservative) | Database workloads need PDB protection | `maxSurge=1`, `maxUnavailable=0` |
| **GPU (ML inference)** | Autoscaled blue-green | Avoid inference latency spikes, no surge capacity assumed | Autoscaled rollout policy |

## Pre-Upgrade Checklist

### Compatibility Validation
- [ ] **Deprecated API check:**
  ```bash
  kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
  ```
- [ ] **GKE recommender insights:**
  ```bash
  gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=us-central1-a \
    --project=PROJECT_ID \
    --filter="category.category:RELIABILITY"
  ```
- [ ] **Postgres operator compatibility:** Verify operator supports Kubernetes 1.33
- [ ] **ML framework compatibility:** Test inference workloads against 1.33 in staging
- [ ] **GPU driver compatibility:** Confirm target GKE version's GPU driver works with your models

### Workload Readiness
- [ ] **PDBs configured for Postgres:** 
  ```bash
  kubectl get pdb -n postgres-namespace
  # Ensure minAvailable allows 1 pod to drain while maintaining quorum
  ```
- [ ] **No bare pods:** `kubectl get pods -A -o json | jq '.items[] | select(.metadata.ownerReferences | length == 0)'`
- [ ] **Postgres backup completed:** Run application-level backup via your operator
- [ ] **ML model checkpoint:** Ensure inference services can reload models post-restart
- [ ] **GPU pool capacity:** Verify no ongoing training jobs that would be disrupted

### Infrastructure Readiness
- [ ] **Compute quota:** Check sufficient quota for general-purpose surge (estimate +5% nodes temporarily)
- [ ] **GPU quota assessment:** Autoscaled blue-green will create replacement GPU nodes - verify capacity
- [ ] **Maintenance window configured:** Set off-peak hours for node pool upgrades
- [ ] **Monitoring baseline:** Capture current error rates, latency, and throughput

## Upgrade Runbook

### Phase 1: Control Plane Upgrade

```bash
# Pre-flight validation
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Upgrade control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-central1-a \
  --master \
  --cluster-version 1.33

# Verify (wait ~10-15 min)
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="value(currentMasterVersion)"

kubectl get pods -n kube-system
```

### Phase 2A: General-Purpose Pool Upgrade

```bash
# Configure surge settings
gcloud container node-pools update general-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# Upgrade
gcloud container node-pools upgrade general-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

### Phase 2B: High-Memory Pool (Postgres) Upgrade

```bash
# Conservative surge settings for database workloads
gcloud container node-pools update high-memory-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade
gcloud container node-pools upgrade high-memory-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33

# Monitor Postgres health during upgrade
kubectl get statefulsets -n postgres-namespace -w
```

### Phase 2C: GPU Pool (ML Inference) Upgrade

```bash
# Enable autoscaling if not already enabled
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --enable-autoscaling \
  --total-min-nodes MIN_NODES \
  --total-max-nodes MAX_NODES

# Configure autoscaled blue-green upgrade
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --strategy=AUTOSCALED_BLUE_GREEN \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Upgrade
gcloud container node-pools upgrade gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33

# Monitor inference service availability
kubectl get pods -n ml-namespace -l app=inference -w
```

## Maintenance Window Configuration

**Recommended schedule:** Weekend off-peak hours to minimize business impact

```bash
# Set recurring weekend maintenance window
gcloud container clusters update CLUSTER_NAME \
  --zone us-central1-a \
  --maintenance-window-start "2024-01-13T02:00:00Z" \
  --maintenance-window-end "2024-01-13T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Risk Mitigation

### High-Memory Pool (Postgres)
- **PDB Protection:** Ensure PDB allows exactly 1 replica to drain while maintaining database quorum
- **Backup Strategy:** Complete application-level backup before upgrade
- **Rollback Plan:** If issues arise, create new pool at 1.32 and migrate workloads

### GPU Pool (ML Inference)
- **Zero-downtime strategy:** Autoscaled blue-green keeps old pool serving while new pool scales up
- **Model compatibility:** Test inference workloads in staging with target GKE version first
- **Capacity planning:** Ensure sufficient GPU quota for replacement nodes during upgrade

### General Mitigations
- **Admission webhook compatibility:** Verify all webhooks (cert-manager, policy controllers) support Kubernetes 1.33
- **Monitoring:** Set up alerts for upgrade progress and service health
- **Communication:** Notify stakeholders of maintenance window

## Post-Upgrade Validation

```bash
# Verify all components at target version
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Check all nodes healthy
kubectl get nodes

# Validate workload health
kubectl get pods -A | grep -v Running | grep -v Completed
kubectl get statefulsets -A  # Postgres health
kubectl get deployments -A   # ML inference health

# Application-specific validation
# - Postgres: Run connection and query tests
# - ML inference: Send test requests, verify latency/accuracy
# - General workloads: Run smoke tests
```

## Troubleshooting Quick Reference

| Issue | Diagnosis | Fix |
|-------|-----------|-----|
| PDB blocking drain | `kubectl get pdb -A` | Temporarily patch `maxUnavailable: "100%"` |
| Pods pending | `kubectl get events --field-selector reason=FailedScheduling` | Scale down non-critical workloads |
| GPU inference latency spike | Monitor during blue-green transition | Normal during pool swap, should resolve |
| Postgres connection errors | Check StatefulSet status | Verify PDB allows orderly failover |

## Timeline Estimate

- **Phase 1 (Control plane):** 15 minutes
- **Phase 2A (General pool):** 30-60 minutes (depends on pool size)  
- **Phase 2B (High-memory pool):** 45-90 minutes (conservative settings)
- **Phase 2C (GPU pool):** 60-120 minutes (blue-green + autoscaling)
- **Validation:** 30 minutes

**Total estimated time:** 3-5 hours

**Recommendation:** Execute during a weekend maintenance window with your on-call team available.

---

**Next Steps:**
1. Review this plan with your database and ML teams
2. Test the upgrade path in a staging environment
3. Schedule the maintenance window
4. Execute pre-upgrade checklist items
5. Run the upgrade during your maintenance window