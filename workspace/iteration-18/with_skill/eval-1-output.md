# GKE Upgrade Plan: Regular Channel 1.32 → 1.33

**Cluster Details:**
- Mode: Standard
- Channel: Regular
- Current version: 1.32
- Target version: 1.33
- Zone: us-central1-a
- Pools: general-purpose, high-memory (Postgres), GPU (ML inference)

## Executive Summary

This is a **minor version upgrade** requiring sequential control plane upgrade followed by node pool upgrades. Key considerations:
- Postgres operator compatibility verification required
- GPU pool needs driver validation in staging
- ML inference workloads benefit from autoscaled blue-green strategy
- Estimated total time: 4-6 hours depending on pool sizes

## Version Compatibility & Availability

**✅ Requirements Check:**
- Target version 1.33 should be available in Regular channel (verify with commands below)
- Minor version jump (1.32→1.33) requires sequential upgrade - no skip-level for control plane
- Node pools can upgrade 1.32→1.33 directly once control plane is upgraded
- No version skew issues (nodes will remain within 2 minor versions of control plane)

**⚠️ Critical Validations:**
- **Postgres operator:** Verify your current Postgres operator version supports Kubernetes 1.33
- **GPU drivers:** GKE will auto-install drivers for 1.33 - may change CUDA version
- **ML inference models:** Validate model compatibility with new driver stack in staging

## Upgrade Strategy by Pool

### Control Plane
- **Strategy:** Direct upgrade 1.32→1.33
- **Timing:** ~10-15 minutes downtime for cluster API
- **Impact:** Cannot deploy/modify workloads during upgrade, existing workloads continue running

### General-Purpose Pool
- **Strategy:** Surge upgrade
- **Settings:** `maxSurge=5%` of pool size (minimum 1), `maxUnavailable=0`
- **Rationale:** Zero-downtime rolling replacement for stateless workloads

### High-Memory Pool (Postgres)
- **Strategy:** Conservative surge upgrade  
- **Settings:** `maxSurge=1, maxUnavailable=0`
- **Rationale:** One-at-a-time replacement to protect database quorum
- **Prerequisites:** Verify Postgres operator PDBs are configured correctly

### GPU Pool (ML Inference)
- **Strategy:** Autoscaled blue-green upgrade (recommended)
- **Rationale:** Prevents inference latency spikes during pod restarts. GPU VMs don't support live migration, so every surge upgrade causes service disruption
- **Alternative:** If autoscaled blue-green unavailable, use `maxSurge=0, maxUnavailable=1` (assumes fixed GPU reservation with no surge capacity)

## Pre-Upgrade Checklist

```
Pre-Upgrade Validation
- [ ] Target version 1.33 available in Regular channel
- [ ] Postgres operator version supports Kubernetes 1.33
- [ ] GPU staging cluster tested with 1.33 + new drivers
- [ ] ML models validated on new CUDA version
- [ ] No deprecated API usage detected
- [ ] PDBs configured for Postgres StatefulSets
- [ ] Application-level Postgres backup completed
- [ ] Compute quota sufficient for surge nodes (general + high-memory pools)
- [ ] Maintenance window scheduled (4-6 hour block recommended)
- [ ] On-call team notified
```

## Upgrade Sequence & Commands

### 1. Pre-flight Validation

```bash
# Verify target version availability
gcloud container get-server-config --zone us-central1-a \
  --format="yaml(channels)" | grep -A 10 "regular"

# Check current cluster state
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check for deprecated APIs
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Verify cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed
kubectl get pdb -A
```

### 2. Control Plane Upgrade

```bash
# Upgrade control plane to 1.33
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

### 3. Node Pool Upgrades (Sequential Order)

**Step 3a: General-Purpose Pool**
```bash
# Configure surge settings (adjust pool size percentage)
gcloud container node-pools update general-purpose-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# Upgrade
gcloud container node-pools upgrade general-purpose-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33

# Monitor
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep general'
```

**Step 3b: High-Memory Pool (Postgres)**
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

# Monitor Postgres health during upgrade
kubectl get statefulsets -n postgres-namespace
kubectl logs -f -l app=postgres-operator -n postgres-namespace
```

**Step 3c: GPU Pool (ML Inference)**

*Option A - Autoscaled Blue-Green (Recommended):*
```bash
# Enable autoscaling and configure blue-green
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --enable-autoscaling \
  --total-min-nodes 1 --total-max-nodes MAX_NODES \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Upgrade
gcloud container node-pools upgrade gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33
```

*Option B - Drain-First (if blue-green unavailable):*
```bash
# No surge capacity mode
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

# Upgrade
gcloud container node-pools upgrade gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33
```

### 4. Post-Upgrade Validation

```bash
# Verify all components at 1.33
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="table(currentMasterVersion, nodePools[].name, nodePools[].version)"

# Cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed

# ML inference health check
kubectl get pods -l app=ml-inference -o wide
# Test inference endpoint
curl -X POST http://INFERENCE_SERVICE/predict -d '{"test": "data"}'

# Postgres health check  
kubectl exec -it postgres-0 -n postgres-namespace -- psql -c "SELECT version();"
kubectl get postgresql -A  # If using operator CRDs
```

## Rollback Plan

**Control Plane:** Minor version downgrades require GKE support involvement. Consider two-step upgrade instead (`--control-plane-soak-duration`) for rollback safety during soak period.

**Node Pools:** Can be rolled back by creating new pools at 1.32:
```bash
# Create rollback pool
gcloud container node-pools create POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.32 \
  --num-nodes NUM_NODES \
  --machine-type MACHINE_TYPE

# Migrate workloads, then delete upgraded pool
```

## Risk Mitigation

### High-Risk Items
1. **GPU driver compatibility** - MUST test in staging first
2. **Postgres operator breaking changes** - Verify operator docs for 1.33 support
3. **ML model compatibility** - New CUDA version may affect inference

### Medium-Risk Items
1. **Inference latency during GPU upgrade** - Mitigated by blue-green strategy
2. **Database brief unavailability** - Mitigated by conservative surge settings
3. **Resource constraints** - Monitor quota usage during surge

## Timeline & Coordination

**Recommended Window:** Weekend maintenance window, 4-6 hours
- Hour 1: Pre-flight checks and control plane upgrade  
- Hour 2: General-purpose pool upgrade
- Hour 3: High-memory pool upgrade (with Postgres monitoring)
- Hours 4-6: GPU pool upgrade (blue-green process including soak time)

**Stakeholder Communication:**
- ML team: Inference may be briefly unavailable during GPU upgrade
- Database team: Monitor Postgres health during high-memory pool upgrade  
- Development teams: No new deployments during control plane upgrade (~15 min)

## Success Criteria

- [ ] All components running Kubernetes 1.33
- [ ] Zero failed pods post-upgrade
- [ ] ML inference endpoints responding with normal latency
- [ ] Postgres databases accepting connections and queries
- [ ] No increase in error rates or P95 latency
- [ ] All PVCs remain bound and accessible

This plan prioritizes safety with conservative settings for critical workloads (Postgres) while optimizing for minimal disruption on inference workloads through blue-green strategy.