# GKE Upgrade Plan: Standard Cluster 1.32 → 1.33

**Cluster:** Standard GKE, Regular release channel, us-central1-a  
**Current version:** 1.32  
**Target version:** 1.33  
**Upgrade type:** Minor version upgrade  

## Executive Summary

This is a straightforward minor version upgrade within the supported 2-version skew policy. The upgrade will proceed in sequence: control plane first, then node pools. Total estimated time: 2-4 hours depending on node pool sizes and surge settings.

## Version Compatibility Assessment

✅ **Target version availability:** Verify 1.33 is available in Regular channel:
```bash
gcloud container get-server-config --zone us-central1-a --format="yaml(channels.regular)"
```

✅ **Version skew:** 1.32 → 1.33 is a single minor version jump - fully supported  
✅ **Node pool compatibility:** All pools can skip-level upgrade 1.32 → 1.33 after control plane upgrade

**Action required:** Check GKE release notes for 1.32 → 1.33 breaking changes and verify no deprecated API usage:
```bash
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```

## Upgrade Strategy

### Control plane upgrade
- **Method:** Sequential minor version upgrade (1.32 → 1.33)
- **Downtime:** ~5-10 minutes for zonal cluster API unavailability
- **Rollback:** Two-step upgrade available for 1.33+ with configurable soak period

### Node pool upgrade strategies

**General-purpose pool:**
- **Strategy:** Surge upgrade (default)
- **Settings:** `maxSurge=5%` of pool size (minimum 1), `maxUnavailable=0`
- **Rationale:** Stateless workloads, zero-downtime rolling replacement

**High-memory Postgres pool:**
- **Strategy:** Surge upgrade (conservative)
- **Settings:** `maxSurge=1, maxUnavailable=0`
- **Rationale:** Database workloads need careful one-at-a-time replacement, let PDBs protect quorum

**GPU inference pool:**
- **Strategy:** Surge upgrade (capacity-constrained)
- **Settings:** `maxSurge=0, maxUnavailable=1`
- **Rationale:** GPU reservations typically have no surge capacity; `maxUnavailable` is the primary lever for GPU pools

## Pre-Upgrade Checklist

```markdown
- [ ] Version 1.33 available in Regular channel (verify above command)
- [ ] No deprecated API usage detected
- [ ] GKE release notes reviewed for 1.32 → 1.33 breaking changes
- [ ] Postgres operator compatibility with K8s 1.33 confirmed
- [ ] GPU driver compatibility with 1.33 node image verified
- [ ] PDBs configured for Postgres StatefulSets (recommend `minAvailable: 1` or 50%)
- [ ] PDBs configured for ML inference deployments
- [ ] No bare pods in cluster
- [ ] Postgres backups completed and PV reclaim policy = Retain
- [ ] Baseline metrics captured (error rates, inference latency)
- [ ] Maintenance window scheduled (recommend weekend off-peak)
- [ ] On-call team available during upgrade window
```

## Maintenance Window Configuration

**Recommended timing:** Weekend 2-6 AM maintenance window to minimize business impact:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone us-central1-a \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Optional upgrade control:** If you need maximum control over timing, add a "no minor or node upgrades" exclusion to prevent auto-upgrades and trigger manually:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "manual-upgrade-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-03-31T23:59:59Z"
```

This allows you to manually trigger the upgrade exactly when ready rather than waiting for GKE's auto-upgrade timing.

## Upgrade Runbook

### Step 1: Control Plane Upgrade

```bash
# Verify current state
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Upgrade control plane (5-10 min)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-central1-a \
  --master \
  --cluster-version 1.33

# Verify control plane upgraded
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="value(currentMasterVersion)"

# Check system pods health
kubectl get pods -n kube-system
```

### Step 2: Configure Node Pool Surge Settings

```bash
# General-purpose pool (assuming 20 nodes = maxSurge=1)
gcloud container node-pools update general-purpose-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# High-memory Postgres pool (conservative)
gcloud container node-pools update high-memory-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# GPU pool (no surge capacity assumed)
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

### Step 3: Node Pool Upgrades (Sequential)

**Upgrade order:** General → GPU → Postgres (least to most sensitive)

```bash
# 1. General-purpose pool first
gcloud container node-pools upgrade general-purpose-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# 2. GPU inference pool
gcloud container node-pools upgrade gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33

# 3. Postgres pool last (most careful)
gcloud container node-pools upgrade high-memory-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33
```

### Step 4: Post-Upgrade Validation

```bash
# All nodes at target version
gcloud container node-pools list --cluster CLUSTER_NAME --zone us-central1-a

# All nodes Ready
kubectl get nodes

# No stuck pods
kubectl get pods -A | grep -v Running | grep -v Completed

# Postgres StatefulSets healthy
kubectl get statefulsets -A

# ML inference deployments healthy  
kubectl get deployments -A

# Application health checks
# [Add your specific health check endpoints]
```

## Rollback Plan

**Control plane:** Contact GKE support for minor version rollback (or use two-step upgrade soak period if configured)

**Node pools:** Can be rolled back by creating new pools at 1.32 and migrating workloads:

```bash
# Create rollback pool
gcloud container node-pools create POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.32 \
  --num-nodes NUM_NODES \
  --machine-type MACHINE_TYPE

# Cordon upgraded pool and migrate
kubectl cordon -l cloud.google.com/gke-nodepool=ORIGINAL_POOL
```

## Risk Mitigation

**Postgres-specific:**
- PDB configured to protect database quorum during drain
- Application-level backup completed before node upgrades
- `maxSurge=1` ensures conservative one-node-at-a-time replacement

**GPU inference-specific:**
- `maxUnavailable=1` works within fixed GPU reservations
- GPU driver automatically updated to match 1.33 - verify inference pipeline compatibility
- Consider brief inference service degradation during GPU node replacement

**General:**
- Maintenance window during off-peak hours
- Sequential node pool upgrades to isolate issues
- Monitoring active throughout upgrade process

## Success Criteria

- [ ] Control plane at 1.33
- [ ] All node pools at 1.33  
- [ ] All nodes in Ready state
- [ ] Postgres databases accessible and responsive
- [ ] ML inference endpoints serving traffic
- [ ] Error rates within baseline
- [ ] No deprecated API warnings

**Estimated timeline:** 2-4 hours total (30 min CP + 1-3 hours node pools depending on size)

Would you like me to adjust any of these settings based on your specific pool sizes or add additional validation steps for your Postgres operator or ML inference workloads?