# GKE Upgrade Plan: 1.32 → 1.33

## Overview
**Cluster:** Standard GKE cluster  
**Channel:** Regular  
**Current Version:** 1.32  
**Target Version:** 1.33  
**Location:** us-central1-a (zonal)  
**Timeline:** Before end of quarter  

## Version Compatibility Assessment

✅ **Target version availability:** 1.33 should be available in Regular channel (check current status with pre-flight commands below)  
⚠️ **Version skew:** Verify all node pools are within 2 minor versions of control plane  
🔍 **Breaking changes:** Review GKE release notes between 1.32 → 1.33 for deprecated APIs and feature changes  

## Upgrade Strategy

### Sequential Upgrade Approach
1. **Control plane first:** 1.32 → 1.33 (required order)
2. **Node pools in order of risk:** General → High-memory (Postgres) → GPU (highest risk)

### Node Pool Strategies

| Pool | Strategy | Rationale |
|------|----------|-----------|
| **General-purpose** | Surge: `maxSurge=5%, maxUnavailable=0` | Stateless workloads, fast parallel upgrade |
| **High-memory (Postgres)** | Surge: `maxSurge=1, maxUnavailable=0` | Stateful database, conservative one-at-a-time |
| **GPU (inference)** | Autoscaled blue-green | Avoids inference latency spikes, assuming capacity available |

**GPU Strategy Note:** If you have fixed GPU reservations with no surge capacity, use `maxSurge=0, maxUnavailable=1` instead.

## Pre-Upgrade Requirements

### Critical Checks
- [ ] **Deprecated API scan:** Check GKE deprecation insights dashboard and run kubectl deprecated API check
- [ ] **Postgres operator compatibility:** Verify your Postgres operator version supports Kubernetes 1.33
- [ ] **GPU driver compatibility:** Confirm target GKE 1.33 GPU driver version works with your ML inference workloads
- [ ] **PDB configuration:** Review PodDisruptionBudgets for Postgres StatefulSets (recommend `minAvailable: 1` or 50%)

### Infrastructure Readiness
- [ ] **Compute quota:** Verify sufficient quota for surge nodes (general + high-memory pools)
- [ ] **GPU capacity:** Confirm available capacity for blue-green upgrade (2x GPU pool size temporarily)
- [ ] **Maintenance window:** Configure upgrade window during off-peak hours
- [ ] **Baseline metrics:** Capture current performance baselines for validation

## Detailed Upgrade Steps

### Phase 1: Control Plane Upgrade (10-15 minutes)
```bash
# Pre-flight check
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="value(currentMasterVersion)"

# Check 1.33 availability in Regular channel
gcloud container get-server-config --zone us-central1-a \
  --format="yaml(channels.REGULAR)"

# Upgrade control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-central1-a \
  --master \
  --cluster-version 1.33

# Validate
kubectl get pods -n kube-system
```

**Downtime:** 3-5 minutes of API unavailability (zonal cluster). Workloads continue running.

### Phase 2: General-Purpose Pool (20-30 minutes)
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

# Monitor
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=general-pool'
```

### Phase 3: High-Memory Pool (Postgres) (45-60 minutes)
```bash
# Conservative settings for database workloads
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
```

**Critical:** Monitor Postgres pod rescheduling and connection recovery. PVs will reattach automatically.

### Phase 4: GPU Pool (Inference) (30-45 minutes)
```bash
# Option A: Autoscaled blue-green (if capacity available)
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --enable-autoscaling \
  --total-min-nodes 1 --total-max-nodes MAX_CAPACITY \
  --strategy BLUE_GREEN \
  --node-pool-soak-duration 1800s

# Option B: If fixed GPU reservation with no surge capacity
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

**Critical:** Test inference latency and model loading immediately after GPU nodes come online.

## Staging Validation Plan

**Before production upgrade:**
1. **Create staging GPU node pool** at 1.33 to test driver compatibility
2. **Deploy representative ML inference workload** to verify model loading and CUDA calls
3. **Run Postgres operator smoke tests** against 1.33 control plane
4. **Validate admission webhooks** don't reject pod creation on 1.33

## Risk Mitigation

### High-Risk Areas
- **GPU driver version change:** GKE 1.33 may install different CUDA drivers
- **Postgres operator compatibility:** Database operators are sensitive to Kubernetes API changes  
- **Inference latency:** GPU node restarts cause brief service interruption
- **Zonal cluster:** Single control plane means API downtime during CP upgrade

### Rollback Strategy
- **Control plane:** Contact GKE support (minor version rollback requires assistance)
- **Node pools:** Create new pools at 1.32, cordon upgraded pools, migrate workloads
- **Emergency:** Apply "no upgrades" maintenance exclusion to prevent auto-upgrades while troubleshooting

## Timeline & Coordination

### Recommended Sequence (2-3 hour window)
```
Hour 1: Control plane + General pool
Hour 2: High-memory pool (with Postgres monitoring)  
Hour 3: GPU pool (with inference testing)
```

### Success Criteria
- [ ] All nodes show Ready status with 1.33
- [ ] Postgres connections restored and queries responding
- [ ] ML inference latency within 10% of pre-upgrade baseline
- [ ] No CrashLoopBackOff pods after 30 minutes
- [ ] Application smoke tests passing

## Post-Upgrade Validation

```bash
# Cluster health
kubectl get nodes
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded

# Workload-specific checks
kubectl get statefulsets -A  # Postgres replicas
kubectl logs -l app=your-inference-service --tail=50  # GPU workload logs
kubectl top pods -A | grep -E "(postgres|gpu)"  # Resource usage
```

Would you like me to customize any part of this plan based on your specific Postgres operator (CloudNativePG, Zalando, etc.) or GPU instance types?