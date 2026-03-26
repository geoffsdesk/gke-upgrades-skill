# GKE Upgrade Plan: 1.32 → 1.33

**Cluster Details:**
- **Cluster:** Standard GKE on Regular release channel
- **Current Version:** 1.32
- **Target Version:** 1.33
- **Zone:** us-central1-a
- **Node Pools:** General-purpose, High-memory (Postgres), GPU (ML inference)

## Executive Summary

This is a **minor version upgrade** requiring sequential control plane upgrade followed by node pool upgrades. Since you're on Regular channel, 1.33 should be available. The upgrade will require careful handling of your Postgres workloads and GPU inference pods.

**Estimated Timeline:** 4-6 hours total
- Control plane: 15-30 minutes
- Node pools: 3-4 hours (depending on pool sizes and surge settings)

## Version Compatibility Check

```bash
# Verify 1.33 is available in Regular channel
gcloud container get-server-config --zone us-central1-a \
  --format="yaml(channels.REGULAR)"

# Check current cluster version
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Critical: Check for deprecated APIs (most common upgrade failure cause)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Also check GKE deprecation insights
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=us-central1-a \
    --project=PROJECT_ID
```

## Upgrade Strategy by Node Pool

### 1. General-Purpose Pool
**Strategy:** Surge upgrade with conservative settings
- `maxSurge=5%` of pool size (minimum 1)
- `maxUnavailable=0` for zero-downtime rolling replacement

### 2. High-Memory Pool (Postgres)
**Strategy:** Conservative surge upgrade
- `maxSurge=1, maxUnavailable=0` — one-at-a-time replacement
- **Critical:** Configure PDBs before upgrade to protect Postgres quorum

### 3. GPU Pool (ML Inference) 
**Strategy:** Depends on your GPU reservation setup
- **If fixed GPU reservation (no surge capacity):** `maxSurge=0, maxUnavailable=1`
- **If surge GPU capacity available:** `maxSurge=1, maxUnavailable=0`
- **Alternative:** Consider autoscaled blue-green to avoid inference latency spikes

## Pre-Upgrade Requirements

### Postgres Workload Protection
Configure PDBs immediately if not already present:
```bash
# Example PDB for Postgres (adjust replicas based on your setup)
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: postgres-pdb
  namespace: postgres-namespace
spec:
  minAvailable: 1  # Adjust based on your replica count
  selector:
    matchLabels:
      app: postgres
```

### GPU Driver Compatibility
**Critical step:** Verify GPU driver compatibility before upgrading production:
1. Create a staging GPU node pool with GKE 1.33
2. Deploy your ML inference workloads
3. Validate CUDA calls, model loading, and throughput
4. **Never skip this validation** — GKE auto-installs drivers matching the GKE version, which can change CUDA versions

## Upgrade Sequence

### Phase 1: Control Plane Upgrade
```bash
# Set maintenance window (optional but recommended)
gcloud container clusters update CLUSTER_NAME \
  --zone us-central1-a \
  --maintenance-window-start "2024-01-13T02:00:00Z" \
  --maintenance-window-end "2024-01-13T08:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Upgrade control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-central1-a \
  --master \
  --cluster-version 1.33
```

**Validation:**
```bash
# Wait 15-30 minutes, then verify
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="value(currentMasterVersion)"

kubectl get pods -n kube-system  # All should be Running
```

### Phase 2: Node Pool Upgrades (Sequential)

**Order:** General-purpose → GPU → High-memory (Postgres last for maximum caution)

#### Step 1: General-Purpose Pool
```bash
# Calculate maxSurge (5% of pool size, minimum 1)
# For 20-node pool: maxSurge=1, for 40-node pool: maxSurge=2

gcloud container node-pools update general-purpose-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade CALCULATED_VALUE \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade general-purpose-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33
```

#### Step 2: GPU Pool
```bash
# Option A: If NO surge GPU capacity (most common)
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

# Option B: If surge GPU capacity IS available
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33
```

#### Step 3: High-Memory Pool (Postgres)
```bash
gcloud container node-pools update high-memory-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade high-memory-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33
```

## Monitoring During Upgrade

```bash
# Monitor node upgrade progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check for stuck pods
kubectl get pods -A | grep -E "Terminating|Pending|Error"

# Monitor PDB status
kubectl get pdb -A -o wide

# Check upgrade operations
gcloud container operations list --cluster CLUSTER_NAME --zone us-central1-a --limit=3
```

## Rollback Plan

- **Control plane:** Minor version rollback requires GKE support involvement
- **Node pools:** Can be rolled back by creating new pools at 1.32 and migrating workloads
- **During upgrade:** Cancel in-progress node pool upgrades if critical issues arise

## Success Validation

```bash
# All components at 1.33
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="table(currentMasterVersion, nodePools[].name, nodePools[].version)"

# All nodes Ready
kubectl get nodes

# Postgres health check
kubectl get pods -n postgres-namespace
kubectl logs -n postgres-namespace -l app=postgres --tail=50

# GPU inference health check
kubectl get pods -n ml-namespace
# Run sample inference request to validate GPU functionality

# System pods healthy
kubectl get pods -n kube-system

# No deprecated API warnings
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```

## Risk Mitigation

### High-Risk Items
1. **GPU driver compatibility** — validated in staging first
2. **Postgres PDB configuration** — prevents database unavailability
3. **Inference latency spikes** — consider autoscaled blue-green for GPU pool

### Maintenance Window Recommendation
Schedule for **Saturday 2-8 AM** to minimize business impact. The 6-hour window accommodates potential troubleshooting time.

### Emergency Contacts
- Ensure on-call engineer available during upgrade window
- Have GKE support case number ready if escalation needed

## Pre-Upgrade Checklist

- [ ] 1.33 available in Regular channel (verified via get-server-config)
- [ ] No deprecated API usage detected
- [ ] PDBs configured for Postgres workloads
- [ ] GPU driver compatibility tested in staging
- [ ] Baseline metrics captured (error rates, inference latency)
- [ ] Maintenance window scheduled
- [ ] On-call team notified
- [ ] Sufficient compute quota for surge nodes (check GPU quota especially)

**Next Steps:** Execute the pre-upgrade checklist, then proceed with Phase 1 (control plane) during your scheduled maintenance window.