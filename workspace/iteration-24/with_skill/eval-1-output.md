# GKE Upgrade Plan: 1.32 → 1.33

**Cluster:** Standard GKE cluster  
**Channel:** Regular  
**Current Version:** 1.32  
**Target Version:** 1.33  
**Region:** us-central1-a  
**Timeline:** Before end of quarter  

## Executive Summary

This plan covers upgrading your 3-node-pool Standard cluster from GKE 1.32 to 1.33. Given your workload diversity (general-purpose, Postgres, ML inference), we'll use a phased approach with appropriate upgrade strategies per pool type. The total upgrade window should be 4-6 hours depending on pool sizes.

## Version Compatibility Assessment

✅ **Target version availability:** Verify 1.33 is available in Regular channel:
```bash
gcloud container get-server-config --zone us-central1-a --format="yaml(channels.REGULAR)"
```

✅ **Version skew:** 1.32→1.33 is a single minor version jump - fully supported  
✅ **Breaking changes:** Review [GKE 1.33 release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) for API deprecations

⚠️ **Critical check - Deprecated APIs:**
```bash
# Check for deprecated API usage (most common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Also check GKE deprecation insights in console
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=us-central1-a \
    --project=PROJECT_ID
```

## Upgrade Strategy by Node Pool

### 1. General-Purpose Pool (Upgrade First)
- **Strategy:** Surge upgrade
- **Settings:** `maxSurge=5%` (minimum 1), `maxUnavailable=0`
- **Rationale:** Stateless workloads can tolerate rolling replacement

### 2. High-Memory Pool (Postgres) (Upgrade Second)  
- **Strategy:** Surge upgrade (conservative)
- **Settings:** `maxSurge=1, maxUnavailable=0`
- **Rationale:** Database workloads need careful one-at-a-time replacement
- **Special prep:** Verify PDBs protect Postgres replicas, take application backup

### 3. GPU Pool (ML Inference) (Upgrade Last)
- **Strategy:** Depends on your GPU reservation setup
- **If fixed reservation (no surge capacity):** `maxSurge=0, maxUnavailable=1`
- **If surge capacity available:** `maxSurge=1, maxUnavailable=0`
- **Rationale:** GPU nodes don't support live migration; inference workloads benefit from autoscaled blue-green to avoid service interruption

**Recommended GPU strategy - Autoscaled Blue-Green:**
```bash
gcloud container node-pools update GPU_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone us-central1-a \
    --enable-autoscaling \
    --total-min-nodes MIN --total-max-nodes MAX \
    --strategy=AUTOSCALED_BLUE_GREEN \
    --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

## Detailed Upgrade Sequence

### Phase 1: Pre-Flight Validation (30 minutes)

**Maintenance Window Setup:**
```bash
# Set weekend maintenance window (recommend Saturday 2-6 AM)
gcloud container clusters update CLUSTER_NAME \
    --zone us-central1-a \
    --maintenance-window-start "2024-12-14T02:00:00-06:00" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Pre-upgrade Checklist:**
- [ ] Deprecated API check completed (see commands above)
- [ ] Postgres operator compatibility with K8s 1.33 verified
- [ ] ML inference service PDBs configured
- [ ] GPU driver compatibility confirmed for target GKE version
- [ ] Application-level Postgres backup completed
- [ ] Monitoring baseline captured (error rates, latency)

### Phase 2: Control Plane Upgrade (15 minutes)

```bash
# Upgrade control plane first (required order)
gcloud container clusters upgrade CLUSTER_NAME \
    --zone us-central1-a \
    --master \
    --cluster-version 1.33

# Verify control plane health
kubectl get pods -n kube-system
kubectl get nodes  # Should show CP at 1.33, nodes still at 1.32
```

### Phase 3: Node Pool Upgrades (3-4 hours total)

**Step 1: General-Purpose Pool (45 minutes)**
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

# Monitor progress
watch 'kubectl get nodes -L cloud.google.com/gke-nodepool | grep GENERAL_POOL'
```

**Step 2: High-Memory Pool (Postgres) (60-90 minutes)**
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

# Validate Postgres health after each node
kubectl get pods -n POSTGRES_NAMESPACE -o wide
kubectl exec -it postgres-pod -- pg_isready
```

**Step 3: GPU Pool (ML Inference) (60-90 minutes)**
```bash
# Option A: If you have GPU surge capacity
gcloud container node-pools update GPU_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone us-central1-a \
    --max-surge-upgrade 1 \
    --max-unavailable-upgrade 0

# Option B: If fixed GPU reservation (more likely)
gcloud container node-pools update GPU_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone us-central1-a \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 1

# Upgrade
gcloud container node-pools upgrade GPU_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone us-central1-a \
    --cluster-version 1.33

# Validate inference service
curl -X POST INFERENCE_ENDPOINT/health
# Check GPU driver loaded correctly
kubectl exec -it gpu-pod -- nvidia-smi
```

### Phase 4: Post-Upgrade Validation (30 minutes)

**Cluster Health:**
```bash
# All components at target version
gcloud container clusters describe CLUSTER_NAME \
    --zone us-central1-a \
    --format="table(currentMasterVersion, nodePools[].version)"

# All nodes ready
kubectl get nodes

# System pods healthy  
kubectl get pods -n kube-system | grep -v Running
```

**Workload Health:**
```bash
# No stuck deployments
kubectl get deployments -A | grep -v "READY"

# Postgres cluster healthy
kubectl get postgresql -A  # Or your operator's CRD
kubectl exec -it postgres-primary -- pg_isready

# ML inference responding
curl INFERENCE_ENDPOINT/health
kubectl get pods -l app=inference -o wide
```

## Risk Mitigation

### Postgres-Specific Precautions
- **PDB Configuration:** Ensure `minAvailable: 1` for Postgres replicas to prevent simultaneous eviction
- **Backup Strategy:** Take `pg_dump` before starting node upgrades
- **Connection Pooling:** Verify PgBouncer or similar can handle brief connection interruptions
- **Replica Validation:** Check replication lag after each node upgrade

### GPU Pool Considerations  
- **Driver Testing:** Create a staging GPU node at 1.33 first to validate CUDA compatibility
- **Inference Latency:** Monitor p95/p99 latency during GPU node replacement
- **Model Loading:** Large models may take 5-10 minutes to load on new GPU nodes
- **Capacity Planning:** With `maxUnavailable=1`, you'll have temporary capacity reduction

### Common Failure Scenarios
1. **PDB blocking drain:** Temporarily patch restrictive PDBs
2. **GPU surge quota exhausted:** Use `maxUnavailable` mode instead  
3. **Postgres connection storms:** Scale down non-essential apps during high-memory pool upgrade
4. **Inference cold starts:** Pre-warm models on new GPU nodes before old node drain

## Rollback Plan

**If control plane upgrade fails:**
- Patch rollback possible within hours (contact GKE support)
- Node pools remain functional at 1.32

**If node pool upgrade fails:**
- Cancel operation: GKE completes current node batch then stops
- Mixed-version state (some 1.32, some 1.33) is valid and functional
- Retry after fixing root cause (usually PDB or quota issues)

**Emergency rollback (node pools):**
```bash
# Create rollback node pool at 1.32
gcloud container node-pools create POOL_NAME-rollback \
    --cluster CLUSTER_NAME \
    --zone us-central1-a \
    --cluster-version 1.32 \
    --num-nodes 3

# Cordon problematic nodes and migrate workloads
kubectl cordon -l cloud.google.com/gke-nodepool=PROBLEMATIC_POOL
```

## Timeline Estimate

- **Pre-flight:** 30 minutes
- **Control plane:** 15 minutes  
- **General pool:** 45 minutes
- **High-memory pool:** 90 minutes
- **GPU pool:** 90 minutes  
- **Validation:** 30 minutes
- **Buffer:** 60 minutes

**Total:** 5.5 hours (plan for 6-hour maintenance window)

## Success Criteria

✅ All nodes at GKE 1.33  
✅ All deployments at desired replica count  
✅ Postgres primary/replicas healthy with <1s lag  
✅ ML inference endpoints responding with <500ms p95 latency  
✅ No CrashLoopBackOff or Pending pods  
✅ Application error rates within pre-upgrade baseline  

## Next Steps

1. **Verify target version availability** in Regular channel
2. **Schedule maintenance window** (recommend weekend off-hours)
3. **Test GPU driver compatibility** in dev/staging cluster
4. **Coordinate with application teams** for Postgres and ML inference services
5. **Set up monitoring dashboards** to track upgrade progress

Would you like me to customize any part of this plan based on your specific node pool sizes or workload requirements?