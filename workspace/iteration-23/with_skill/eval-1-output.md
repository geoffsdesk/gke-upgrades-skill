# GKE Upgrade Plan: Regular Channel 1.32 → 1.33

## Overview
- **Cluster**: Standard GKE cluster (us-central1-a)
- **Current version**: 1.32
- **Target version**: 1.33
- **Release channel**: Regular
- **Timeline**: Before end of quarter

## Version Compatibility Assessment

**✅ Path Analysis:**
- Sequential upgrade path: 1.32 → 1.33 (single minor version jump)
- Control plane upgrade first, then node pools
- Node pools can use skip-level upgrade (all pools 1.32 → 1.33 in single jump)

**Pre-flight Checks:**
```bash
# Verify 1.33 availability in Regular channel
gcloud container get-server-config --zone us-central1-a \
  --format="yaml(channels.REGULAR)"

# Check for deprecated API usage (most common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Also check GKE deprecation insights
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=us-central1-a \
    --project=PROJECT_ID
```

## Node Pool Upgrade Strategy

### 1. General-Purpose Pool
**Strategy**: Surge upgrade
- **Settings**: `maxSurge=5%` of pool size (minimum 1), `maxUnavailable=0`
- **Rationale**: Zero-downtime rolling replacement for stateless workloads

### 2. High-Memory Pool (Postgres)
**Strategy**: Conservative surge upgrade
- **Settings**: `maxSurge=1, maxUnavailable=0`
- **Rationale**: One-at-a-time replacement to protect database quorum
- **Special considerations**: 
  - Verify PDBs are configured on Postgres operator StatefulSets
  - Take application-level backup before node pool upgrade
  - Monitor Postgres cluster health during upgrade

### 3. GPU Pool (ML Inference)
**Strategy**: Autoscaled blue-green upgrade (recommended for inference)
- **Rationale**: Avoids inference latency spikes from pod restarts during surge drain
- **Alternative**: If autoscaled blue-green unavailable, use `maxSurge=0, maxUnavailable=1` (assumes fixed GPU reservation with no surge capacity)
- **GPU-specific checks**:
  - Verify target GKE 1.33 GPU driver compatibility in staging first
  - Test inference workloads on 1.33 before production upgrade

## Upgrade Sequence & Timeline

### Week 1: Preparation
- [ ] Run pre-flight compatibility checks
- [ ] Configure PDBs for critical workloads (Postgres, inference services)
- [ ] Test GPU driver compatibility on 1.33 in staging cluster
- [ ] Schedule maintenance window (suggest Saturday 2-6 AM)

### Week 2: Control Plane Upgrade
```bash
# Control plane upgrade (10-15 minutes)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-central1-a \
  --master \
  --cluster-version 1.33.0-gke.PATCH_VERSION
```

### Week 3: Node Pool Upgrades
**Order**: General → High-memory → GPU (lowest to highest risk)

```bash
# 1. General-purpose pool
gcloud container node-pools update general-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade general-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33.0-gke.PATCH_VERSION

# 2. High-memory pool (Postgres)
gcloud container node-pools update high-memory-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade high-memory-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33.0-gke.PATCH_VERSION

# 3. GPU pool (autoscaled blue-green preferred)
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --enable-autoscaling \
  --total-min-nodes MIN --total-max-nodes MAX \
  --strategy=AUTOSCALED_BLUE_GREEN \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25

gcloud container node-pools upgrade gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33.0-gke.PATCH_VERSION
```

## Maintenance Controls

**Maintenance Window** (recommended):
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone us-central1-a \
  --maintenance-window-start "2024-12-07T02:00:00Z" \
  --maintenance-window-end "2024-12-07T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Optional**: If you need to defer auto-upgrades while planning:
```bash
# Temporary "no minor or node upgrades" exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "q4-planning" \
  --add-maintenance-exclusion-start-time "2024-12-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-15T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

## Postgres-Specific Preparations

```bash
# Verify PDBs exist for Postgres StatefulSets
kubectl get pdb -A | grep postgres

# If missing, create PDB (example for 3-replica setup):
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: postgres-pdb
  namespace: postgres-namespace
spec:
  minAvailable: 2  # Maintains quorum during drain
  selector:
    matchLabels:
      app: postgres
```

**Pre-upgrade Postgres backup:**
```bash
# Application-level backup before node upgrades
kubectl exec -it postgres-primary-pod -n postgres-namespace -- \
  pg_dump -U postgres -d production > postgres-backup-pre-upgrade.sql
```

## GPU Pool Considerations

**Driver Compatibility Check** (run in staging first):
```bash
# Deploy test inference workload on 1.33
kubectl run gpu-test --image=tensorflow/tensorflow:latest-gpu \
  --restart=Never --rm -it -- python -c "import tensorflow as tf; print(tf.config.list_physical_devices('GPU'))"
```

**If autoscaled blue-green unavailable**, use drain-first strategy:
```bash
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

## Validation Commands

**After each upgrade phase:**
```bash
# Control plane version
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="value(currentMasterVersion)"

# Node versions
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion

# Postgres health
kubectl get pods -n postgres-namespace -l app=postgres

# GPU node readiness
kubectl get nodes -l accelerator=nvidia-tesla-* -o wide

# ML inference health check
curl -X POST http://INFERENCE_SERVICE_IP/predict -d '{"test": "data"}'
```

## Timeline Summary

- **Week 1**: Pre-flight checks, PDB setup, GPU testing
- **Week 2**: Control plane upgrade (maintenance window)
- **Week 3**: Node pool upgrades (general → postgres → GPU)
- **Week 4**: Final validation, documentation

This plan gets you to 1.33 well before end of quarter while minimizing risk to your database and inference workloads. The staggered approach allows validation at each step.