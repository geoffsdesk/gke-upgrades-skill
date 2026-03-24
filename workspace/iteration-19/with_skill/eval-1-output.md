# GKE Upgrade Plan: Standard Cluster 1.32 → 1.33

## Cluster Overview
- **Cluster**: Standard GKE cluster
- **Channel**: Regular
- **Current Version**: 1.32
- **Target Version**: 1.33
- **Location**: us-central1-a (zonal)
- **Node Pools**: 3 (general-purpose, high-memory/Postgres, GPU/ML inference)

## Version Compatibility Assessment

### ✅ Channel Availability
```bash
# Verify 1.33 is available in Regular channel
gcloud container get-server-config --zone us-central1-a \
  --format="yaml(channels.regular)"
```

### ⚠️ Breaking Changes Review
**Critical items to check between 1.32 → 1.33:**
- Review [GKE release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) for 1.33
- Check for deprecated API removal (most common upgrade blocker)
- Verify Postgres operator compatibility with Kubernetes 1.33
- Confirm GPU driver/CUDA version changes

### Pre-flight API Deprecation Check
```bash
# Check for deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Check GKE deprecation insights
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=us-central1-a \
    --project=PROJECT_ID
```

## Upgrade Strategy

### Sequential Control Plane → Node Pool Approach
1. **Control plane**: 1.32 → 1.33
2. **Node pools**: Skip-level upgrade 1.32 → 1.33 (all pools simultaneously after CP completion)

**Rationale**: Skip-level node upgrades reduce total upgrade time and minimize drain cycles. Since nodes are only 1 version behind after CP upgrade, this is within the 2-version skew limit.

### Node Pool Upgrade Strategies by Workload Type

#### General-Purpose Pool
- **Strategy**: Surge upgrade
- **Settings**: `maxSurge=5%, maxUnavailable=0`
- **Rationale**: Stateless workloads, zero-downtime rolling replacement

#### High-Memory Pool (Postgres)
- **Strategy**: Surge upgrade (conservative)
- **Settings**: `maxSurge=1, maxUnavailable=0`
- **Rationale**: Database workloads need careful one-at-a-time replacement
- **Prerequisites**: 
  - Verify PDBs configured for Postgres pods
  - Take application-level backup before upgrade
  - Confirm PV reclaim policy is `Retain`

#### GPU Pool (ML Inference)
- **Strategy**: **Autoscaled blue-green** (recommended for inference)
- **Rationale**: 
  - Avoids inference latency spikes from pod restarts
  - GPU VMs don't support live migration (every surge upgrade causes restarts)
  - Keeps old pool serving while new pool warms up
- **Alternative**: If capacity constrained: `maxSurge=0, maxUnavailable=1`
- **Prerequisites**: 
  - Verify GPU driver compatibility with 1.33 node image
  - Test inference workloads in staging with target version

## Maintenance Controls

### Maintenance Window (Recommended)
```bash
# Set weekend maintenance window
gcloud container clusters update CLUSTER_NAME \
  --zone us-central1-a \
  --maintenance-window-start "2024-12-14T02:00:00-06:00" \
  --maintenance-window-end "2024-12-14T08:00:00-06:00" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### Option: Manual Upgrade Control
Since you need to upgrade "before end of quarter," you can:
1. **Auto-upgrade**: Let GKE upgrade automatically within your maintenance window
2. **Manual trigger**: Initiate the upgrade yourself for precise timing control

## Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist - Standard GKE 1.32 → 1.33
- [ ] Cluster: [CLUSTER_NAME] | Mode: Standard | Channel: Regular
- [ ] Current version: 1.32 | Target version: 1.33

Compatibility
- [ ] 1.33 available in Regular channel (`gcloud container get-server-config --zone us-central1-a`)
- [ ] No deprecated API usage (check GKE deprecation insights dashboard)
- [ ] GKE release notes reviewed for 1.32 → 1.33 breaking changes
- [ ] Postgres operator compatibility with K8s 1.33 verified
- [ ] GPU driver compatibility confirmed with 1.33 node image
- [ ] ML inference models tested against target GPU driver version

Workload Readiness
- [ ] PDBs configured for Postgres pods (not overly restrictive)
- [ ] No bare pods — all managed by controllers
- [ ] Postgres application-level backup completed
- [ ] StatefulSet PV reclaim policies verified (should be Retain)
- [ ] GPU inference health checks documented

Infrastructure
- [ ] General pool: maxSurge=5% maxUnavailable=0
- [ ] Postgres pool: maxSurge=1 maxUnavailable=0  
- [ ] GPU pool: autoscaled blue-green OR maxSurge=0 maxUnavailable=1
- [ ] Skip-level upgrade planned (1.32 → 1.33 for all node pools)
- [ ] Sufficient compute quota for surge nodes (check non-GPU pools)
- [ ] Maintenance window configured for weekend upgrade

Ops Readiness
- [ ] Monitoring active, baseline metrics captured
- [ ] Upgrade window communicated to ML/database teams
- [ ] Rollback plan documented
- [ ] On-call team available during maintenance window
```

## Upgrade Runbook

### Phase 1: Control Plane Upgrade
```bash
# Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-central1-a \
  --master \
  --cluster-version 1.33.X-gke.Y

# Wait ~10-15 minutes, then verify
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="value(currentMasterVersion)"

kubectl get pods -n kube-system
```

### Phase 2: Configure Node Pool Upgrade Settings
```bash
# General-purpose pool (5% surge)
gcloud container node-pools update general-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 5% \
  --max-unavailable-upgrade 0

# High-memory/Postgres pool (conservative)
gcloud container node-pools update high-memory-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# GPU pool (autoscaled blue-green)
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --enable-autoscaling \
  --total-min-nodes MIN --total-max-nodes MAX \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

### Phase 3: Node Pool Upgrades (Skip-Level)
```bash
# Upgrade all pools to 1.33 (skip-level from 1.32)
# Start with general-purpose (lowest risk)
gcloud container node-pools upgrade general-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33.X-gke.Y

# Then high-memory pool
gcloud container node-pools upgrade high-memory-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33.X-gke.Y

# Finally GPU pool
gcloud container node-pools upgrade gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33.X-gke.Y
```

### Phase 4: Validation
```bash
# Verify all components at target version
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check node and pod health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed

# Postgres-specific checks
kubectl get statefulsets -A
kubectl get pvc -A | grep -v Bound

# GPU inference checks
kubectl get pods -l app=inference-service
# Test inference endpoints
```

## Risk Mitigation

### Zonal Cluster Consideration
⚠️ **Important**: This is a zonal cluster (us-central1-a). During control plane upgrade (~10-15 min):
- **No new deployments** or cluster config changes possible
- **Existing workloads continue running** normally
- **Higher availability clusters**: Consider migrating to regional (us-central1) for future upgrades

### GPU Pool Special Handling
- **Driver compatibility**: Test ML models with the new GPU driver before production upgrade
- **Inference latency**: Autoscaled blue-green minimizes service disruption vs. surge
- **Capacity constraints**: If using fixed GPU reservation, verify headroom or use `maxUnavailable` mode

### Database Protection
- **PDB verification**: Ensure Postgres PDBs allow some disruption (not 0 unavailable)
- **Backup requirement**: Take fresh application-level backup before any node pool upgrade
- **Connection pooling**: Verify connection pools handle brief pod restarts gracefully

## Timeline Estimate

- **Control plane**: 10-15 minutes
- **General pool**: 30-60 minutes (depends on pool size)
- **High-memory pool**: 45-90 minutes (conservative settings)
- **GPU pool**: 1-2 hours (blue-green soak time + inference validation)
- **Total window**: 2-4 hours

Plan your maintenance window accordingly, preferably during off-peak hours.

---

**Next Steps:**
1. Review the pre-upgrade checklist
2. Schedule your maintenance window
3. Validate the upgrade in a staging environment if available
4. Execute the runbook during your planned window

Would you like me to adjust any part of this plan based on your specific workload requirements or constraints?