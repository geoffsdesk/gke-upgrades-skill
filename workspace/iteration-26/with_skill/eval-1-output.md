# GKE Cluster Upgrade Plan: 1.32 → 1.33

## Cluster Overview
- **Cluster**: Standard GKE on Regular release channel
- **Current version**: 1.32
- **Target version**: 1.33
- **Region**: us-central1-a
- **Node pools**: 3 (general-purpose, high-memory/Postgres, GPU/ML inference)

## Version Compatibility Assessment

✅ **Version skew**: 1.32→1.33 is a single minor version jump - fully supported
✅ **Release channel**: Regular channel should have 1.33 available by now
✅ **Upgrade path**: Sequential control plane upgrade first, then node pools

**Action items before proceeding:**
```bash
# Verify 1.33 is available in Regular channel
gcloud container get-server-config --zone us-central1-a --format="yaml(channels)"

# Check for deprecated API usage (critical!)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Review GKE release notes for 1.32→1.33 breaking changes
```

## Recommended Upgrade Strategy

### Control Plane
- **Method**: Direct 1.32→1.33 upgrade
- **Consider**: Two-step upgrade with soak period for additional safety (1.33+ supports rollback-safe upgrades)
- **Downtime**: ~5-10 minutes API unavailability (zonal cluster)

### Node Pool Strategies

| Pool | Strategy | Settings | Rationale |
|------|----------|----------|-----------|
| **General-purpose** | Surge | `maxSurge=5%, maxUnavailable=0` | Zero-downtime rolling replacement |
| **High-memory (Postgres)** | Surge | `maxSurge=1, maxUnavailable=0` | Conservative - protect database |
| **GPU (ML inference)** | **Autoscaled Blue-Green** | See below | Avoid inference latency spikes from pod restarts |

### GPU Pool Detailed Strategy
Given this is for ML inference, **autoscaled blue-green** is the optimal approach:
- GPU VMs don't support live migration - every surge upgrade causes pod restarts and inference downtime
- Autoscaled blue-green keeps the old pool serving while the new pool warms up
- More cost-effective than standard blue-green (scales down old pool as new pool scales up)

## Pre-Upgrade Checklist

### Compatibility & Breaking Changes
- [ ] Verify 1.33 available in Regular channel
- [ ] Check deprecated API usage - **this is the #1 upgrade failure cause**
- [ ] Review [GKE release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) for 1.32→1.33 changes
- [ ] Test Postgres operator compatibility with Kubernetes 1.33
- [ ] Verify ML inference framework supports 1.33
- [ ] Check GPU driver compatibility with target node image

### Infrastructure Readiness
- [ ] Maintenance window configured for off-peak hours:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone us-central1-a \
  --maintenance-window-start "2024-12-15T02:00:00Z" \
  --maintenance-window-duration 6h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```

- [ ] GPU pool autoscaling enabled (required for autoscaled blue-green):
```bash
gcloud container node-pools update GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --enable-autoscaling \
  --total-min-nodes MIN --total-max-nodes MAX
```

### Workload Protection
- [ ] **Critical**: Configure PDBs for Postgres operator:
```bash
# Example for Postgres primary/replica setup
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: postgres-pdb
spec:
  minAvailable: 1  # Keeps at least 1 replica during upgrade
  selector:
    matchLabels:
      app: postgres
```

- [ ] Backup Postgres data before upgrade
- [ ] No bare pods (check with: `kubectl get pods -A -o json | jq '.items[] | select(.metadata.ownerReferences | length == 0)'`)
- [ ] Adequate `terminationGracePeriodSeconds` on ML inference pods
- [ ] Resource requests set on all containers

## Upgrade Execution Plan

### Phase 1: Control Plane (15-20 minutes)
```bash
# Option A: Direct upgrade (faster)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-central1-a \
  --master \
  --cluster-version 1.33

# Option B: Two-step with rollback capability (safer)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-central1-a \
  --master \
  --cluster-version 1.33 \
  --control-plane-soak-duration 24h  # Can rollback within 24h
```

**Validation:**
```bash
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="value(currentMasterVersion)"

kubectl get pods -n kube-system  # Verify system pods healthy
```

### Phase 2: Node Pool Upgrades

**2a. General-Purpose Pool (30-60 minutes)**
```bash
# Configure surge settings
gcloud container node-pools update GENERAL_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# Upgrade
gcloud container node-pools upgrade GENERAL_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33
```

**2b. High-Memory Pool / Postgres (45-90 minutes)**
```bash
# Conservative settings for database workloads
gcloud container node-pools update HIGH_MEMORY_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade
gcloud container node-pools upgrade HIGH_MEMORY_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33
```

**2c. GPU Pool / ML Inference (60-120 minutes)**
```bash
# Configure autoscaled blue-green
gcloud container node-pools update GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --enable-blue-green-upgrade \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Upgrade
gcloud container node-pools upgrade GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33
```

## Monitoring & Validation

### During Upgrade
```bash
# Monitor node status
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check for stuck pods
kubectl get pods -A | grep -E "Terminating|Pending"

# Monitor PDB status
kubectl get pdb -A -o wide

# Track upgrade operations
gcloud container operations list --cluster CLUSTER_NAME --zone us-central1-a
```

### Post-Upgrade Validation
- [ ] All nodes at version 1.33: `kubectl get nodes -o wide`
- [ ] Postgres operator healthy and accepting connections
- [ ] ML inference endpoints responding with normal latency
- [ ] No CrashLoopBackOff pods: `kubectl get pods -A | grep -v Running`
- [ ] Application smoke tests passing

## Risk Mitigation & Rollback

### High-Risk Areas
1. **Deprecated APIs**: If GKE detects deprecated API usage, auto-upgrades pause automatically
2. **GPU driver changes**: Target version may change CUDA version - test inference models
3. **Postgres operator compatibility**: Database operators are sensitive to API changes

### Rollback Options
- **Control plane**: Patch downgrades possible, minor rollback needs GKE support
- **Node pools**: Can create new pools at 1.32 and migrate workloads if needed
- **GPU pool**: Blue-green strategy allows fast rollback during soak period

### Emergency Procedures
If upgrade fails:
1. Check PDB blocking drain: `kubectl get pdb -A -o wide`
2. Verify resource constraints: `kubectl top nodes`
3. Check admission webhooks: `kubectl get validatingwebhookconfigurations`
4. Contact GKE support with operation IDs if stuck at infrastructure level

## Timeline & Coordination

**Recommended schedule:**
- **Week 1**: Pre-flight checks, PDB configuration, staging validation
- **Week 2**: Production upgrade during planned maintenance window
- **Target completion**: Before end of Q4 (well ahead of any potential 1.32 EoS)

**Estimated total time**: 3-4 hours for all pools with validation

This plan prioritizes safety for your database and inference workloads while meeting your Q4 deadline. The autoscaled blue-green strategy for GPU pools will minimize inference disruption compared to standard surge upgrades.