# GKE Upgrade Plan: Long-Running Batch Jobs (8-16 hours)

## Challenge Analysis

Your 8-16 hour batch jobs present a critical upgrade challenge: **GKE's default surge upgrade strategy force-evicts pods after 1 hour**, regardless of `terminationGracePeriodSeconds`. This will kill your jobs mid-execution.

## Recommended Strategy: Autoscaled Blue-Green Upgrade

**Primary recommendation:** Use GKE's **autoscaled blue-green upgrade strategy** for your batch node pools. This is the ONLY native GKE strategy that respects extended graceful termination periods without force-eviction.

### Why Autoscaled Blue-Green Works

- **No 1-hour eviction timeout** — respects your job's full `terminationGracePeriodSeconds`
- **Cost-efficient** — scales down the old (blue) pool as jobs drain to new (green) pool
- **Graceful migration** — jobs complete naturally before nodes are deleted
- **Native GKE feature** — no custom scripting required

## Implementation Plan

### Step 1: Pre-Upgrade Configuration

```bash
# Configure autoscaled blue-green on batch node pools
gcloud container node-pools update BATCH_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --enable-autoscaling \
    --total-min-nodes 0 \
    --total-max-nodes MAX_CAPACITY \
    --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Set extended termination grace period on batch jobs
# In your job manifests:
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 57600  # 16 hours
```

### Step 2: Batch Job Protection

```bash
# Apply maintenance exclusion to prevent auto-upgrades during active campaigns
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "batch-campaign-protection" \
    --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
    --add-maintenance-exclusion-end-time $(date -u -d "+7 days" +"%Y-%m-%dT%H:%M:%SZ") \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### Step 3: Upgrade Execution

**Control plane first:**
```bash
gcloud container clusters upgrade CLUSTER_NAME \
    --zone ZONE \
    --master \
    --cluster-version 1.31.x-gke.latest
```

**Wait for completion, then upgrade batch pools:**
```bash
# Pause new job submissions
# Wait for current jobs to reach checkpoint or natural completion

# Upgrade batch node pool with autoscaled blue-green
gcloud container node-pools upgrade BATCH_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version 1.31.x-gke.latest
```

## Alternative Strategy: Dedicated Batch Pool with Exclusions

If autoscaled blue-green isn't suitable, use a **dedicated batch node pool** with permanent upgrade exclusions:

```bash
# Create dedicated batch pool (if not already isolated)
gcloud container node-pools create batch-pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --machine-type n1-standard-8 \
    --num-nodes 5 \
    --node-taints batch=true:NoSchedule

# Configure persistent exclusion (no auto-upgrades on this pool)
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "batch-pool-permanent" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support

# Schedule manual upgrades only during planned gaps between batch campaigns
```

## Operational Workflow

### Before Each Upgrade Campaign

- [ ] **30 minutes before:** Pause new job submissions to batch queues
- [ ] **Monitor active jobs:** `kubectl get pods -l app=batch-job --field-selector=status.phase=Running`
- [ ] **Verify checkpointing:** Ensure jobs can resume from checkpoints if interrupted
- [ ] **Set maintenance window:** Configure for off-peak hours when fewer jobs typically run

### During Upgrade

- [ ] **Monitor drain progress:** Jobs should complete naturally, not be force-killed
- [ ] **Check autoscaler behavior:** Verify green pool scales up as blue pool drains
- [ ] **Validate job continuity:** New jobs should land on upgraded nodes

### After Upgrade

- [ ] **Resume job submissions**
- [ ] **Monitor job success rates:** Ensure no compatibility issues with 1.31
- [ ] **Remove temporary exclusions** (keep permanent ones for dedicated batch pools)

## Compatibility Checks for 1.30 → 1.31

- [ ] **Kubernetes 1.31 job controller changes:** Review [release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) for any batch/Job API changes
- [ ] **Container runtime compatibility:** Verify your batch containers work with the updated node image
- [ ] **Volume mounts:** Confirm any shared storage (NFS, Filestore) remains accessible
- [ ] **Resource requests/limits:** Ensure batch jobs have proper resource specifications

## Timeline Estimate

- **Control plane upgrade:** 10-15 minutes
- **Autoscaled blue-green node upgrade:** 2-4 hours per pool (depends on job completion timing)
- **Total maintenance window:** Plan for 6-8 hours to accommodate the longest-running jobs

## Emergency Rollback Plan

If jobs fail on 1.31 nodes:

1. **Immediate:** Scale new job submissions to zero
2. **Create rollback pool:** New node pool at 1.30 version
3. **Migrate active jobs:** Cordon 1.31 nodes, let jobs complete, restart failed jobs on 1.30 nodes
4. **Investigate:** Debug compatibility issues in staging environment

## Key Success Metrics

- [ ] **Zero mid-execution job kills** during upgrade
- [ ] **Job completion rates** remain within baseline
- [ ] **Upgrade completes** within planned maintenance window
- [ ] **New jobs** successfully start on 1.31 nodes

This approach prioritizes job continuity while still achieving the necessary upgrade. The autoscaled blue-green strategy is specifically designed for workloads like yours that cannot tolerate the standard 1-hour eviction timeout.