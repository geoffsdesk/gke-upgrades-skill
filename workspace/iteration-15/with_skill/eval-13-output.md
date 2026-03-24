# GKE Upgrade Plan for Long-Running Batch Jobs

## Overview
For batch jobs running 8-16 hours, GKE's default surge upgrade strategy will force-evict your jobs after 1 hour during node pool upgrades. Here's a comprehensive plan to upgrade safely without killing mid-execution jobs.

## Recommended Strategy: Autoscaled Blue-Green + Job Scheduling

### Primary Approach
Use **autoscaled blue-green upgrade** strategy, which respects extended graceful termination periods and doesn't force-evict jobs after 1 hour like surge upgrades do.

```bash
# Configure autoscaled blue-green for your batch node pool
gcloud container node-pools update BATCH_NODE_POOL \
    --cluster CLUSTER_NAME \
    --region REGION \
    --enable-autoscaling \
    --total-min-nodes 0 --total-max-nodes MAX_NODES \
    --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

### Job Configuration Requirements
Ensure your batch jobs have:
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: long-batch-job
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 57600  # 16 hours
      containers:
      - name: batch-processor
        image: your-batch-image
        # Ensure checkpointing capability
```

## Step-by-Step Upgrade Plan

### Pre-Upgrade Phase (24-48 hours before)
1. **Job scheduling coordination:**
   ```bash
   # Pause new job submissions to batch queue
   # Let currently running jobs complete naturally
   kubectl get jobs -n batch-namespace
   ```

2. **Verify job completion timing:**
   - Check average job duration in your monitoring
   - Identify any jobs approaching 16-hour limit
   - Ensure all jobs have checkpointing enabled

### Control Plane Upgrade (Day 1)
```bash
# Upgrade control plane first (no impact on running jobs)
gcloud container clusters upgrade CLUSTER_NAME \
    --region REGION \
    --master \
    --cluster-version 1.31.x-gke.LATEST

# Verify control plane upgrade
gcloud container clusters describe CLUSTER_NAME \
    --region REGION \
    --format="value(currentMasterVersion)"
```

### Node Pool Upgrade Strategy Selection

**Option A: Autoscaled Blue-Green (Recommended)**
Best for: Jobs that need extended termination periods without 2x cost

```bash
# Configure the upgrade strategy
gcloud container node-pools update BATCH_NODE_POOL \
    --cluster CLUSTER_NAME \
    --region REGION \
    --strategy=AUTOSCALED_BLUE_GREEN \
    --enable-autoscaling \
    --total-min-nodes 0 --total-max-nodes MAX_BATCH_NODES \
    --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Execute the upgrade
gcloud container node-pools upgrade BATCH_NODE_POOL \
    --cluster CLUSTER_NAME \
    --region REGION \
    --cluster-version 1.31.x-gke.LATEST
```

**Option B: Maintenance Exclusion + Scheduled Upgrade**
Best for: Maximum control over timing

```bash
# Block node upgrades during active batch periods
gcloud container clusters update CLUSTER_NAME \
    --region REGION \
    --add-maintenance-exclusion-name "batch-processing-freeze" \
    --add-maintenance-exclusion-start-time "2024-02-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-02-15T23:59:59Z" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Schedule upgrade during planned gap between batch campaigns
# Remove exclusion when ready:
gcloud container clusters update CLUSTER_NAME \
    --region REGION \
    --remove-maintenance-exclusion-name "batch-processing-freeze"
```

**Option C: Dedicated Batch Pool (Architecture Change)**
Best for: Ongoing operational simplicity

```bash
# Create dedicated batch node pool with controlled upgrades
gcloud container node-pools create batch-pool \
    --cluster CLUSTER_NAME \
    --region REGION \
    --machine-type n1-standard-8 \
    --num-nodes 3 \
    --enable-autoscaling --min-nodes 0 --max-nodes 20 \
    --node-taints batch=true:NoSchedule

# Configure batch jobs to use this pool
# Add to job spec:
# nodeSelector:
#   batch-node: "true"
# tolerations:
# - key: "batch"
#   operator: "Equal"
#   value: "true"
#   effect: "NoSchedule"
```

## Pre-Upgrade Checklist

```
Batch Job Upgrade Readiness
- [ ] Current version: 1.30 | Target: 1.31 | Channel: Regular
- [ ] Average job duration documented: ___ hours
- [ ] Maximum job duration: ___ hours  
- [ ] Jobs have checkpointing/resume capability
- [ ] terminationGracePeriodSeconds ≥ max job duration (57600s for 16h jobs)
- [ ] PodDisruptionBudgets configured to protect running jobs
- [ ] Batch queue can be paused for new submissions
- [ ] Monitoring shows current job completion patterns
- [ ] Autoscaled blue-green strategy configured (if chosen)
- [ ] Maintenance exclusion planned (if using Option B)
- [ ] Upgrade window selected during natural gap between batches
```

## Execution Timeline

### Week 1: Control Plane + Non-Batch Pools
- Upgrade control plane to 1.31
- Upgrade non-batch node pools (web servers, APIs, etc.)
- Validate application compatibility with 1.31

### Week 2: Batch Pool Coordination
- Monitor batch job queue for natural completion gap
- When <25% jobs running and queue is light:
  - Pause new submissions
  - Execute batch node pool upgrade with chosen strategy
  - Validate first batch job completes successfully

## Monitoring During Upgrade

```bash
# Track node upgrade progress
watch 'kubectl get nodes -l batch-node=true -o wide'

# Monitor batch jobs during upgrade
kubectl get jobs -n batch-namespace --watch
kubectl get pods -n batch-namespace | grep batch

# Check for evicted jobs (should be none with proper strategy)
kubectl get events -n batch-namespace | grep Evicted
```

## Validation Commands

```bash
# Verify all nodes upgraded
gcloud container node-pools list --cluster CLUSTER_NAME --region REGION

# Test batch job on upgraded nodes
kubectl apply -f test-batch-job.yaml
kubectl logs -f job/test-batch-job

# Confirm no job interruptions in logs
kubectl get events --field-selector reason=Killing
```

## Rollback Plan

If issues arise during upgrade:

```bash
# For autoscaled blue-green: rollback is fast
gcloud container node-pools rollback BATCH_NODE_POOL \
    --cluster CLUSTER_NAME \
    --region REGION

# Alternatively: create new pool at 1.30, migrate workloads
gcloud container node-pools create batch-rollback \
    --cluster CLUSTER_NAME \
    --region REGION \
    --cluster-version 1.30.x-gke.PREVIOUS \
    --machine-type SAME_AS_ORIGINAL
```

## Key Recommendations

1. **Use autoscaled blue-green** - Only GKE strategy that respects >1 hour termination periods
2. **Never use surge for 8+ hour jobs** - Force eviction after 1 hour will kill your work
3. **Coordinate with job scheduling** - Time upgrades during natural completion gaps
4. **Test the upgrade path** in a staging cluster with sample 16-hour jobs first
5. **Enable checkpointing** so jobs can resume if anything goes wrong

This approach ensures your long-running batch jobs complete successfully while getting your cluster upgraded to 1.31 safely.