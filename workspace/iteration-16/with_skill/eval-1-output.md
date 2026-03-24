# GKE Upgrade Plan: 1.32 → 1.33

**Cluster:** Your Standard cluster  
**Mode:** Standard GKE  
**Channel:** Regular  
**Current version:** 1.32  
**Target version:** 1.33  
**Timeline:** Before end of quarter  

## Executive Summary

This is a **minor version upgrade** requiring careful sequencing: control plane first, then node pools. Since you're on Regular channel, 1.33 should be available (it typically reaches Regular ~2-4 weeks after Rapid). The upgrade will follow a staged approach with the GPU pool getting special attention due to inference workload sensitivity.

## Version Compatibility Check

**Action Items:**
- [ ] Verify 1.33 availability in Regular channel:
```bash
gcloud container get-server-config --zone us-central1-a \
  --format="yaml(channels.REGULAR)"
```
- [ ] Check for deprecated API usage (most common upgrade blocker):
```bash
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```
- [ ] Review [GKE 1.33 release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) for breaking changes
- [ ] Verify Postgres operator compatibility with Kubernetes 1.33

## Upgrade Strategy by Pool

### 1. General-Purpose Pool (First)
- **Strategy:** Surge upgrade (stateless workloads assumed)
- **Settings:** `maxSurge=5%` (minimum 1), `maxUnavailable=0`
- **Rationale:** Zero-downtime rolling replacement, percentage scales with pool size

### 2. High-Memory Pool (Postgres) (Second)
- **Strategy:** Conservative surge
- **Settings:** `maxSurge=1, maxUnavailable=0`
- **Rationale:** Database workloads need one-at-a-time replacement, let PDBs protect quorum
- **Prerequisites:** Ensure Postgres operator PDBs are configured properly

### 3. GPU Pool (ML Inference) (Last)
- **Strategy:** Depends on your GPU reservation setup
- **Option A** (if no surge GPU capacity): `maxSurge=0, maxUnavailable=1`
- **Option B** (if surge GPU quota available): `maxSurge=1, maxUnavailable=0`
- **Rationale:** GPU VMs don't support live migration, every upgrade requires pod restart. Inference workloads need minimal disruption.

## Detailed Upgrade Plan

### Phase 1: Pre-Upgrade (1-2 days before)

**Infrastructure Readiness:**
```bash
# Check current cluster state
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Verify node health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed

# Check PDBs for critical workloads
kubectl get pdb -A -o wide
```

**GPU Pool Capacity Check:**
```bash
# Verify if you have GPU surge capacity
gcloud compute reservations list --filter="zone:us-central1-a"
# If using reservations, check headroom beyond current utilization
```

**Workload Readiness:**
- [ ] Postgres operator: Verify PDB allows 1 replica down (for HA setups)
- [ ] ML inference: Confirm models can handle brief pod restarts
- [ ] General workloads: Ensure no bare pods exist

### Phase 2: Control Plane Upgrade

**Recommended timing:** During maintenance window (suggest weekend morning)

```bash
# Upgrade control plane to 1.33
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-central1-a \
  --master \
  --cluster-version=1.33.X-gke.Y

# Monitor progress (~10-15 minutes for zonal cluster)
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="value(currentMasterVersion)"
```

**Validation:**
```bash
kubectl get pods -n kube-system
kubectl version --short
```

### Phase 3: Node Pool Upgrades (Sequential)

#### Step 1: General-Purpose Pool
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
  --cluster-version=1.33.X-gke.Y
```

#### Step 2: High-Memory Pool (Postgres)
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
  --cluster-version=1.33.X-gke.Y
```

#### Step 3: GPU Pool (ML Inference)
**Choose based on your GPU capacity:**

**Option A - No Surge Capacity (most common):**
```bash
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

gcloud container node-pools upgrade gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version=1.33.X-gke.Y
```

**Option B - Surge Capacity Available:**
```bash
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

## Risk Mitigation

**GPU Driver Compatibility:**
- [ ] GKE will auto-install GPU drivers matching 1.33 - this may change CUDA versions
- [ ] Test inference workloads in staging first to verify compatibility

**Postgres Operator:**
- [ ] Ensure PDB configured: `minAvailable: 1` or `minAvailable: 50%`
- [ ] Verify operator supports Kubernetes 1.33
- [ ] Consider backup before upgrade as safety measure

**Maintenance Window Setup:**
```bash
# Configure for weekend maintenance (example: Saturday 6 AM PST)
gcloud container clusters update CLUSTER_NAME \
  --zone us-central1-a \
  --maintenance-window-start "2024-01-06T14:00:00Z" \
  --maintenance-window-end "2024-01-06T20:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Timeline Estimate

- **Control plane:** 10-15 minutes
- **General-purpose pool:** 30-60 minutes (depends on size)
- **High-memory pool:** 45-90 minutes (conservative, one-at-a-time)
- **GPU pool:** 60-120 minutes (depends on inference traffic patterns)

**Total upgrade window:** Plan 4-6 hours including validation

## Rollback Plan

**Control plane:** Minor version rollback requires GKE support. Consider using two-step upgrade with soak period if available.

**Node pools:** Can create new pools at 1.32 and migrate workloads if needed:
```bash
gcloud container node-pools create POOL-rollback \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version=1.32.X-gke.Y
```

## Success Criteria

Post-upgrade validation checklist:
- [ ] All nodes at 1.33: `kubectl get nodes -o wide`
- [ ] All system pods healthy: `kubectl get pods -n kube-system`
- [ ] Postgres operator reporting healthy
- [ ] ML inference endpoints responding with normal latency
- [ ] No CrashLoopBackOff pods: `kubectl get pods -A | grep -v Running`

## Next Steps

1. **Immediate:** Verify 1.33 availability in Regular channel
2. **This week:** Schedule maintenance window and stakeholder communication
3. **Pre-upgrade day:** Run pre-flight checklist and backup verification
4. **Upgrade day:** Execute in sequence with validation between phases

Would you like me to adjust this plan based on your specific node pool sizes or provide more detailed commands for any particular phase?