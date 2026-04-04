# GKE Upgrade Plan: 1.32 → 1.33

**Cluster:** Standard GKE cluster  
**Channel:** Regular  
**Current Version:** 1.32  
**Target Version:** 1.33  
**Region:** us-central1-a  
**Timeline:** Before end of quarter

## Executive Summary

This is a **single minor version upgrade** from 1.32 → 1.33. The upgrade follows the required sequence: control plane first, then node pools. Special attention needed for the GPU inference pool (requires careful strategy selection) and Postgres operator compatibility.

## Version Compatibility Assessment

### ✅ Version Availability
- Target version 1.33 should be available in Regular channel
- Verify current availability: `gcloud container get-server-config --zone us-central1-a --format="yaml(channels.regular)"`

### ⚠️ Critical Compatibility Checks
1. **Postgres Operator:** Verify your Postgres operator version supports Kubernetes 1.33. Most operators lag behind K8s releases by 2-4 weeks.
2. **GPU Driver:** GKE will auto-install drivers matching 1.33. Confirm inference workloads are compatible with the target driver/CUDA version.
3. **Deprecated APIs:** Check for deprecated API usage that may break in 1.33:
   ```bash
   kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
   ```

## Upgrade Strategy by Node Pool

### 1. General-Purpose Pool
**Strategy:** Surge upgrade with moderate parallelism
- **Settings:** `maxSurge=2, maxUnavailable=0`
- **Rationale:** Zero-downtime rolling replacement, moderate speed

### 2. High-Memory Postgres Pool  
**Strategy:** Conservative surge upgrade
- **Settings:** `maxSurge=1, maxUnavailable=0`
- **Rationale:** Database workloads need careful one-at-a-time replacement. PDBs will protect quorum during drain.

### 3. GPU Inference Pool
**Strategy:** **Autoscaled blue-green upgrade** (recommended)
- **Rationale:** 
  - GPU inference is latency-sensitive — surge upgrades cause pod restarts and inference downtime
  - GPU VMs don't support live migration — every upgrade requires pod restart
  - Autoscaled blue-green keeps old pool serving while new pool warms up
  - More cost-effective than standard blue-green (scales down old pool as workloads migrate)

**Alternative if autoscaled blue-green unavailable:** `maxSurge=0, maxUnavailable=1` (assumes fixed GPU reservation with no surge capacity)

## Upgrade Sequence

### Phase 1: Pre-Flight Validation (1 hour)
```bash
# Check current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Verify 1.33 available in Regular channel
gcloud container get-server-config --zone us-central1-a \
  --format="yaml(channels.regular)"

# Check deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Verify cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed
```

### Phase 2: Control Plane Upgrade (15-20 minutes)
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-central1-a \
  --master \
  --cluster-version 1.33

# Monitor completion
watch 'gcloud container clusters describe CLUSTER_NAME --zone us-central1-a --format="value(currentMasterVersion)"'
```

**Validation:**
- Control plane version shows 1.33
- `kubectl` commands work normally  
- System pods in kube-system are healthy

### Phase 3: Node Pool Upgrades (Sequential)

#### Step 1: General-Purpose Pool (30-60 minutes)
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
```

#### Step 2: High-Memory Postgres Pool (45-90 minutes)
```bash
# Conservative settings for database workloads
gcloud container node-pools update postgres-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade
gcloud container node-pools upgrade postgres-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33
```

#### Step 3: GPU Inference Pool (60-120 minutes)
```bash
# Configure autoscaled blue-green upgrade
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --enable-autoscaling \
  --total-min-nodes MIN --total-max-nodes MAX \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Upgrade
gcloud container node-pools upgrade gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33
```

**Alternative for fixed GPU reservations:**
```bash
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist - 1.32 → 1.33 Upgrade
- [ ] Cluster: CLUSTER_NAME | Mode: Standard | Channel: Regular
- [ ] Current version: 1.32 | Target version: 1.33

Compatibility
- [ ] Target version 1.33 available in Regular channel
- [ ] Postgres operator compatibility with K8s 1.33 verified
- [ ] GPU driver/CUDA compatibility confirmed for inference workloads
- [ ] No deprecated API usage detected
- [ ] GKE release notes reviewed for 1.32 → 1.33 breaking changes

Workload Readiness
- [ ] PDBs configured for Postgres StatefulSets (minAvailable: 2 for HA setup)
- [ ] GPU inference pods have appropriate resource requests/limits
- [ ] No bare pods — all managed by Deployments/StatefulSets
- [ ] Application-level backup of Postgres data completed
- [ ] Inference model warming strategy documented

Infrastructure
- [ ] General pool: maxSurge=2, maxUnavailable=0
- [ ] Postgres pool: maxSurge=1, maxUnavailable=0  
- [ ] GPU pool: Autoscaled blue-green configured OR maxSurge=0/maxUnavailable=1
- [ ] Maintenance window set for off-peak hours
- [ ] Sufficient compute quota for surge nodes (general + postgres pools)

Ops Readiness
- [ ] Monitoring baselines captured (inference latency, DB query performance)
- [ ] Upgrade window communicated to stakeholders
- [ ] Rollback plan documented
- [ ] On-call team available during upgrade window
```

## Risk Assessment & Mitigation

### High Risk: GPU Inference Pool
**Risk:** Inference downtime during pod restarts  
**Mitigation:** Autoscaled blue-green keeps old pool serving during transition

### Medium Risk: Postgres Operator Compatibility  
**Risk:** Operator may not support K8s 1.33 immediately  
**Mitigation:** Test in staging first, have rollback plan ready

### Low Risk: General Workloads
**Risk:** Brief pod restarts during rolling upgrade  
**Mitigation:** Surge settings ensure zero-downtime deployment updates

## Rollback Plan

**Control Plane:** Requires GKE support involvement for minor version downgrades. Apply maintenance exclusion first to prevent auto-upgrades back.

**Node Pools:** Create new pools at 1.32, migrate workloads:
```bash
# Create rollback pool
gcloud container node-pools create POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.32.X \
  --num-nodes NUM_NODES

# Cordon upgraded pool and migrate
kubectl cordon -l cloud.google.com/gke-nodepool=UPGRADED_POOL
```

## Timeline Estimate

| Phase | Duration | Notes |
|-------|----------|-------|
| Pre-flight checks | 1 hour | API compatibility, cluster health |
| Control plane upgrade | 15-20 min | Zonal cluster downtime |
| General pool upgrade | 30-60 min | Depends on pool size |
| Postgres pool upgrade | 45-90 min | Conservative one-at-a-time |
| GPU pool upgrade | 60-120 min | Blue-green transition time |
| **Total** | **3-5 hours** | Schedule 6-hour maintenance window |

## Success Criteria

- [ ] All components at version 1.33
- [ ] All nodes showing Ready status
- [ ] Postgres queries performing within baseline
- [ ] GPU inference latency within 5% of baseline  
- [ ] No CrashLoopBackOff or Pending pods
- [ ] Application health checks passing

## Next Steps

1. **Schedule upgrade window** during off-peak hours (weekend recommended)
2. **Test Postgres operator compatibility** in staging environment
3. **Validate GPU inference** with target 1.33 drivers in dev cluster
4. **Execute pre-flight checklist** 24 hours before upgrade
5. **Run upgrade following the phased approach** above

This plan prioritizes workload stability while meeting your end-of-quarter deadline. The sequential node pool upgrade approach minimizes blast radius and allows validation between phases.