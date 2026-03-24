# GKE Upgrade Plan for Long-Running Batch Jobs

## Executive Summary

For 8-16 hour batch jobs, GKE's default surge upgrade strategy will **force-evict your jobs after 1 hour** — well before they complete. We need a strategy that protects running jobs while enabling the necessary upgrade.

## Recommended Approach: Autoscaled Blue-Green + Job Management

### Primary Strategy: Autoscaled Blue-Green Upgrade

Autoscaled blue-green is specifically designed for long-running workloads like yours. Unlike surge upgrades, it respects extended `terminationGracePeriodSeconds` without force-eviction after 1 hour.

**Configure your batch job node pool:**
```bash
# Set extended termination grace period on batch jobs (16+ hours)
# In your batch job spec:
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 57600  # 16 hours

# Enable autoscaling on the batch node pool
gcloud container node-pools update BATCH_NODE_POOL \
  --cluster CLUSTER_NAME \
  --region REGION \
  --enable-autoscaling \
  --total-min-nodes 0 \
  --total-max-nodes MAX_NODES

# Configure autoscaled blue-green upgrade strategy
gcloud container node-pools update BATCH_NODE_POOL \
  --cluster CLUSTER_NAME \
  --region REGION \
  --strategy=AUTOSCALED_BLUE_GREEN \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

**How it works:**
- Creates new nodes (green pool) alongside existing nodes (blue pool)
- Cordons blue pool to prevent new job scheduling
- Respects your 16-hour `terminationGracePeriodSeconds` — no force eviction
- Scales down blue pool as jobs naturally complete and drain to green pool
- Cost-efficient: avoids 2x resource cost of standard blue-green

### Alternative: Maintenance Exclusion + Planned Upgrade Window

If you prefer maximum control over timing:

```bash
# Block node upgrades during batch campaigns
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "batch-campaign-freeze" \
  --add-maintenance-exclusion-start-time 2024-12-01T00:00:00Z \
  --add-maintenance-exclusion-end-time 2024-12-15T23:59:59Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Plan upgrade during batch job gaps
# Remove exclusion when ready to upgrade:
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --remove-maintenance-exclusion-name "batch-campaign-freeze"
```

## Step-by-Step Upgrade Runbook

### Phase 1: Prepare Batch Job Protection

**1. Upgrade control plane first (safe - doesn't affect running jobs):**
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.31
```

**2. Configure batch jobs for extended termination:**
```yaml
# Add to your batch job specs
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 57600  # 16 hours
      containers:
      - name: batch-job
        # Ensure your job handles SIGTERM gracefully
        # Save checkpoints on SIGTERM signal
```

**3. Verify job checkpoint/resume capability:**
- Test that jobs can save state on SIGTERM
- Confirm jobs resume from checkpoints after restart

### Phase 2: Node Pool Upgrade Strategy

**Option A: Autoscaled Blue-Green (Recommended)**
```bash
# Configure the upgrade strategy
gcloud container node-pools update BATCH_NODE_POOL \
  --cluster CLUSTER_NAME \
  --region REGION \
  --enable-autoscaling \
  --total-min-nodes 0 \
  --total-max-nodes MAX_NODES \
  --strategy=AUTOSCALED_BLUE_GREEN \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Execute upgrade
gcloud container node-pools upgrade BATCH_NODE_POOL \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.31
```

**Option B: Maintenance Exclusion + Scheduled Upgrade**
```bash
# Wait for current batch jobs to complete naturally
# Then remove exclusion and upgrade during gap:
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --remove-maintenance-exclusion-name "batch-campaign-freeze"

# Use conservative surge settings
gcloud container node-pools update BATCH_NODE_POOL \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

gcloud container node-pools upgrade BATCH_NODE_POOL \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.31
```

### Phase 3: Validation

**Monitor upgrade progress:**
```bash
# Check node versions
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool

# Verify no jobs were killed prematurely
kubectl get pods -A | grep batch

# Monitor batch job completion
kubectl get jobs -n BATCH_NAMESPACE
```

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist - Long-Running Batch Jobs
- [ ] Control plane upgraded to 1.31 first
- [ ] Batch jobs have terminationGracePeriodSeconds: 57600 (16 hours)
- [ ] Jobs handle SIGTERM gracefully and save checkpoints
- [ ] Batch node pool configured for autoscaling
- [ ] Autoscaled blue-green strategy configured
- [ ] Alternative: maintenance exclusion in place during batch campaigns
- [ ] Job scheduling paused 30 minutes before upgrade window
- [ ] Monitoring active to track job completion during drain
- [ ] Rollback plan documented (cordon new nodes, uncordon old nodes)
```

## Why This Approach Works

**Problems with default surge upgrade:**
- ❌ 1-hour PDB timeout forces eviction of 8-16 hour jobs
- ❌ Jobs restart from beginning, losing 1-8 hours of work
- ❌ No respect for extended `terminationGracePeriodSeconds`

**Benefits of autoscaled blue-green:**
- ✅ Respects your 16-hour termination grace period
- ✅ Jobs complete naturally before node drain
- ✅ Cost-efficient scaling (no 2x resource spike)
- ✅ Quick rollback path if issues arise

## Key Considerations

1. **Job Duration vs Grace Period:** Set `terminationGracePeriodSeconds` longer than your max job duration (16+ hours for your 8-16 hour jobs)

2. **Checkpoint Strategy:** Ensure jobs save progress on SIGTERM and can resume from checkpoints

3. **Scheduling Gap:** Plan upgrades during natural gaps between batch campaigns when possible

4. **Resource Requirements:** Autoscaled blue-green needs quota to create replacement nodes, but scales efficiently

5. **Regular Channel Timing:** Stay aware of when 1.30 reaches end of support to avoid forced upgrades during batch campaigns

This strategy protects your long-running jobs while enabling the necessary version upgrade. The autoscaled blue-green approach is specifically designed for workloads like yours that can't tolerate mid-execution eviction.