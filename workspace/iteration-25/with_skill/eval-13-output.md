# GKE Upgrade Plan: Long-Running Batch Jobs (8-16 hours)

## Current State Analysis
- **Cluster:** Standard GKE on Regular release channel
- **Upgrade path:** 1.30 → 1.31 (single minor version jump)
- **Challenge:** Batch jobs running 8-16 hours exceed GKE's 1-hour pod eviction timeout during surge upgrades

## Recommended Strategy: Autoscaled Blue-Green

**Why autoscaled blue-green is ideal for your use case:**
- Respects longer `terminationGracePeriodSeconds` (no 1-hour force-eviction limit)
- Allows jobs to complete naturally during drain phase
- More cost-efficient than standard blue-green (scales down old pool as new pool scales up)
- Provides clean rollback path if needed

## Pre-Upgrade Configuration

### 1. Enable Autoscaling on Batch Node Pools
```bash
# Configure autoscaling and blue-green strategy
gcloud container node-pools update BATCH_NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --enable-autoscaling \
  --total-min-nodes 0 \
  --total-max-nodes MAX_NODES \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=7200s
```

### 2. Configure Batch Workloads
```yaml
# Add to your batch job specs
spec:
  template:
    metadata:
      annotations:
        # Prevent cluster autoscaler from evicting during scale-down
        cluster-autoscaler.kubernetes.io/safe-to-evict: "false"
    spec:
      # Allow extended graceful termination (set to job max duration + buffer)
      terminationGracePeriodSeconds: 61200  # 17 hours
      containers:
      - name: batch-job
        # Ensure proper resource requests for scheduling
        resources:
          requests:
            cpu: "1000m"
            memory: "2Gi"
```

## Upgrade Execution Plan

### Phase 1: Control Plane Upgrade
```bash
# Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.31.X-gke.XXXX

# Verify control plane upgrade
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="value(currentMasterVersion)"
```

### Phase 2: Batch-Aware Node Pool Upgrade

**Option A: Wait for Job Completion (Recommended)**
```bash
# 1. Stop new batch job submissions
kubectl scale deployment batch-job-scheduler --replicas=0

# 2. Monitor running jobs
kubectl get jobs -n batch-namespace
kubectl get pods -n batch-namespace -o wide

# 3. Wait for jobs to complete naturally (8-16 hours)
# Monitor with: watch 'kubectl get jobs -n batch-namespace'

# 4. Once all jobs complete, upgrade node pools
gcloud container node-pools upgrade BATCH_NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.31.X-gke.XXXX

# 5. Resume job scheduling
kubectl scale deployment batch-job-scheduler --replicas=1
```

**Option B: Concurrent Upgrade with Autoscaled Blue-Green**
```bash
# Upgrade immediately - autoscaled blue-green respects long termination periods
gcloud container node-pools upgrade BATCH_NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.31.X-gke.XXXX

# Monitor progress - jobs will migrate gracefully as old pool scales down
watch 'kubectl get nodes -L cloud.google.com/gke-nodepool'
```

## Alternative: Maintenance Exclusions

If you prefer manual control over upgrade timing:

```bash
# Block node upgrades during active batch campaigns
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "batch-campaign-freeze" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Manually upgrade during batch job gaps
# Remove exclusion temporarily when ready:
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --remove-maintenance-exclusion-name "batch-campaign-freeze"
```

## Pre-Upgrade Checklist

```markdown
- [ ] Cluster: ___ | Current: 1.30 | Target: 1.31
- [ ] Autoscaling enabled on batch node pools
- [ ] Autoscaled blue-green rollout policy configured
- [ ] Batch jobs have terminationGracePeriodSeconds ≥ max job duration
- [ ] Resource requests configured on all batch containers
- [ ] Job scheduler/submission pipeline identified
- [ ] Monitoring in place for job completion tracking
- [ ] 1.31 tested with representative batch workloads in staging
```

## Monitoring During Upgrade

```bash
# Track node pool upgrade progress
kubectl get nodes -o custom-columns="NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,POOL:.metadata.labels.cloud\.google\.com/gke-nodepool"

# Monitor batch job status
kubectl get jobs -n batch-namespace -o wide
kubectl get pods -n batch-namespace --field-selector=status.phase=Running

# Watch autoscaling behavior
kubectl describe nodes | grep -A5 "Allocated resources"
```

## Recovery Plan

If jobs are unexpectedly terminated:
1. Check job logs for checkpoint data
2. Restart jobs from last checkpoint
3. Consider rolling back node pool if widespread job failures occur

## Cost Optimization

- Schedule upgrades during low-batch periods when possible
- Use Spot VMs for batch node pools (workloads already handle interruption)
- Configure cluster autoscaler to scale to zero during idle periods

This approach ensures your 8-16 hour batch jobs complete successfully while upgrading to 1.31. The autoscaled blue-green strategy is specifically designed for long-running workloads like yours.