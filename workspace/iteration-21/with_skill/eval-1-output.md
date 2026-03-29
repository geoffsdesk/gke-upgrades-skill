# GKE Upgrade Plan: Standard Cluster 1.32 → 1.33

## Cluster Overview
- **Cluster:** Standard GKE on Regular release channel
- **Current version:** 1.32
- **Target version:** 1.33
- **Location:** us-central1-a (zonal)
- **Node pools:** 3 (general-purpose, high-memory/Postgres, GPU/inference)

## Version Compatibility Assessment

### ✅ Version Availability
- 1.33 is available in Regular channel
- Sequential minor upgrade (1.32→1.33) - supported path
- No version skew issues (nodes will be within 2 minor versions of CP)

### ⚠️ Breaking Changes to Review
Check the [GKE 1.33 release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) for:
- Deprecated API removals (most common upgrade failure)
- Postgres operator compatibility with K8s 1.33
- GPU driver version changes that might affect ML inference workloads

## Upgrade Strategy

### Control Plane First (Required Order)
- **Strategy:** Direct upgrade 1.32→1.33
- **Timing:** Weekend maintenance window (2-4 hour window)
- **Downtime:** ~5-10 minutes for zonal cluster (API unavailable during CP upgrade)

### Node Pool Upgrade Strategy by Pool Type

#### 1. General-Purpose Pool (Upgrade First - Lowest Risk)
- **Strategy:** Surge upgrade
- **Settings:** `maxSurge=5%` (minimum 1), `maxUnavailable=0`
- **Rationale:** Stateless workloads, zero-downtime rolling replacement

#### 2. GPU Pool (Upgrade Second - Special Handling)
- **Strategy:** Surge with drain-first approach
- **Settings:** `maxSurge=0, maxUnavailable=1`
- **Rationale:** 
  - GPU VMs don't support live migration (every upgrade = pod restart)
  - Assume fixed GPU reservation with no surge capacity
  - Inference workloads can tolerate brief capacity dips
  - `maxUnavailable` is the primary lever for GPU pools

#### 3. High-Memory/Postgres Pool (Upgrade Last - Highest Risk)
- **Strategy:** Conservative surge upgrade
- **Settings:** `maxSurge=1, maxUnavailable=0`
- **Rationale:** Database workloads need careful handling, one node at a time

## Pre-Upgrade Requirements

### Critical Pre-Flight Checks
```bash
# 1. Check for deprecated API usage (CRITICAL)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# 2. Verify GKE recommender insights for upgrade blockers
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=us-central1-a \
    --project=PROJECT_ID \
    --filter="category.category:RELIABILITY"

# 3. Verify 1.33 availability in Regular channel
gcloud container get-server-config --zone us-central1-a --format="yaml(channels)"
```

### Postgres Operator Preparation
- **Backup:** Take application-level backup via Postgres operator before upgrade
- **PDB Review:** Ensure Postgres PDBs allow at least 1 replica to drain (`minAvailable: 1` or `minAvailable: 50%`)
- **Operator Compatibility:** Verify your Postgres operator version supports K8s 1.33

### GPU Workload Preparation  
- **Driver Testing:** Create staging GPU node pool at 1.33 to test CUDA compatibility
- **Inference Validation:** Deploy representative models on staging pool
- **Capacity Planning:** Confirm no surge GPU capacity exists in reservation

## Upgrade Sequence & Timeline

### Phase 1: Control Plane (Saturday, 2 AM - 6 AM)
```bash
# Upgrade control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-central1-a \
  --master \
  --cluster-version 1.33.X-gke.XXXX

# Wait ~10-15 minutes, verify
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="value(currentMasterVersion)"
```

### Phase 2: General-Purpose Pool (Immediately After CP)
```bash
# Configure surge settings
gcloud container node-pools update general-purpose-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade nodes
gcloud container node-pools upgrade general-purpose-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33.X-gke.XXXX
```

### Phase 3: GPU Pool (+30 min soak after general pool)
```bash
# Configure for fixed GPU reservation
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

# Upgrade (expect inference brief interruption per node)
gcloud container node-pools upgrade gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33.X-gke.XXXX
```

### Phase 4: High-Memory/Postgres Pool (+1 hour soak after GPU)
```bash
# Conservative settings for database workload
gcloud container node-pools update high-memory-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade with careful monitoring
gcloud container node-pools upgrade high-memory-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33.X-gke.XXXX
```

## Risk Mitigation

### Maintenance Window Configuration
```bash
# Set predictable upgrade window (Saturdays 2-6 AM)
gcloud container clusters update CLUSTER_NAME \
  --zone us-central1-a \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-end "2024-01-06T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### PDB Protection for Postgres
Verify these PDBs exist before upgrade:
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: postgres-primary-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: postgres-primary
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: postgres-replica-pdb  
spec:
  minAvailable: 50%
  selector:
    matchLabels:
      app: postgres-replica
```

### GPU Driver Compatibility Staging
Before production GPU upgrade:
```bash
# Create test GPU node pool at target version
gcloud container node-pools create gpu-staging \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --machine-type n1-standard-4 \
  --accelerator type=nvidia-tesla-t4,count=1 \
  --cluster-version 1.33.X-gke.XXXX \
  --num-nodes 1

# Test inference workloads, validate CUDA compatibility
# Delete staging pool after validation
```

## Rollback Strategy

### If Control Plane Issues
- Minor version rollback requires GKE support involvement
- Apply temporary maintenance exclusion to prevent further auto-upgrades:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "rollback-hold" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-01-31T00:00:00Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

### If Node Pool Issues
- Cancel in-progress upgrade: GKE completes current node then stops
- Create new pool at 1.32, migrate workloads, delete failed pool
- Nodes can run mixed versions during recovery (1.32 nodes with 1.33 control plane)

## Monitoring & Validation

### During Upgrade
```bash
# Monitor node upgrade progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check for stuck pods
kubectl get pods -A | grep -E "Terminating|Pending|CrashLoopBackOff"

# Monitor Postgres health
kubectl get pods -l app=postgres -n postgres-namespace
```

### Post-Upgrade Validation
```bash
# Verify all components at target version
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Application health checks
# - Postgres connection tests
# - GPU inference endpoint smoke tests  
# - General application health checks
```

## Timeline Estimate
- **Total window:** 4-6 hours
- **Control plane:** 15 minutes  
- **General pool:** 1-2 hours
- **GPU pool:** 1-2 hours (depends on pool size)
- **Postgres pool:** 2-3 hours (conservative, database-safe)

## Key Recommendations
1. **Stage GPU driver testing first** - Critical for inference workloads
2. **Take Postgres backup before starting** - Database safety
3. **Use the node pool upgrade sequence above** - Lowest to highest risk
4. **Monitor PDB violations** - Check Cloud Logging for eviction blocks
5. **Have rollback plan ready** - Especially for the Postgres pool

This plan prioritizes workload safety while meeting your end-of-quarter deadline. The sequential approach (general→GPU→Postgres) minimizes risk by validating the upgrade on less critical workloads first.