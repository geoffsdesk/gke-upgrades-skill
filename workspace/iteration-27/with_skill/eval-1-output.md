# GKE Upgrade Plan: Standard Cluster 1.32 → 1.33

## Cluster Overview
- **Cluster**: Standard GKE cluster
- **Current version**: 1.32
- **Target version**: 1.33
- **Channel**: Regular
- **Region**: us-central1-a
- **Node pools**: 3 (general-purpose, high-memory/Postgres, GPU/ML inference)

## Executive Summary
This upgrade follows GKE best practices with sequential control plane → node pool upgrades. The GPU inference pool requires special attention due to capacity constraints and inference latency sensitivity. Total estimated duration: 4-8 hours depending on pool sizes.

## Version Compatibility Assessment

### ✅ Version Availability
- **Status**: 1.33 should be available in Regular channel (verify with pre-flight commands)
- **Version skew**: Within supported limits (nodes will be max 1 minor version behind CP during upgrade)

### ⚠️ Breaking Changes to Review
Check [GKE 1.33 release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) for:
- Deprecated API removals (most common upgrade blocker)
- Postgres operator compatibility with K8s 1.33
- GPU driver changes that might affect ML inference workloads
- Changes to networking, storage, or scheduling behavior

### 🔍 Pre-upgrade Validation Required
```bash
# Check for deprecated API usage (upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# GKE deprecation insights
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=us-central1-a \
    --project=PROJECT_ID \
    --filter="category.category:RELIABILITY"
```

## Upgrade Strategy by Node Pool

### 1. General-Purpose Pool
- **Strategy**: Surge upgrade
- **Settings**: `maxSurge=5%` (minimum 1), `maxUnavailable=0`
- **Rationale**: Stateless workloads can tolerate rolling replacement, percentage-based surge scales with pool size

### 2. High-Memory Pool (Postgres)
- **Strategy**: Surge upgrade (conservative)
- **Settings**: `maxSurge=1, maxUnavailable=0`
- **Rationale**: Database workloads need careful one-at-a-time replacement, let PDBs protect quorum
- **Special considerations**:
  - Verify Postgres operator compatibility with K8s 1.33 before starting
  - Take application-level backup before upgrade
  - Monitor StatefulSet rollout status during upgrade

### 3. GPU Pool (ML Inference) ⚠️ **Requires Special Handling**
- **Strategy**: Autoscaled blue-green upgrade (recommended)
- **Rationale**: 
  - GPU VMs don't support live migration (every upgrade = pod restart)
  - Inference workloads are latency-sensitive
  - Blue-green keeps old pool serving while new pool warms up
  - Autoscaled variant avoids 2x resource cost of standard blue-green
- **Alternative if no autoscaling**: `maxSurge=0, maxUnavailable=1` (assumes fixed GPU reservation with no surge capacity)
- **Critical**: Test GPU driver compatibility with 1.33 in staging first

## Upgrade Sequence

### Phase 1: Control Plane Upgrade
**Estimated duration**: 10-15 minutes
**Impact**: Brief API unavailability, workloads continue running

### Phase 2: Node Pool Upgrades (sequential)
**Order**: General → High-memory → GPU (lowest risk to highest risk)

1. **General-purpose pool** (~1-2 hours depending on size)
2. **High-memory pool** (~2-4 hours, conservative pace)  
3. **GPU pool** (~1-2 hours for blue-green transition)

## Maintenance Controls

### Recommended Maintenance Window
```bash
# Saturday 2-6 AM for 4-hour window
gcloud container clusters update CLUSTER_NAME \
    --zone us-central1-a \
    --maintenance-window-start "2024-12-07T02:00:00-06:00" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### Optional: Upgrade Control
Since you're on Regular channel, the upgrade may happen automatically. To maintain manual control:
```bash
# Apply "no minor or node upgrades" exclusion to control timing
gcloud container clusters update CLUSTER_NAME \
    --zone us-central1-a \
    --add-maintenance-exclusion-name "q4-upgrade-control" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```
Remove this exclusion when ready to upgrade manually.

## Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist
- [ ] Cluster: ___ | Mode: Standard | Channel: Regular
- [ ] Current version: 1.32 | Target version: 1.33

Compatibility
- [ ] 1.33 available in Regular channel: `gcloud container get-server-config --zone us-central1-a --format="yaml(channels)"`
- [ ] No deprecated API usage (check command above)
- [ ] GKE 1.32→1.33 release notes reviewed for breaking changes
- [ ] Postgres operator compatibility with K8s 1.33 verified
- [ ] GPU driver compatibility tested in staging cluster

Workload Readiness
- [ ] PDBs configured for Postgres StatefulSets (not overly restrictive)
- [ ] No bare pods: `kubectl get pods -A -o json | jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'`
- [ ] Postgres application-level backup completed
- [ ] ML inference baseline metrics captured (latency, throughput)
- [ ] terminationGracePeriodSeconds adequate for graceful shutdown

Infrastructure
- [ ] General pool surge: maxSurge=5%, maxUnavailable=0
- [ ] High-memory pool surge: maxSurge=1, maxUnavailable=0  
- [ ] GPU pool: autoscaled blue-green configured OR maxSurge=0,maxUnavailable=1
- [ ] GPU reservation headroom verified (if using surge): `gcloud compute reservations describe RESERVATION_NAME --zone us-central1-a`
- [ ] Maintenance window configured (off-peak hours)

Ops Readiness
- [ ] Monitoring active, baseline metrics captured
- [ ] Upgrade window communicated to ML/data teams
- [ ] On-call engineer available during upgrade window
```

## Upgrade Runbook

### Phase 1: Control Plane
```bash
# Upgrade control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-central1-a \
  --master \
  --cluster-version 1.33

# Verify (wait 10-15 min)
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="value(currentMasterVersion)"
```

### Phase 2A: General-Purpose Pool
```bash
# Configure surge
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

# Monitor: watch 'kubectl get nodes -o wide'
```

### Phase 2B: High-Memory Pool (Postgres)
```bash
# Conservative surge settings
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

# Monitor StatefulSets: kubectl get sts -A -w
```

### Phase 2C: GPU Pool (Autoscaled Blue-Green)
```bash
# Configure autoscaled blue-green
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --enable-autoscaling \
  --enable-blue-green-upgrade \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Upgrade
gcloud container node-pools upgrade gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33

# Monitor inference latency during transition
```

## Post-Upgrade Validation

```bash
# All versions at 1.33
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# No stuck pods
kubectl get pods -A | grep -v Running | grep -v Completed

# Postgres health
kubectl get sts -A
kubectl exec -it postgres-primary-0 -- pg_isready

# GPU inference test
# Run inference request against ML service
# Verify GPU utilization: kubectl exec -it gpu-pod -- nvidia-smi
```

## Rollback Plan

- **Control plane**: Requires GKE support for minor version downgrade
- **Node pools**: Create new pools at 1.32, migrate workloads, delete upgraded pools
- **GPU pool**: Blue-green allows fast rollback by uncordoning old pool during soak period

## Risk Mitigation

### High Risk: GPU Pool
- **Mitigation**: Test 1.33 + GPU drivers in staging first
- **Monitoring**: Watch inference latency during blue-green transition
- **Contingency**: Keep old GPU pool available during soak period for quick rollback

### Medium Risk: Postgres Pool  
- **Mitigation**: Application-level backup, conservative surge settings
- **Monitoring**: Watch StatefulSet pod readiness, connection counts
- **Contingency**: Postgres operator may need version update for K8s 1.33

### Timeline Risk: End of Quarter Deadline
- **Mitigation**: Start with staging cluster upgrade 2 weeks before production
- **Buffer**: Plan production upgrade 1 week before deadline
- **Escalation**: GKE support can assist with stuck upgrades

Would you like me to adjust any part of this plan based on your specific pool sizes, workload types, or operational constraints?