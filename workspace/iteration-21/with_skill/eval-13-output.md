# GKE Upgrade Plan: Long-Running Batch Jobs Protection

## Current Situation Analysis
- **Cluster**: Standard GKE on Regular release channel
- **Workload**: 8-16 hour batch processing jobs
- **Challenge**: GKE's default surge upgrade timeout is 1 hour — your jobs will be force-evicted

## Recommended Upgrade Strategy

### Primary Approach: Autoscaled Blue-Green Upgrade

For your long-running batch jobs, **autoscaled blue-green** is the optimal strategy:

```bash
# Configure autoscaled blue-green for your batch node pool
gcloud container node-pools update BATCH_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --enable-autoscaling \
    --total-min-nodes 0 \
    --total-max-nodes MAX_NODES \
    --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

**Why this works for your jobs:**
- Respects `terminationGracePeriodSeconds` without the 1-hour force-eviction limit
- Scales down the old pool as jobs complete naturally on the new pool
- Cost-efficient (avoids 2x resource requirement of standard blue-green)
- No hard timeout — jobs can run to completion

### Workload Configuration Requirements

Update your batch job specs to support graceful transitions:

```yaml
# Job/Pod spec adjustments
spec:
  terminationGracePeriodSeconds: 57600  # 16 hours (exceed your max job duration)
  containers:
  - name: batch-job
    resources:
      requests:  # Required for autoscaling decisions
        cpu: "2"
        memory: "4Gi"
```

## Complete Upgrade Runbook

### Phase 1: Pre-upgrade Setup (Do This First)

```bash
# 1. Verify current job status
kubectl get jobs -A
kubectl get pods -A -l job-type=batch --field-selector=status.phase=Running

# 2. Configure maintenance window for predictable timing
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --maintenance-window-start "2024-01-06T02:00:00Z" \
    --maintenance-window-duration 8h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# 3. Set up job completion monitoring
kubectl get events --field-selector involvedObject.kind=Job -w &
```

### Phase 2: Control Plane Upgrade

```bash
# Upgrade control plane first (1.30 → 1.31)
gcloud container clusters upgrade CLUSTER_NAME \
    --zone ZONE \
    --master \
    --cluster-version 1.31.X-gke.XXXX

# Verify control plane (wait ~10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
    --zone ZONE \
    --format="value(currentMasterVersion)"
```

### Phase 3: Batch Node Pool Upgrade

```bash
# Configure autoscaled blue-green strategy
gcloud container node-pools update BATCH_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --enable-autoscaling \
    --total-min-nodes 0 \
    --total-max-nodes 20 \
    --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Trigger node pool upgrade
gcloud container node-pools upgrade BATCH_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version 1.31.X-gke.XXXX
```

### Phase 4: Monitor Progress

```bash
# Watch node transitions (blue pool scales down, green scales up)
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=BATCH_POOL_NAME -o wide'

# Monitor job health during transition
kubectl get jobs -A -o wide
kubectl top pods -A -l job-type=batch
```

## Alternative Approach: Maintenance Exclusion Strategy

If you prefer to control timing more tightly:

```bash
# Block auto-upgrades during active batch campaigns
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "batch-processing-window" \
    --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-01-31T23:59:59Z" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# When ready to upgrade (between batch campaigns):
# 1. Verify no running jobs: kubectl get jobs -A --field-selector=status.active=1
# 2. Remove exclusion and trigger manual upgrade
```

## Pre-Upgrade Checklist

```markdown
- [ ] Batch jobs have checkpointing/resume capability
- [ ] terminationGracePeriodSeconds set to exceed max job duration (57600s for 16h)
- [ ] Resource requests specified on all batch containers
- [ ] Monitoring active for job completion events
- [ ] Maintenance window configured for off-peak hours
- [ ] Rollback plan documented (see below)
- [ ] Team aware of upgrade window and potential job migration
```

## Rollback Plan

If issues arise during the autoscaled blue-green upgrade:

```bash
# Cancel upgrade (keeps current progress)
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE
# Note: Autoscaled blue-green continues until completion - cannot pause mid-upgrade

# If new nodes have issues, cordon them to prevent new job scheduling
kubectl cordon -l cloud.google.com/gke-nodepool=BATCH_POOL_NAME
kubectl label nodes -l cloud.google.com/gke-nodepool=BATCH_POOL_NAME --overwrite upgrade-status=problematic

# Force jobs back to old nodes (emergency only)
kubectl delete nodes -l upgrade-status=problematic
```

## Key Advantages of This Approach

1. **No job interruption**: Jobs complete naturally on their original nodes
2. **Cost-efficient**: Old pool scales down as new pool scales up
3. **Graceful transition**: Respects your 16-hour graceful termination periods
4. **Automatic**: No manual cordon/drain orchestration required

## Post-Upgrade Validation

```bash
# Verify all nodes upgraded
kubectl get nodes -o wide

# Confirm batch jobs resuming on new nodes
kubectl get jobs -A
kubectl get pods -A -l job-type=batch

# Check resource utilization stabilized
kubectl top nodes
```

This strategy ensures your long-running batch jobs can complete without interruption while still achieving your 1.30→1.31 upgrade goal. The autoscaled blue-green approach is specifically designed for workloads like yours that exceed GKE's default 1-hour eviction timeout.