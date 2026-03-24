# GKE Upgrade Plan for Long-Running Batch Jobs

## Problem Analysis

Your 8-16 hour batch jobs are incompatible with GKE's default surge upgrade strategy, which force-evicts pods after 1 hour regardless of `terminationGracePeriodSeconds`. This will kill your jobs mid-execution.

## Recommended Approach: Autoscaled Blue-Green Strategy

**Primary recommendation:** Use GKE's **autoscaled blue-green upgrade strategy** - it's specifically designed for long-running workloads and respects extended termination periods without the 1-hour force-eviction limit.

### Configuration

```bash
# Configure autoscaled blue-green for your batch node pools
gcloud container node-pools update BATCH_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --enable-autoscaling \
    --total-min-nodes MIN_NODES --total-max-nodes MAX_NODES \
    --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Set extended termination grace period in your batch job specs
# terminationGracePeriodSeconds: 57600  # 16 hours
```

**How it works:**
- Creates a new "green" node pool (25% initial capacity)
- Cordons the old "blue" pool
- Green pool auto-scales up as batch jobs complete and get rescheduled
- Blue pool scales down as jobs naturally finish
- No force-eviction after 1 hour - respects your full termination period
- Cost-efficient: avoids 2x resource cost of standard blue-green

## Alternative: Maintenance Exclusion + Controlled Timing

If autoscaled blue-green isn't available in your region yet:

```bash
# Block auto-upgrades during batch campaigns
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "batch-campaign-q1" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support

# When ready to upgrade (between campaigns):
# 1. Verify no long-running jobs
kubectl get pods -A --field-selector=status.phase=Running | grep batch

# 2. Trigger manual upgrade
gcloud container clusters upgrade CLUSTER_NAME --cluster-version 1.31.x-gke.xxx
gcloud container node-pools upgrade BATCH_POOL_NAME --cluster CLUSTER_NAME --cluster-version 1.31.x-gke.xxx

# 3. Remove exclusion to resume normal auto-upgrades
gcloud container clusters update CLUSTER_NAME \
    --remove-maintenance-exclusion-name "batch-campaign-q1"
```

## Pre-Upgrade Checklist

```
Batch Job Upgrade Checklist
- [ ] Cluster: ___ | Current: 1.30 | Target: 1.31
- [ ] Batch jobs have checkpointing/resume capability
- [ ] terminationGracePeriodSeconds ≥ max job duration (57600s for 16h)
- [ ] PDBs configured: minAvailable: 1 (prevents multiple batch pods draining simultaneously)
- [ ] Jobs managed by controllers (CronJob/Job), no bare pods
- [ ] Autoscaling enabled on batch node pools
- [ ] Sufficient quota for green pool scale-up
- [ ] Monitoring in place to track job completion rates

Timing Strategy Selected:
- [ ] Option A: Autoscaled blue-green (respects long termination periods)
- [ ] Option B: Maintenance exclusion during campaigns + manual upgrades between
```

## Step-by-Step Runbook

### Phase 1: Control Plane Upgrade (Safe)
```bash
# Control plane upgrade doesn't affect running pods
gcloud container clusters upgrade CLUSTER_NAME \
    --zone ZONE \
    --master \
    --cluster-version 1.31.x-gke.xxx

# Verify (10-15 min)
gcloud container clusters describe CLUSTER_NAME \
    --zone ZONE \
    --format="value(currentMasterVersion)"
```

### Phase 2: Node Pool Upgrade (Critical Phase)

**If using autoscaled blue-green:**
```bash
# Enable autoscaling if not already configured
gcloud container node-pools update BATCH_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --enable-autoscaling \
    --total-min-nodes 2 \
    --total-max-nodes 20

# Start autoscaled blue-green upgrade
gcloud container node-pools upgrade BATCH_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version 1.31.x-gke.xxx

# Monitor progress - jobs should complete naturally before eviction
watch 'kubectl get nodes -L cloud.google.com/gke-nodepool | grep -E "batch|Ready"'
watch 'kubectl get pods -n BATCH_NAMESPACE | grep Running'
```

**If using maintenance exclusion approach:**
```bash
# Wait for current jobs to complete
kubectl get pods -A --field-selector=status.phase=Running | grep batch

# Once clear, upgrade quickly during the gap
gcloud container node-pools upgrade BATCH_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version 1.31.x-gke.xxx \
    --max-surge-upgrade 2 \
    --max-unavailable-upgrade 0
```

## Post-Upgrade Validation

```bash
# Verify all nodes upgraded
kubectl get nodes -o wide

# Test batch job scheduling on new nodes
kubectl run test-batch --image=busybox --rm -it \
    --restart=Never \
    --overrides='{"spec":{"terminationGracePeriodSeconds":57600}}' \
    -- sleep 30

# Monitor next batch job completion
kubectl get jobs -n BATCH_NAMESPACE -w
```

## Key Insights

1. **Autoscaled blue-green is your best option** - it's the only native GKE strategy that respects termination periods >1 hour
2. **Standard blue-green requires 2x resources** - may not be cost-effective for large batch clusters  
3. **Surge upgrade will kill your jobs** - never use default surge for 8+ hour workloads
4. **Plan upgrades between batch campaigns** - coordinate with your job scheduling
5. **Checkpointing is essential** - ensure jobs can resume from where they left off

## Timeline Expectations

- **Control plane:** 10-15 minutes, no job impact
- **Autoscaled blue-green nodes:** 2-4 hours depending on job completion rate and node count
- **Total window:** Plan 4-6 hours for the complete upgrade

Would you like me to adapt this plan for your specific batch job patterns or cluster configuration?