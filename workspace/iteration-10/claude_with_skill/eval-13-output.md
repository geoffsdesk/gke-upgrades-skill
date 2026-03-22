# GKE Upgrade Plan for Long-Running Batch Jobs

## Executive Summary

For your 8-16 hour batch jobs, the key is preventing mid-job interruption during upgrades. I recommend a **maintenance exclusion + scheduled upgrade approach** rather than disabling auto-upgrades entirely.

## Recommended Strategy

### 1. Use Maintenance Exclusions for Protection

Apply a **"No minor or node upgrades"** exclusion during active batch campaigns:

```bash
# Block disruptive upgrades while allowing security patches
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "batch-processing-protection" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time YYYY-MM-DDTHH:MM:SSZ \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

This exclusion:
- ✅ Blocks node pool upgrades that would kill your jobs
- ✅ Blocks minor version upgrades (1.30→1.31)  
- ✅ Still allows control plane security patches
- ✅ Can extend up to version's End of Support date

### 2. Dedicated Node Pool Strategy

Create separate node pools for batch vs. other workloads:

```bash
# Create batch-specific node pool
gcloud container node-pools create batch-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --num-nodes 3 \
  --machine-type n2-standard-8 \
  --node-labels workload-type=batch
```

**Benefits:**
- Upgrade batch pool separately during scheduled maintenance windows
- Keep other workloads on auto-upgrade for security patches
- Use node selectors to ensure batch jobs only run on protected nodes

### 3. Upgrade Execution Plan

**Phase 1: Control Plane (safe for running jobs)**
```bash
# Control plane upgrade doesn't affect running pods
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.31.x-gke.yyyy
```

**Phase 2: Node Pool Upgrade (scheduled window)**
```bash
# Wait for batch job completion, then:
gcloud container node-pools update batch-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1  # One node at a time

gcloud container node-pools upgrade batch-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.yyyy
```

## Workload Protection Checklist

```
Pre-Upgrade Protection Setup
- [ ] Maintenance exclusion "no minor or node upgrades" applied
- [ ] Batch jobs isolated on dedicated node pool
- [ ] Node selectors configured: nodeSelector: workload-type: batch
- [ ] PodDisruptionBudgets configured for batch workloads
- [ ] Jobs have checkpointing enabled for resume after interruption

Job Monitoring During Protection Period
- [ ] Monitor job completion status
- [ ] Track maintenance exclusion expiration date
- [ ] Plan upgrade window between batch campaigns
- [ ] Verify no other critical workloads on batch pool

Upgrade Execution (scheduled window)
- [ ] Confirm no active batch jobs: kubectl get jobs -n NAMESPACE
- [ ] Remove maintenance exclusion or let it expire
- [ ] Upgrade control plane first (safe operation)
- [ ] Wait for batch job completion window
- [ ] Upgrade batch node pool with maxUnavailable=1
- [ ] Verify job scheduling works post-upgrade
```

## Advanced: Autoscaled Blue-Green for Maximum Safety

For the most protection, consider GKE's **autoscaled blue-green upgrade** (preview):

```bash
gcloud container node-pools update batch-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaled-blue-green-upgrade \
  --standard-rollout-policy-batch-soak-duration 24h
```

**Why this works well for batch jobs:**
- Creates new pool, gracefully drains old pool
- Supports longer eviction periods for job completion
- Automatic rollback if issues detected
- Cost-effective scaling based on demand

## Alternative: Cordon and Wait Pattern

If you prefer manual control:

```bash
# 1. Cordon batch node pool (prevents new scheduling)
kubectl cordon -l workload-type=batch

# 2. Wait for jobs to complete naturally
kubectl get jobs -n BATCH_NAMESPACE --watch

# 3. Once empty, upgrade the pool
gcloud container node-pools upgrade batch-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.yyyy

# 4. Uncordon after upgrade
kubectl uncordon -l workload-type=batch
```

## Timeline Recommendations

**Immediate (this week):**
- Apply maintenance exclusion to prevent forced upgrades
- Verify current 1.30 version is not approaching EoS

**Planned upgrade window:**
- Schedule during natural gap between batch campaigns
- Control plane upgrade: any time (no job impact)
- Node upgrade: only during job-free window

**Ongoing:**
- Monitor GKE release schedule for 1.30 End of Support date
- Plan regular upgrade cadence aligned with batch processing schedule

This approach gives you maximum control while maintaining GKE's security posture through continued control plane patches.