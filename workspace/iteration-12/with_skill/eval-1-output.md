# GKE Upgrade Plan: 1.32 → 1.33

## Overview
- **Cluster**: Standard GKE on Regular release channel
- **Location**: us-central1-a
- **Current version**: 1.32.x
- **Target version**: 1.33.x
- **Timeline**: Before end of quarter
- **Node pools**: General-purpose, high-memory (Postgres), GPU (ML inference)

## Version Compatibility & Availability

### Pre-flight checks
```bash
# Verify 1.33 availability in Regular channel
gcloud container get-server-config --zone us-central1-a \
  --format="yaml(channels)" | grep -A 10 "regular"

# Check current cluster state
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check for deprecated API usage (critical - blocks auto-upgrades)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Also check GKE deprecation insights
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=us-central1-a \
    --project=PROJECT_ID
```

### Breaking changes review
Review [GKE 1.33 release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) for:
- Kubernetes 1.33 changes from upstream
- GKE-specific modifications
- GPU driver version changes (affects your ML inference pool)

## Upgrade Strategy

### Control plane first (required)
The control plane must be upgraded before any node pools. This is non-negotiable in GKE's upgrade order.

### Node pool upgrade approach
Given your workload types, I recommend **skip-level upgrades within supported version skew** to minimize total upgrade time:

1. **General-purpose pool**: Surge upgrade with moderate parallelism
2. **High-memory pool (Postgres)**: Conservative surge to protect database workloads  
3. **GPU pool**: Drain-first approach (assumes limited GPU surge capacity)

## Node Pool Upgrade Configuration

### General-purpose pool
```bash
gcloud container node-pools update general-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```
**Rationale**: 2 surge nodes provide reasonable upgrade speed while limiting quota impact. Zero unavailable ensures no capacity dip.

### High-memory pool (Postgres operator)
```bash
gcloud container node-pools update postgres-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```
**Rationale**: Conservative single-node surge. Let PodDisruptionBudgets protect Postgres workloads. High-memory VMs are expensive, so minimize surge overhead.

### GPU pool (ML inference)
```bash
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```
**Rationale**: GPU VMs typically have fixed reservations with no surge capacity. `maxUnavailable=1` is the primary lever - drains first, no extra GPUs needed, but causes temporary capacity dip. Increase to 2 if you can tolerate more inference capacity reduction during upgrade.

## Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist
- [ ] Cluster: CLUSTER_NAME | Mode: Standard | Channel: Regular
- [ ] Current version: 1.32.x | Target version: 1.33.x

Compatibility
- [ ] Target version 1.33 available in Regular channel
- [ ] No deprecated API usage (check GKE deprecation insights dashboard)
- [ ] GKE release notes reviewed for 1.32→1.33 breaking changes
- [ ] Node version skew within 2 minor versions of control plane ✓
- [ ] Postgres operator compatibility with K8s 1.33 verified
- [ ] ML inference framework compatibility with new GPU drivers verified

Workload Readiness
- [ ] PDBs configured for Postgres workloads (verify minAvailable settings)
- [ ] No bare pods — all managed by controllers
- [ ] terminationGracePeriodSeconds adequate for graceful shutdown
- [ ] Postgres PV backups completed, reclaim policies verified
- [ ] Resource requests/limits set on all containers
- [ ] GPU driver compatibility confirmed with target node image
- [ ] ML inference service health checks configured

Infrastructure
- [ ] Node pool upgrade strategies configured (see commands above)
- [ ] Sufficient compute quota for surge nodes (general + postgres pools)
- [ ] GPU quota verified (N/A for drain-first approach)
- [ ] Maintenance window configured for off-peak hours

Ops Readiness
- [ ] Baseline metrics captured (inference latency, Postgres response times)
- [ ] Upgrade window communicated to stakeholders
- [ ] On-call team available during upgrade window
- [ ] Postgres backup verified and tested
```

## Upgrade Execution Runbook

### Phase 1: Control plane upgrade
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-central1-a \
  --master \
  --cluster-version 1.33.x

# Monitor (takes ~10-15 minutes)
watch 'gcloud container clusters describe CLUSTER_NAME --zone us-central1-a --format="value(currentMasterVersion)"'

# Verify system pods healthy
kubectl get pods -n kube-system
```

### Phase 2: Node pool upgrades (sequential)

**Step 1: General-purpose pool**
```bash
gcloud container node-pools upgrade general-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33.x

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

**Step 2: High-memory pool (Postgres)**
```bash
# Verify Postgres pods healthy before starting
kubectl get pods -A | grep postgres

gcloud container node-pools upgrade postgres-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33.x

# Monitor Postgres pod stability during upgrade
kubectl get pods -A -w | grep postgres
```

**Step 3: GPU pool (ML inference)**
```bash
# Note: This will temporarily reduce inference capacity
gcloud container node-pools upgrade gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33.x

# Monitor GPU driver installation
kubectl get nodes -l cloud.google.com/gke-accelerator -o wide
```

## Validation Steps

After each phase:
```bash
# Node health
kubectl get nodes

# Workload health
kubectl get pods -A | grep -v Running | grep -v Completed

# Specific validation per pool type:

# Postgres validation
kubectl get statefulsets -A | grep postgres
kubectl exec -it POSTGRES_POD -- psql -c "SELECT version();"

# GPU validation
kubectl get nodes -l cloud.google.com/gke-accelerator
kubectl describe node GPU_NODE_NAME | grep -A 5 "nvidia.com/gpu"

# Inference service validation
curl -X POST YOUR_INFERENCE_ENDPOINT/health
```

## Maintenance Window Recommendation

Configure a maintenance window to control auto-upgrade timing:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone us-central1-a \
  --maintenance-window-start 2024-01-13T02:00:00Z \
  --maintenance-window-end 2024-01-13T06:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```

## Troubleshooting Preparedness

**Most likely issues for your workload types:**

1. **Postgres PDBs blocking drain**: Check `kubectl get pdb -A` and temporarily relax if needed
2. **GPU driver compatibility**: New 1.33 node image may change CUDA version - test in staging first
3. **High-memory node surge capacity**: If surge fails due to quota, switch to `maxUnavailable` mode temporarily
4. **Long-running inference requests**: Consider shorter graceful termination periods or request queuing

## Timeline Estimate

- Control plane: ~15 minutes
- General pool: ~30-45 minutes (depends on size)
- Postgres pool: ~45-60 minutes (conservative pace)
- GPU pool: ~60-90 minutes (drain-first is slower, driver installation takes time)

**Total window**: Plan for 3-4 hours including validation.

## Rollback Plan

If issues arise:
- Control plane downgrades require GKE support involvement
- Node pools can be rolled back by creating new pools at 1.32 and migrating workloads
- Keep previous node pool configurations documented for quick recreation

Would you like me to adjust any part of this plan based on your specific cluster size, workload patterns, or operational constraints?