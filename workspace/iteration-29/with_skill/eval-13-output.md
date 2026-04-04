# GKE Upgrade Plan for Long-Running Batch Jobs

## Executive Summary

For 8-16 hour batch jobs, GKE's default surge upgrade strategy is **incompatible** — it force-evicts pods after 1 hour regardless of `terminationGracePeriodSeconds`. You need **autoscaled blue-green upgrade strategy** combined with job scheduling coordination.

## Key Issue: Surge Upgrade Timeout

- **GKE's surge upgrade timeout:** 1 hour maximum for pod eviction
- **Your job duration:** 8-16 hours
- **Result:** Jobs will be force-killed mid-execution during upgrades

## Recommended Approach

### Primary Strategy: Autoscaled Blue-Green + Job Coordination

**Step 1: Configure autoscaled blue-green on batch node pools**

```bash
# Enable autoscaling if not already enabled
gcloud container node-pools update BATCH_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --enable-autoscaling \
  --total-min-nodes 0 \
  --total-max-nodes MAX_NODES

# Configure autoscaled blue-green upgrade
gcloud container node-pools update BATCH_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --enable-autoscaled-blue-green-upgrade \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=7200s
```

**Step 2: Set extended termination grace period on batch pods**

```yaml
apiVersion: batch/v1
kind: Job
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 57600  # 16 hours
      containers:
      - name: batch-processor
        image: your-batch-image
```

**Step 3: Coordinate upgrade timing with job scheduler**

```bash
# 1. Pause new job submissions
kubectl patch cronjob JOB_NAME -p '{"spec":{"suspend":true}}'

# 2. Wait for running jobs to complete OR proceed with autoscaled blue-green
# (it will respect the long termination grace period)

# 3. Trigger upgrade during low-activity window
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.31.x-gke.latest

# Wait for control plane upgrade, then:
gcloud container node-pools upgrade BATCH_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.31.x-gke.latest

# 4. Resume job submissions after upgrade
kubectl patch cronjob JOB_NAME -p '{"spec":{"suspend":false}}'
```

## Alternative Strategy: Maintenance Exclusions

If you prefer to avoid job coordination, use cluster-level maintenance exclusions:

```bash
# Block all upgrades during batch campaigns
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "batch-campaign-q4" \
  --add-maintenance-exclusion-start-time "2024-01-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-02-14T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Manual upgrade during scheduled gap between campaigns
# (Remove exclusion temporarily or trigger manual upgrade)
```

## Pre-Upgrade Checklist

```markdown
Long-Running Batch Job Upgrade Checklist

Batch Job Protection
- [ ] Autoscaled blue-green configured on batch node pools
- [ ] terminationGracePeriodSeconds set to exceed max job duration (57600s for 16h)
- [ ] Jobs have checkpoint/resume capability (recommended)
- [ ] Job scheduler coordination planned (pause → upgrade → resume)

Compatibility Validation
- [ ] Target version 1.31.x available in Regular channel
- [ ] Batch job framework (Kubernetes Job, Argo Workflows, etc.) compatible with 1.31
- [ ] No deprecated APIs in batch job specs (check GKE deprecation insights)
- [ ] Control plane upgrade path: 1.30 → 1.31 (single minor jump)

Infrastructure Readiness  
- [ ] Node pool autoscaling enabled with appropriate max limits
- [ ] Sufficient quota for blue-green temporary capacity
- [ ] Maintenance window configured for low-activity periods
- [ ] Monitoring active for job completion rates and upgrade progress

Rollback Plan
- [ ] Procedure to cancel autoscaled blue-green mid-upgrade documented
- [ ] Job restart/resume procedures tested
- [ ] Downgrade path identified (create new pool at 1.30 if needed)
```

## Why This Approach Works

1. **Autoscaled blue-green** is the ONLY GKE native strategy that respects `terminationGracePeriodSeconds` beyond 1 hour
2. **Cost efficient:** Unlike standard blue-green, it scales down the old pool as jobs drain to the new pool
3. **Job-aware:** Extended grace periods let jobs complete naturally before eviction
4. **Automatic:** No manual pod migration required

## Timeline Expectations

- **Control plane upgrade:** 10-15 minutes
- **Node pool autoscaled blue-green:** 2-4 hours depending on job completion
- **Total maintenance window:** Plan for 4-6 hours to accommodate longest-running jobs

## Monitoring During Upgrade

```bash
# Track job completion
kubectl get jobs -A --watch

# Monitor blue-green progress
kubectl get nodes -l cloud.google.com/gke-nodepool=BATCH_POOL_NAME -o wide --watch

# Check for stuck pods
kubectl get pods -A | grep Terminating
```

**Key insight:** Standard surge upgrades are fundamentally incompatible with batch jobs exceeding 1 hour. Autoscaled blue-green is specifically designed for this use case — it's the only native GKE strategy that properly handles long-running workloads.