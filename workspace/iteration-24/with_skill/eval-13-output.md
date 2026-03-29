# Long-Running Batch Job Upgrade Plan

## Overview
Standard GKE surge upgrades force-evict pods after 1 hour, which will kill your 8-16 hour batch jobs. You need a strategy that respects job completion times.

## Recommended Approach: Autoscaled Blue-Green Upgrade

**Primary strategy:** Use GKE's autoscaled blue-green upgrade for your batch node pools. This is the ONLY native GKE upgrade strategy that respects extended `terminationGracePeriodSeconds` without force-eviction after 1 hour.

### Configuration Steps

1. **Enable autoscaling on batch node pools:**
```bash
gcloud container node-pools update BATCH_POOL_NAME \
    --cluster CLUSTER_NAME \
    --region REGION \
    --enable-autoscaling \
    --total-min-nodes 0 \
    --total-max-nodes MAX_NODES
```

2. **Configure autoscaled blue-green upgrade:**
```bash
gcloud container node-pools update BATCH_POOL_NAME \
    --cluster CLUSTER_NAME \
    --region REGION \
    --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=7200s
```

3. **Update batch job `terminationGracePeriodSeconds`:**
```yaml
# In your Job/CronJob spec
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 57600  # 16 hours
      containers:
      - name: batch-job
        # ... your container spec
```

### How Autoscaled Blue-Green Works
- Creates green pool (25% initial capacity)
- Cordons blue pool (your current nodes)
- Green pool scales up as jobs complete and new jobs start
- Blue pool scales down as jobs drain naturally
- **No force-eviction** - respects your 16-hour grace period
- Cost-efficient: avoids 2x resource requirement of standard blue-green

## Alternative: Maintenance Exclusion Strategy

If autoscaled blue-green isn't suitable, use maintenance exclusions to control timing:

1. **Apply "no minor or node upgrades" exclusion:**
```bash
gcloud container clusters update CLUSTER_NAME \
    --region REGION \
    --add-maintenance-exclusion-name "batch-campaign-protection" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

2. **Manual upgrade during batch gaps:**
- Monitor batch job completion
- When queue is empty, manually trigger upgrade:
```bash
# Control plane first
gcloud container clusters upgrade CLUSTER_NAME \
    --region REGION \
    --master \
    --cluster-version 1.31.x-gke.xxxx

# Then node pools (after CP upgrade completes)
gcloud container node-pools upgrade BATCH_POOL_NAME \
    --cluster CLUSTER_NAME \
    --region REGION \
    --cluster-version 1.31.x-gke.xxxx
```

## Pre-Upgrade Checklist

```markdown
Long-Running Batch Job Upgrade Checklist

Workload Preparation
- [ ] Batch jobs have checkpointing/resume capability
- [ ] terminationGracePeriodSeconds set to exceed max job duration (57600s for 16h)
- [ ] Jobs managed by controllers (Job/CronJob, not bare pods)
- [ ] Resource requests/limits properly configured

Node Pool Strategy Selection
- [ ] Autoscaled blue-green configured (preferred)
  - [ ] Autoscaling enabled with appropriate min/max
  - [ ] blue-green-initial-node-percentage set (recommend 25%)
  - [ ] blue-green-full-batch-timeout configured (2+ hours)
- [ ] OR maintenance exclusion strategy chosen
  - [ ] "no minor or node upgrades" exclusion applied
  - [ ] Manual upgrade window planned during batch gaps

Capacity Planning
- [ ] Sufficient quota for green pool scaling (if using blue-green)
- [ ] Batch queue monitoring in place
- [ ] Job completion time estimates verified

Monitoring Setup
- [ ] Job completion rate baseline captured
- [ ] Node resource utilization monitoring active
- [ ] Upgrade progress tracking configured
```

## Execution Steps

### For Autoscaled Blue-Green:

1. **Pre-upgrade:**
   - Verify no urgent batch jobs in queue
   - Confirm autoscaling limits accommodate current + new jobs

2. **Upgrade control plane:**
```bash
gcloud container clusters upgrade CLUSTER_NAME \
    --region REGION \
    --master \
    --cluster-version 1.31.x-gke.xxxx
```

3. **Trigger node pool upgrade:**
```bash
gcloud container node-pools upgrade BATCH_POOL_NAME \
    --cluster CLUSTER_NAME \
    --region REGION \
    --cluster-version 1.31.x-gke.xxxx
```

4. **Monitor progress:**
```bash
# Watch job completion and node transition
kubectl get jobs -A --watch
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool

# Check autoscaler events
kubectl get events -n kube-system --field-selector involvedObject.name=cluster-autoscaler
```

### For Manual Timing Strategy:

1. **Monitor batch queue:**
```bash
kubectl get jobs -A --field-selector status.active=1
```

2. **When queue empty, pause new submissions and upgrade**

3. **Resume batch processing after validation**

## Validation

```bash
# Verify upgrade completion
gcloud container clusters describe CLUSTER_NAME \
    --region REGION \
    --format="table(name, currentMasterVersion, nodePools[].version)"

# Confirm jobs can start on new nodes
kubectl run test-batch --image=busybox --restart=OnFailure \
    --overrides='{"spec":{"template":{"spec":{"terminationGracePeriodSeconds":57600}}}}' \
    -- sleep 30

# Check job scheduling across node versions during transition
kubectl get pods -o wide -A | grep batch
```

## Key Advantages of This Approach

- **Zero job interruption:** Autoscaled blue-green respects full termination grace periods
- **Cost efficient:** No 2x resource spike like standard blue-green
- **Native GKE feature:** Fully supported, no custom scripting
- **Gradual transition:** Jobs naturally migrate as they complete

This strategy ensures your long-running batch jobs complete successfully while achieving the 1.30→1.31 upgrade safely.