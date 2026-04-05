# GKE Upgrade Plan: 1.32 → 1.33

**Cluster:** Standard GKE, Regular channel, us-central1-a  
**Current:** 1.32 → **Target:** 1.33  
**Timeline:** Before end of quarter  

## Executive Summary

This is a **minor version upgrade** requiring sequential control plane upgrade followed by node pool upgrades. The Regular release channel should have 1.33 available as the auto-upgrade target. We'll use a **staged approach** with the general-purpose pool first (lowest risk), then high-memory pool, and GPU pool last due to inference sensitivity.

## Pre-Upgrade Assessment

### Version Compatibility Check
```bash
# Verify 1.33 availability in Regular channel
gcloud container get-server-config --zone us-central1-a \
  --format="yaml(channels.REGULAR.validVersions)"

# Check current auto-upgrade target
gcloud container clusters get-upgrade-info CLUSTER_NAME --region us-central1-a
```

### Breaking Changes Review
**Critical items between 1.32 → 1.33:**
- Review [GKE 1.33 release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) for API deprecations
- Check deprecated API usage:
```bash
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Also check GKE deprecation insights
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=us-central1-a \
    --project=PROJECT_ID \
    --filter="category.category:RELIABILITY"
```

## Upgrade Strategy by Node Pool

### 1. General-Purpose Pool (Lowest Risk)
**Strategy:** Surge upgrade with moderate parallelism
```bash
gcloud container node-pools update general-purpose-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```
- **Rationale:** Stateless workloads can tolerate brief disruption
- **Timeline:** ~1-2 hours depending on pool size

### 2. High-Memory Pool (Postgres - Moderate Risk)
**Strategy:** Conservative surge upgrade
```bash
gcloud container node-pools update high-memory-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```
- **Rationale:** Database workloads need careful handling
- **Prerequisites:** 
  - Verify Postgres operator compatibility with K8s 1.33
  - Ensure PDBs are configured (recommend `minAvailable: 1` for HA setups)
  - Take application-level backup before upgrade
- **Timeline:** ~2-3 hours

### 3. GPU Pool (Highest Risk - ML Inference)
**Strategy:** Autoscaled blue-green (recommended) OR conservative surge
```bash
# Option A: Autoscaled blue-green (preferred for inference)
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --enable-autoscaling \
  --total-min-nodes MIN --total-max-nodes MAX \
  --strategy AUTOSCALED_BLUE_GREEN \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25

# Option B: Conservative surge (if blue-green not feasible)
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```
- **Rationale:** 
  - **Autoscaled blue-green preferred** - keeps inference serving while new nodes warm up, avoids inference latency spikes
  - **If surge required** - Use `maxSurge=0, maxUnavailable=1` (GPU reservations typically have no surge capacity)
- **Critical checks:**
  - Verify GPU driver compatibility with 1.33 node image
  - Test inference workloads on staging cluster with 1.33 first
  - Confirm GPU reservation has capacity for replacement nodes (blue-green only)
- **Timeline:** ~4-6 hours (blue-green includes soak time)

## Maintenance Window Configuration

**Recommended:** Off-peak weekend window
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone us-central1-a \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-duration 8h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Upgrade Sequence

### Phase 1: Control Plane Upgrade
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-central1-a \
  --master \
  --cluster-version 1.33
```
**Duration:** 10-15 minutes  
**Validation:** CP responsive, system pods healthy

### Phase 2: Node Pool Upgrades (Sequential)
1. **General-purpose pool** → validate → proceed
2. **High-memory pool** → validate Postgres health → proceed  
3. **GPU pool** → validate inference endpoints → complete

**Soak time between pools:** 30 minutes minimum

## Risk Mitigation

### Database Protection (High-Memory Pool)
```bash
# Verify PDB exists
kubectl get pdb -n postgres-namespace

# If missing, create one:
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: postgres-pdb
  namespace: postgres-namespace
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: postgres
EOF
```

### GPU Workload Protection
- **Pre-upgrade:** Create staging GPU node pool with 1.33, test inference models
- **During upgrade:** Monitor inference latency and error rates
- **Rollback plan:** Blue-green allows fast rollback by uncordoning old pool

### Emergency Deferral (if needed)
If critical issues are discovered before upgrade window:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "emergency-defer" \
  --add-maintenance-exclusion-start "2024-01-05T00:00:00Z" \
  --add-maintenance-exclusion-end "2024-01-12T00:00:00Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Pre-Flight Checklist

```
- [ ] 1.33 available in Regular channel verified
- [ ] No deprecated API usage confirmed  
- [ ] Postgres operator 1.33 compatibility verified
- [ ] GPU driver compatibility tested in staging
- [ ] Application-level Postgres backup completed
- [ ] PDBs configured for database workloads
- [ ] Inference health checks and rollback procedures ready
- [ ] Monitoring and alerting active
- [ ] Stakeholder notification sent
- [ ] Maintenance window scheduled
```

## Timeline Estimate

| Phase | Duration | Cumulative |
|-------|----------|------------|
| Control plane | 15 min | 15 min |
| General-purpose pool | 1.5 hours | 1h 45m |
| High-memory pool | 2.5 hours | 4h 15m |
| GPU pool (blue-green) | 4 hours | 8h 15m |
| **Total window** | **~8.5 hours** | **Full Saturday** |

## Success Criteria

- [ ] All pools at 1.33
- [ ] No CrashLoopBackOff pods
- [ ] Postgres connections stable
- [ ] Inference latency within baseline
- [ ] No deprecated API warnings

This plan prioritizes **inference availability** through autoscaled blue-green for the GPU pool while using efficient surge upgrades for stateless workloads. The sequential approach allows validation at each stage with rollback options.